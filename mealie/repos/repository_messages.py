from datetime import datetime

from pydantic import UUID4
from sqlalchemy import delete, func, select

from mealie.db.models.household.messages import HouseholdMessage, HouseholdMessageRead, UserPushSubscription
from mealie.db.models.users.users import User
from mealie.schema.messages.messages import HouseholdMessageOut, PushSubscriptionOut, PushSubscriptionSave

from .repository_generic import HouseholdRepositoryGeneric, RepositoryGeneric


class RepositoryHouseholdMessages(HouseholdRepositoryGeneric[HouseholdMessageOut, HouseholdMessage]):
    def _scoped(self):
        return self._query().filter_by(**self._filter_builder())

    def _validate(self, models) -> list[HouseholdMessageOut]:
        return [self.schema.model_validate(model) for model in models]

    def latest(self, limit: int, before: datetime | None = None) -> tuple[list[HouseholdMessageOut], bool]:
        """The newest `limit` messages (before `before`, if given), oldest first, and whether there are older ones"""
        query = self._scoped()
        if before is not None:
            query = query.where(HouseholdMessage.created_at < before)
        query = query.order_by(HouseholdMessage.created_at.desc(), HouseholdMessage.id.desc()).limit(limit + 1)
        models = list(self.session.execute(query).unique().scalars())
        return self._validate(reversed(models[:limit])), len(models) > limit

    def since(self, after: datetime, limit: int) -> list[HouseholdMessageOut]:
        """Messages newer than `after`, oldest first"""
        query = (
            self._scoped()
            .where(HouseholdMessage.created_at > after)
            .order_by(HouseholdMessage.created_at, HouseholdMessage.id)
            .limit(limit)
        )
        return self._validate(self.session.execute(query).unique().scalars())

    def newest(self) -> HouseholdMessageOut | None:
        query = self._scoped().order_by(HouseholdMessage.created_at.desc(), HouseholdMessage.id.desc()).limit(1)
        model = self.session.execute(query).unique().scalars().one_or_none()
        return self.schema.model_validate(model) if model else None

    def count_from_others(self, user_id: UUID4, since: datetime | None) -> int:
        query = (
            select(func.count(HouseholdMessage.id))
            .filter_by(**self._filter_builder())
            .where(HouseholdMessage.user_id != user_id)
        )
        if since is not None:
            query = query.where(HouseholdMessage.created_at > since)
        return self.session.execute(query).scalar_one()

    def read_at(self, user_id: UUID4) -> datetime | None:
        """When the user last read the conversation"""
        query = select(HouseholdMessageRead.last_read_at).where(HouseholdMessageRead.user_id == user_id)
        return self.session.execute(query).scalar_one_or_none()

    def mark_read(self, user_id: UUID4, at: datetime) -> datetime:
        """Move the user's read marker forward to `at`; it never moves back"""
        marker = self.session.execute(
            select(HouseholdMessageRead).where(HouseholdMessageRead.user_id == user_id)
        ).scalar_one_or_none()
        try:
            if marker is None:
                marker = HouseholdMessageRead(session=self.session, user_id=user_id, last_read_at=at)
                self.session.add(marker)
            elif marker.last_read_at < at:
                marker.last_read_at = at
            else:
                return marker.last_read_at
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return at


class RepositoryPushSubscriptions(RepositoryGeneric[PushSubscriptionOut, UserPushSubscription]):
    """Push subscriptions of every user. They're keyed by endpoint, which is unique to one install on one device."""

    def get_by_endpoint(self, endpoint: str) -> UserPushSubscription | None:
        query = select(UserPushSubscription).where(UserPushSubscription.endpoint == endpoint)
        return self.session.execute(query).scalar_one_or_none()

    def save(self, data: PushSubscriptionSave) -> PushSubscriptionOut:
        """Add the subscription, or take it over: a device signed in as someone else now belongs to this user"""
        existing = self.get_by_endpoint(data.endpoint)
        if existing is None:
            return self.create(data)
        try:
            existing.user_id = data.user_id
            existing.p256dh = data.p256dh
            existing.auth = data.auth
            existing.user_agent = data.user_agent
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return self.schema.model_validate(existing)

    def remove(self, endpoint: str, user_id: UUID4 | None = None) -> bool:
        statement = delete(UserPushSubscription).where(UserPushSubscription.endpoint == endpoint)
        if user_id is not None:
            statement = statement.where(UserPushSubscription.user_id == user_id)
        try:
            result = self.session.execute(statement)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return bool(getattr(result, "rowcount", 0))

    def for_user(self, user_id: UUID4) -> list[PushSubscriptionOut]:
        query = select(UserPushSubscription).where(UserPushSubscription.user_id == user_id)
        return [self.schema.model_validate(model) for model in self.session.execute(query).scalars()]

    def for_household(self, household_id: UUID4, exclude_user_id: UUID4 | None = None) -> list[PushSubscriptionOut]:
        """Subscriptions of everyone now in the household, found through users so moving households counts"""
        query = (
            select(UserPushSubscription)
            .join(User, User.id == UserPushSubscription.user_id)
            .where(User.household_id == household_id)
        )
        if exclude_user_id is not None:
            query = query.where(UserPushSubscription.user_id != exclude_user_id)
        return [self.schema.model_validate(model) for model in self.session.execute(query).scalars()]
