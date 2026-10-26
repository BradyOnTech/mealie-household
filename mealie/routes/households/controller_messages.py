from datetime import datetime
from functools import cached_property

from fastapi import APIRouter, BackgroundTasks, Query, Request
from pydantic import UUID4

from mealie.routes._base.base_controllers import BaseUserController
from mealie.routes._base.controller import controller
from mealie.schema.messages.messages import (
    HouseholdMessageCreate,
    HouseholdMessageList,
    HouseholdMessageOut,
    HouseholdMessageReadIn,
    HouseholdMessageUnread,
    PushConfig,
    PushSubscriptionCreate,
    PushTestResult,
)
from mealie.services.household_services.messages import (
    MAX_PAGE_SIZE,
    PAGE_SIZE,
    HouseholdMessageService,
    notify_household,
)

router = APIRouter(prefix="/households/messages", tags=["Households: Messages"])


@controller(router)
class HouseholdMessagesController(BaseUserController):
    @cached_property
    def service(self) -> HouseholdMessageService:
        return HouseholdMessageService(self.repos, self.user)

    @router.get("", response_model=HouseholdMessageList)
    def list_messages(
        self,
        before: datetime | None = None,
        after: datetime | None = None,
        limit: int = Query(PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    ) -> HouseholdMessageList:
        """The newest messages, oldest first; `before` pages back through history, `after` fetches what's new"""
        return self.service.list(before=before, after=after, limit=limit)

    @router.post("", response_model=HouseholdMessageOut, status_code=201)
    def send_message(self, data: HouseholdMessageCreate, bg: BackgroundTasks) -> HouseholdMessageOut:
        message = self.service.send(data)
        bg.add_task(notify_household, message.id, self.group_id, self.household_id)
        return message

    @router.get("/unread", response_model=HouseholdMessageUnread)
    def unread(self) -> HouseholdMessageUnread:
        return self.service.unread()

    @router.post("/read", response_model=HouseholdMessageUnread)
    def mark_read(self, data: HouseholdMessageReadIn) -> HouseholdMessageUnread:
        return self.service.mark_read(data.read_at)

    @router.get("/push", response_model=PushConfig)
    def push_config(self, endpoint: str | None = None) -> PushConfig:
        """The key to subscribe with, and whether `endpoint` is already subscribed for this user"""
        return self.service.push_config(endpoint)

    @router.post("/push/subscriptions", response_model=PushConfig, status_code=201)
    def subscribe(self, data: PushSubscriptionCreate, request: Request) -> PushConfig:
        self.service.subscribe(data, user_agent=request.headers.get("user-agent", ""))
        return self.service.push_config(data.endpoint)

    @router.delete("/push/subscriptions", response_model=PushConfig)
    def unsubscribe(self, endpoint: str) -> PushConfig:
        self.service.unsubscribe(endpoint)
        return self.service.push_config(endpoint)

    @router.post("/push/test", response_model=PushTestResult)
    def send_test(self) -> PushTestResult:
        """Send a notification to this user's own devices"""
        return self.service.send_test()

    @router.delete("/{message_id}", response_model=HouseholdMessageOut)
    def delete_message(self, message_id: UUID4) -> HouseholdMessageOut:
        return self.service.delete(message_id)
