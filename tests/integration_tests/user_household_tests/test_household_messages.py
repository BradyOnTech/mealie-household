"""The household's shared conversation, and the push notifications that tell everyone else about new messages."""

from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from mealie.schema.messages.messages import PushSubscriptionOut
from mealie.services.household_services import messages as message_service
from mealie.services.web_push import web_push
from tests.utils import api_routes
from tests.utils.fixture_schemas import TestUser

APPLE = "https://web.push.apple.com/"


@dataclass
class Sent:
    endpoint: str
    message: web_push.PushMessage


@dataclass
class FakePush:
    sent: list[Sent] = field(default_factory=list)
    gone: set[str] = field(default_factory=set)

    def __call__(self, subscription: PushSubscriptionOut, message: web_push.PushMessage) -> None:
        if subscription.endpoint in self.gone:
            raise web_push.SubscriptionGone
        self.sent.append(Sent(subscription.endpoint, message))


@pytest.fixture
def push(monkeypatch: pytest.MonkeyPatch) -> FakePush:
    fake = FakePush()
    monkeypatch.setattr(web_push, "send", fake)
    return fake


def send(client: TestClient, user: TestUser, text: str) -> dict:
    response = client.post(api_routes.households_messages, json={"text": text}, headers=user.token)
    assert response.status_code == 201, response.text
    return response.json()


def listing(client: TestClient, user: TestUser, **params) -> dict:
    response = client.get(api_routes.households_messages, params=params, headers=user.token)
    assert response.status_code == 200, response.text
    return response.json()


def read_all(client: TestClient, user: TestUser) -> dict:
    response = client.post(api_routes.households_messages_read, json={}, headers=user.token)
    assert response.status_code == 200, response.text
    return response.json()


def subscribe(client: TestClient, user: TestUser, endpoint: str | None = None) -> str:
    endpoint = endpoint or f"{APPLE}{uuid4().hex}"
    response = client.post(
        api_routes.households_messages_push_subscriptions,
        json={"endpoint": endpoint, "keys": {"p256dh": "p256dh-key", "auth": "auth-secret"}},
        headers=user.token,
    )
    assert response.status_code == 201, response.text
    assert response.json()["subscribed"] is True
    return endpoint


def test_household_members_share_a_conversation(api_client: TestClient, user_tuple: list[TestUser], push: FakePush):
    me, partner = user_tuple
    read_all(api_client, partner)

    sent = send(api_client, me, "  We're out of eggs  ")
    assert sent["text"] == "We're out of eggs"
    assert sent["user"]["fullName"] == me.full_name

    seen = listing(api_client, partner)
    assert seen["items"][-1]["id"] == sent["id"]
    assert seen["unread"] == 1
    # Your own messages are never unread
    assert listing(api_client, me)["unread"] == 0

    unread = api_client.get(api_routes.households_messages_unread, headers=partner.token).json()
    assert unread["unread"] == 1
    assert unread["lastMessage"]["id"] == sent["id"]

    assert read_all(api_client, partner)["unread"] == 0
    assert listing(api_client, partner)["unread"] == 0


def test_replying_marks_the_conversation_read(api_client: TestClient, user_tuple: list[TestUser], push: FakePush):
    me, partner = user_tuple
    send(api_client, me, "Tacos tonight?")
    assert listing(api_client, partner)["unread"] >= 1

    send(api_client, partner, "Yes please")
    assert listing(api_client, partner)["unread"] == 0


def test_messages_page_back_and_poll_forward(api_client: TestClient, user_tuple: list[TestUser], push: FakePush):
    me, _ = user_tuple
    texts = [f"page {i} {uuid4().hex[:6]}" for i in range(3)]
    sent = [send(api_client, me, text) for text in texts]

    newest = listing(api_client, me, limit=2)
    assert [item["text"] for item in newest["items"]] == texts[1:]
    assert newest["hasOlder"] is True

    older = listing(api_client, me, limit=1, before=newest["items"][0]["createdAt"])
    assert [item["text"] for item in older["items"]] == texts[:1]

    since = listing(api_client, me, after=sent[0]["createdAt"])
    assert [item["text"] for item in since["items"]] == texts[1:]
    assert since["hasOlder"] is False


@pytest.mark.parametrize("text", ["", "   ", "x" * 2001])
def test_message_text_is_checked(api_client: TestClient, unique_user: TestUser, text: str):
    response = api_client.post(api_routes.households_messages, json={"text": text}, headers=unique_user.token)
    assert response.status_code == 422


def test_other_households_cant_see_or_delete_messages(
    api_client: TestClient, unique_user: TestUser, h2_user: TestUser, push: FakePush
):
    sent = send(api_client, unique_user, "Just for our household")

    assert sent["id"] not in [item["id"] for item in listing(api_client, h2_user)["items"]]
    response = api_client.delete(api_routes.households_messages_message_id(sent["id"]), headers=h2_user.token)
    assert response.status_code == 404


def test_only_the_sender_deletes_a_message(api_client: TestClient, user_tuple: list[TestUser], push: FakePush):
    me, partner = user_tuple
    sent = send(api_client, me, "Typo")

    response = api_client.delete(api_routes.households_messages_message_id(sent["id"]), headers=partner.token)
    assert response.status_code == 403

    response = api_client.delete(api_routes.households_messages_message_id(sent["id"]), headers=me.token)
    assert response.status_code == 200
    assert sent["id"] not in [item["id"] for item in listing(api_client, me)["items"]]


def test_push_config_has_the_servers_key(api_client: TestClient, unique_user: TestUser):
    response = api_client.get(api_routes.households_messages_push, headers=unique_user.token)
    assert response.status_code == 200
    config = response.json()
    # An uncompressed P-256 point: 65 bytes, base64url without padding
    assert len(config["publicKey"]) == 87
    assert config["subscribed"] is False


@pytest.mark.parametrize(
    "endpoint",
    ["http://web.push.apple.com/abc", "https://example.com/push", "https://web.push.apple.com.evil.test/abc"],
)
def test_subscriptions_must_point_at_a_push_service(api_client: TestClient, unique_user: TestUser, endpoint: str):
    response = api_client.post(
        api_routes.households_messages_push_subscriptions,
        json={"endpoint": endpoint, "keys": {"p256dh": "key", "auth": "secret"}},
        headers=unique_user.token,
    )
    assert response.status_code == 422


def test_subscribe_and_unsubscribe(api_client: TestClient, unique_user: TestUser):
    endpoint = subscribe(api_client, unique_user)
    config = api_client.get(
        api_routes.households_messages_push, params={"endpoint": endpoint}, headers=unique_user.token
    )
    assert config.json()["subscribed"] is True

    response = api_client.delete(
        api_routes.households_messages_push_subscriptions, params={"endpoint": endpoint}, headers=unique_user.token
    )
    assert response.status_code == 200
    assert response.json()["subscribed"] is False


def test_a_new_message_notifies_everyone_else(api_client: TestClient, user_tuple: list[TestUser], push: FakePush):
    me, partner = user_tuple
    mine = subscribe(api_client, me)
    theirs = subscribe(api_client, partner)
    read_all(api_client, partner)

    send(api_client, me, "Can you grab milk on the way home?")

    assert [sent.endpoint for sent in push.sent] == [theirs]
    notification = push.sent[0].message
    assert notification.title == me.full_name
    assert notification.body == "Can you grab milk on the way home?"
    assert notification.url == "/household/messages"
    assert notification.badge == 1
    assert mine not in [sent.endpoint for sent in push.sent]


def test_a_signed_in_device_moves_to_its_new_user(api_client: TestClient, user_tuple: list[TestUser], push: FakePush):
    me, partner = user_tuple
    endpoint = subscribe(api_client, partner)
    # The same phone signs in as the other person
    subscribe(api_client, me, endpoint)

    send(api_client, me, "Only the other person's devices hear about this")
    assert endpoint not in [sent.endpoint for sent in push.sent]


def test_gone_subscriptions_are_forgotten(api_client: TestClient, user_tuple: list[TestUser], push: FakePush):
    me, partner = user_tuple
    endpoint = subscribe(api_client, partner)
    push.gone.add(endpoint)

    send(api_client, me, "Hello?")

    config = api_client.get(api_routes.households_messages_push, params={"endpoint": endpoint}, headers=partner.token)
    assert config.json()["subscribed"] is False


def test_test_notification_goes_to_your_own_devices(api_client: TestClient, user_tuple: list[TestUser], push: FakePush):
    me, partner = user_tuple
    mine = subscribe(api_client, me)
    subscribe(api_client, partner)

    response = api_client.post(api_routes.households_messages_push_test, headers=me.token)
    assert response.status_code == 200
    assert response.json()["sent"] >= 1
    assert mine in [sent.endpoint for sent in push.sent]
    assert all(
        sent.endpoint in {s.endpoint for s in me.repos.push_subscriptions.for_user(me.user_id)} for sent in push.sent
    )


def test_notification_previews_are_short():
    long = "word " * 100
    assert len(message_service.preview(long)) <= message_service.PREVIEW_LENGTH
    assert message_service.preview("a\n\nb") == "a b"
