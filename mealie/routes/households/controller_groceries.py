from datetime import date
from functools import cached_property
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import UUID4
from starlette.responses import FileResponse

from mealie.routes._base.base_controllers import BaseCrudController
from mealie.routes._base.controller import controller
from mealie.schema.grocery.grocery import (
    GroceryCommonItemList,
    GroceryFoodRuleCreate,
    GroceryFoodRuleOut,
    GroceryItemAssignment,
    GroceryItemCheck,
    GroceryItemDelete,
    GroceryManualItemCreate,
    GroceryProductCreate,
    GroceryProductLookup,
    GroceryProductLookupRequest,
    GroceryProductOut,
    GroceryRestockBought,
    GroceryRestockCreate,
    GroceryRestockList,
    GrocerySuggestionOut,
    GroceryWeekGenerate,
    GroceryWeekView,
)
from mealie.schema.response.responses import SuccessResponse
from mealie.services.event_bus_service.event_types import EventOperation, EventShoppingListData, EventTypes
from mealie.services.household_services.groceries import GroceryService
from mealie.services.household_services.grocery_product_links import GroceryProductReader

router = APIRouter(prefix="/households/groceries", tags=["Households: Groceries"])


@controller(router)
class GroceryController(BaseCrudController):
    @router.get("/source", response_class=FileResponse, response_model=None)
    def source(self) -> FileResponse:
        source = Path(__file__).resolve().parents[2] / "household-source.zip"
        if not source.is_file():
            raise HTTPException(404, "Source archive is not built. See HOUSEHOLD_GROCERIES.md for the build command.")
        return FileResponse(source, media_type="application/zip", filename="mealie-household-source.zip")

    @cached_property
    def service(self) -> GroceryService:
        return GroceryService(self.repos, self.user.id)

    def publish_week(self, view: GroceryWeekView) -> GroceryWeekView:
        if view.shopping_list:
            shopping_list = view.shopping_list
            self.publish_event(
                EventTypes.shopping_list_updated,
                document_data=EventShoppingListData(operation=EventOperation.update, shopping_list_id=shopping_list.id),
                group_id=shopping_list.group_id,
                household_id=shopping_list.household_id,
            )
        return view

    def publish_restock(self, result: GroceryRestockList) -> GroceryRestockList:
        """Out of items live on the newest list, so that's the list a change to them touches"""
        week = self.repos.grocery_weeks.get_by_date(result.next_list_week) if result.next_list_week else None
        if week:
            self.publish_event(
                EventTypes.shopping_list_updated,
                document_data=EventShoppingListData(
                    operation=EventOperation.update, shopping_list_id=week.shopping_list_id
                ),
                group_id=week.group_id,
                household_id=week.household_id,
            )
        return result

    @router.get("/common-items", response_model=GroceryCommonItemList)
    def common_items(self) -> GroceryCommonItemList:
        return self.service.common_items()

    @router.get("/restock", response_model=GroceryRestockList)
    def restock(self) -> GroceryRestockList:
        return self.service.restock_list()

    @router.post("/restock", response_model=GroceryRestockList, status_code=201)
    def add_restock(self, data: GroceryRestockCreate) -> GroceryRestockList:
        self.service.add_restock(data, added_by=self.user.full_name or self.user.username or "")
        return self.publish_restock(self.service.restock_list())

    @router.put("/restock/{item_id}", response_model=GroceryRestockList)
    def update_restock(self, item_id: UUID4, data: GroceryRestockCreate) -> GroceryRestockList:
        self.service.update_restock(item_id, data)
        return self.publish_restock(self.service.restock_list())

    @router.delete("/restock/{item_id}", response_model=GroceryRestockList)
    def remove_restock(self, item_id: UUID4) -> GroceryRestockList:
        self.service.remove_restock(item_id)
        return self.publish_restock(self.service.restock_list())

    @router.put("/restock/{item_id}/bought", response_model=GroceryRestockList)
    def restock_bought(self, item_id: UUID4, data: GroceryRestockBought) -> GroceryRestockList:
        self.service.set_restock_bought(item_id, data.bought)
        return self.publish_restock(self.service.restock_list())

    @router.get("/products", response_model=list[GroceryProductOut])
    def products(self) -> list[GroceryProductOut]:
        return self.repos.grocery_products.get_all(order_by="priority", order_descending=False)

    @router.post("/products", response_model=GroceryProductOut, status_code=201)
    def create_product(self, data: GroceryProductCreate) -> GroceryProductOut:
        return self.service.save_product(data)

    @router.post("/products/lookup", response_model=GroceryProductLookup)
    async def lookup_product(self, data: GroceryProductLookupRequest) -> GroceryProductLookup:
        """Reads a product's store link into a draft product: its name, store, package size and ingredient"""
        return await GroceryProductReader(self.repos).read(data.url)

    @router.put("/products/{product_id}", response_model=GroceryProductOut)
    def update_product(self, product_id: UUID4, data: GroceryProductCreate) -> GroceryProductOut:
        return self.service.save_product(data, product_id)

    @router.delete("/products/{product_id}", response_model=SuccessResponse)
    def delete_product(self, product_id: UUID4) -> SuccessResponse:
        if self.repos.grocery_products.get_one(product_id) is None:
            raise HTTPException(404, "Product not found")
        self.repos.grocery_products.delete(product_id)
        return SuccessResponse.model_validate(SuccessResponse.respond())

    @router.get("/rules", response_model=list[GroceryFoodRuleOut])
    def rules(self) -> list[GroceryFoodRuleOut]:
        return self.repos.grocery_food_rules.get_all()

    @router.post("/rules", response_model=GroceryFoodRuleOut, status_code=201)
    def create_rule(self, data: GroceryFoodRuleCreate) -> GroceryFoodRuleOut:
        return self.service.save_rule(data)

    @router.put("/rules/{rule_id}", response_model=GroceryFoodRuleOut)
    def update_rule(self, rule_id: UUID4, data: GroceryFoodRuleCreate) -> GroceryFoodRuleOut:
        return self.service.save_rule(data, rule_id)

    @router.delete("/rules/{rule_id}", response_model=SuccessResponse)
    def delete_rule(self, rule_id: UUID4) -> SuccessResponse:
        if self.repos.grocery_food_rules.get_one(rule_id) is None:
            raise HTTPException(404, "Rule not found")
        self.repos.grocery_food_rules.delete(rule_id)
        return SuccessResponse.model_validate(SuccessResponse.respond())

    @router.get("/suggestions", response_model=list[GrocerySuggestionOut])
    def suggestions(self, plan_date: date, limit: int = Query(default=5, ge=1, le=20)) -> list[GrocerySuggestionOut]:
        return self.service.suggestions(plan_date, limit)

    @router.get("/weeks/{week_start}", response_model=GroceryWeekView)
    def get_week(self, week_start: date) -> GroceryWeekView:
        return self.service.view(week_start)

    @router.put("/weeks/{week_start}", response_model=GroceryWeekView)
    def generate_week(self, week_start: date, data: GroceryWeekGenerate) -> GroceryWeekView:
        return self.publish_week(self.service.generate(week_start, data))

    @router.put("/weeks/{week_start}/assignment", response_model=GroceryWeekView)
    def assign_items(self, week_start: date, data: GroceryItemAssignment) -> GroceryWeekView:
        return self.publish_week(self.service.assign(week_start, data))

    @router.put("/weeks/{week_start}/checked", response_model=GroceryWeekView)
    def check_items(self, week_start: date, data: GroceryItemCheck) -> GroceryWeekView:
        return self.publish_week(self.service.check(week_start, data))

    @router.post("/weeks/{week_start}/items", response_model=GroceryWeekView, status_code=201)
    def add_item(self, week_start: date, data: GroceryManualItemCreate) -> GroceryWeekView:
        return self.publish_week(self.service.add_manual(week_start, data))

    @router.post("/weeks/{week_start}/items/delete", response_model=GroceryWeekView)
    def delete_items(self, week_start: date, data: GroceryItemDelete) -> GroceryWeekView:
        return self.publish_week(self.service.delete_manual(week_start, data))
