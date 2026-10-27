"""
Keys the grocery features keep in the `extras` of shopping lists and their items. They're stored with the data,
and the frontend and backups read them as they are, so a rename needs a data migration.

This module imports nothing, so repositories and services can both use it.
"""

SOURCE = "shop.source"
"""Why an item is on the list: "week" (recipes and staples), "manual" (added by hand), or "restock" (Out of)"""
STORE_OVERRIDE = "shop.store_override"
PRODUCT_OVERRIDE = "shop.product_override"
PURCHASED_AMOUNT = "shop.purchased_amount"
PURCHASED_UNIT = "shop.purchased_unit"
RESTOCK_ID = "shop.restock_id"
"""The Out of item a list row stands in for"""
SATISFIED = "shop.satisfied"
"""Set on a wanted item while a list is generated, when the pantry already covers it"""
WEEK = "shop.week"
"""Marks a shopping list as a grocery week's list, with the week it's for; nothing reads it, it's for people"""
