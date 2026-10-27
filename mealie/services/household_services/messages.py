from datetime import datetime

from fastapi import HTTPException, status
from pydantic import UUID4

from mealie.core.root_logger import get_logger
from mealie.db.db_setup import session_context
from mealie.db.models._model_utils.datetime import get_utc_now
from mealie.repos.all_repositories import AllRepositories, get_repositories
from mealie.schema.messages.messages import (
    HouseholdMessageCreate,
    HouseholdMessageList,
    HouseholdMessageOut,
    HouseholdMessageSave,
    HouseholdMessageUnread,
    PushConfig,
    PushSubscriptionCreate,
    PushSubscriptionOut,
    PushSubscriptionSave,
    PushTestResult,
)
from mealie.schema.user.user import PrivateUser
from mealie.services.web_push import web_push

PAGE_SIZE = 50
MAX_PAGE_SIZE = 200
PREVIEW_LENGTH = 180
"""How much of a message a notification shows"""
MESSAGES_URL = "/household/messages"

logger = get_logger()


def preview(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= PREVIEW_LENGTH else f"{text[: PREVIEW_LENGTH - 1].rstrip()}…"


class HouseholdMessageService:
    """The household's shared conversation, and the notifications that tell everyone else about it"""

    def __init__(self, repos: AllRepositories, user: PrivateUser) -> None:
        self.repos = repos
        self.user = user

    @property
    def messages(self):
        return self.repos.household_messages

    def unread_count(self) -> int:
        return self.messages.count_from_others(self.user.id, self.messages.read_at(self.user.id))

    def list(
        self, before: datetime | None = None, after: datetime | None = None, limit: int = PAGE_SIZE
    ) -> HouseholdMessageList:
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        if after is not None:
            items, has_older = self.messages.since(after, limit), False
        else:
            items, has_older = self.messages.latest(limit, before)
        return HouseholdMessageList(items=items, has_older=has_older, unread=self.unread_count())

    def unread(self) -> HouseholdMessageUnread:
        return HouseholdMessageUnread(unread=self.unread_count(), last_message=self.messages.newest())

    def send(self, data: HouseholdMessageCreate) -> HouseholdMessageOut:
        message = self.messages.create(
            HouseholdMessageSave(
                text=data.text,
                group_id=self.user.group_id,
                household_id=self.user.household_id,
                user_id=self.user.id,
            )
        )
        # Writing a message means you've read everything up to it
        self.messages.mark_read(self.user.id, message.created_at)
        return message

    def delete(self, message_id: UUID4) -> HouseholdMessageOut:
        message = self.messages.get_one(message_id)
        if message is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Message not found")
        if message.user_id != self.user.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="You can only delete your own messages")
        return self.messages.delete(message_id)

    def mark_read(self, at: datetime | None = None) -> HouseholdMessageUnread:
        now = get_utc_now()
        # A device's clock can run ahead; never mark messages read that haven't been written yet
        self.messages.mark_read(self.user.id, min(at, now) if at else now)
        return self.unread()

    # Push subscriptions

    def push_config(self, endpoint: str | None = None) -> PushConfig:
        subscribed = False
        if endpoint:
            existing = self.repos.push_subscriptions.get_by_endpoint(endpoint)
            subscribed = existing is not None and existing.user_id == self.user.id
        return PushConfig(public_key=web_push.public_key(), subscribed=subscribed)

    def subscribe(self, data: PushSubscriptionCreate, user_agent: str = "") -> PushSubscriptionOut:
        return self.repos.push_subscriptions.save(
            PushSubscriptionSave(
                user_id=self.user.id,
                endpoint=data.endpoint,
                p256dh=data.keys.p256dh,
                auth=data.keys.auth,
                user_agent=user_agent[:255],
            )
        )

    def unsubscribe(self, endpoint: str) -> None:
        self.repos.push_subscriptions.remove(endpoint, user_id=self.user.id)

    def send_test(self) -> PushTestResult:
        message = web_push.PushMessage(
            title="Notifications are on",
            body="New household messages will show up here.",
            url=MESSAGES_URL,
            badge=self.unread_count(),
        )
        sent = deliver(self.repos, self.repos.push_subscriptions.for_user(self.user.id), message)
        return PushTestResult(sent=sent)


def deliver(repos: AllRepositories, subscriptions: list[PushSubscriptionOut], message: web_push.PushMessage) -> int:
    """Send to each subscription, forgetting the ones push services say are gone. Returns how many were sent."""
    sent = 0
    for subscription in subscriptions:
        try:
            web_push.send(subscription, message)
            sent += 1
        except web_push.SubscriptionGone:
            repos.push_subscriptions.remove(subscription.endpoint)
        except Exception:
            logger.exception("Couldn't send a push notification")
    return sent


def notify_household(message_id: UUID4, group_id: UUID4, household_id: UUID4) -> None:
    """
    Tell everyone else in the household about a new message. Runs after the response, in its own session,
    so a slow push service never holds up sending.
    """
    with session_context() as session:
        repos = get_repositories(session, group_id=group_id, household_id=household_id)
        message = repos.household_messages.get_one(message_id)
        if message is None:
            return
        sender = message.user.full_name or message.user.username or "Someone"
        by_user: dict[UUID4, list[PushSubscriptionOut]] = {}
        for subscription in repos.push_subscriptions.for_household(household_id, exclude_user_id=message.user_id):
            by_user.setdefault(subscription.user_id, []).append(subscription)

        for user_id, subscriptions in by_user.items():
            badge = repos.household_messages.count_from_others(user_id, repos.household_messages.read_at(user_id))
            push = web_push.PushMessage(title=sender, body=preview(message.text), url=MESSAGES_URL, badge=badge)
            deliver(repos, subscriptions, push)
