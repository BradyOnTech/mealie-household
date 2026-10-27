from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mealie.db.models._model_base import BaseMixins, FilterableColumn, SqlAlchemyBase
from mealie.db.models._model_utils.auto_init import auto_init
from mealie.db.models._model_utils.datetime import NaiveDateTime
from mealie.db.models._model_utils.guid import GUID

if TYPE_CHECKING:
    from ..users import User
    from .household import Household


class HouseholdMessage(SqlAlchemyBase, BaseMixins):
    """A message in the household's shared conversation (the app's Messages page)"""

    __tablename__ = "household_messages"

    id: FilterableColumn[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    group_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    household_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("households.id"), nullable=False, index=True)
    household: Mapped[Household] = relationship("Household", back_populates="household_messages")
    user_id: FilterableColumn[GUID] = mapped_column(GUID, ForeignKey("users.id"), nullable=False, index=True)
    user: Mapped[User] = relationship("User", back_populates="household_messages", foreign_keys=[user_id])
    text: Mapped[str] = mapped_column(String, nullable=False)

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class HouseholdMessageRead(SqlAlchemyBase, BaseMixins):
    """How far a user has read the conversation. It follows the user, whichever household they're in."""

    __tablename__ = "household_message_reads"

    id: Mapped[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    user_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    user: Mapped[User] = relationship("User", back_populates="household_message_read", foreign_keys=[user_id])
    last_read_at: Mapped[datetime] = mapped_column(NaiveDateTime, nullable=False)

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class UserPushSubscription(SqlAlchemyBase, BaseMixins):
    """
    A browser's Web Push subscription: one per installed app on a device. The endpoint is the push
    service's URL for that install, and the two keys encrypt what's sent to it.
    """

    __tablename__ = "user_push_subscriptions"

    id: Mapped[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    user_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("users.id"), nullable=False, index=True)
    user: Mapped[User] = relationship("User", back_populates="push_subscriptions", foreign_keys=[user_id])
    endpoint: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    p256dh: Mapped[str] = mapped_column(String, nullable=False)
    auth: Mapped[str] = mapped_column(String, nullable=False)
    user_agent: Mapped[str] = mapped_column(String, nullable=False, default="")

    @auto_init()
    def __init__(self, **_) -> None:
        pass
