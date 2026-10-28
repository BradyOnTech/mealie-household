from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import ForeignKey, orm
from sqlalchemy.orm import Mapped, mapped_column

from .._model_base import BaseMixins, SqlAlchemyBase
from .._model_utils.auto_init import auto_init
from .._model_utils.guid import GUID

if TYPE_CHECKING:
    from .group import Group


class CookbookImportRecipeModel(SqlAlchemyBase, BaseMixins):
    """A recipe found in a cookbook, identified by its page and its place among the recipes starting there."""

    __tablename__ = "cookbook_import_recipes"
    __table_args__ = (
        sa.UniqueConstraint("cookbook_import_id", "first_page", "item", name="cookbook_import_recipes_location_key"),
    )

    id: Mapped[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    cookbook_import_id: Mapped[GUID] = mapped_column(
        GUID, ForeignKey("cookbook_imports.id"), nullable=False, index=True
    )
    cookbook_import: Mapped[CookbookImportModel] = orm.relationship("CookbookImportModel", back_populates="recipes")

    name: Mapped[str] = mapped_column(sa.String, nullable=False)
    first_page: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    last_page: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    item: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    @auto_init()
    def __init__(self, **_) -> None:
        pass


class CookbookImportModel(SqlAlchemyBase, BaseMixins):
    """
    The recipes found in a cookbook file the first time it was imported, so importing it again
    picks up the same recipes rather than whatever the AI finds the next time.
    """

    __tablename__ = "cookbook_imports"
    __table_args__ = (sa.UniqueConstraint("group_id", "fingerprint", name="cookbook_imports_group_id_fingerprint_key"),)

    id: Mapped[GUID] = mapped_column(GUID, primary_key=True, default=GUID.generate)
    group_id: Mapped[GUID] = mapped_column(GUID, ForeignKey("groups.id"), nullable=False, index=True)
    group: Mapped[Group] = orm.relationship("Group", back_populates="cookbook_imports")

    fingerprint: Mapped[str] = mapped_column(sa.String, nullable=False, index=True)
    unread_pages: Mapped[str] = mapped_column(sa.String, nullable=False, default="")
    """Pages the AI couldn't look through for recipes, comma separated, to look through again next time"""

    recipes: Mapped[list[CookbookImportRecipeModel]] = orm.relationship(
        CookbookImportRecipeModel, back_populates="cookbook_import", cascade="all, delete-orphan"
    )

    @auto_init()
    def __init__(self, **_) -> None:
        pass
