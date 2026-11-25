from datetime import datetime
from decimal import Decimal
from typing import List, Optional
import strawberry
import strawberry_django
from strawberry import auto
from . import models


@strawberry_django.type(models.Category)
class CategoryType:
    id: auto
    name: auto
    description: auto
    created_at: auto
    updated_at: auto
    products: List["ProductType"]


@strawberry_django.type(models.Product)
class ProductType:
    id: auto
    name: auto
    description: auto
    base_price: auto
    is_available: auto
    created_at: auto
    updated_at: auto
    category: CategoryType
    recipes: List["ProductRecipeType"]


@strawberry_django.type(models.Addon)
class AddonType:
    id: auto
    name: auto
    extra_price: auto
    is_available: auto
    created_at: auto
    updated_at: auto


@strawberry_django.type(models.Ingredient)
class IngredientType:
    id: auto
    name: auto
    current_quantity: auto
    unit: auto
    reorder_level: auto
    created_at: auto
    updated_at: auto
    movements: List["StockMovementType"]

    @strawberry.field
    def is_low_stock(self, root: models.Ingredient) -> bool:
        return root.is_low_stock


@strawberry_django.type(models.ProductRecipe)
class ProductRecipeType:
    id: auto
    product: ProductType
    ingredient: IngredientType
    quantity_needed: auto


@strawberry_django.type(models.Shift)
class ShiftType:
    id: auto
    cashier_name: auto
    opening_cash: auto
    closing_cash: auto
    opened_at: auto
    closed_at: auto
    status: auto
    notes: auto
    orders: List["OrderType"]

    @strawberry.field
    def cash_sales(self, root: models.Shift) -> Decimal:
        return root.cash_sales

    @strawberry.field
    def transfer_sales(self, root: models.Shift) -> Decimal:
        return root.transfer_sales

    @strawberry.field
    def total_sales(self, root: models.Shift) -> Decimal:
        return root.total_sales

    @strawberry.field
    def expected_cash(self, root: models.Shift) -> Decimal:
        return root.expected_cash

    @strawberry.field
    def cash_discrepancy(self, root: models.Shift) -> Decimal:
        return root.cash_discrepancy


@strawberry_django.type(models.OrderItemAddon)
class OrderItemAddonType:
    id: auto
    addon: Optional[AddonType]
    addon_name: auto
    extra_price: auto


@strawberry_django.type(models.OrderItem)
class OrderItemType:
    id: auto
    product: Optional[ProductType]
    product_name: auto
    unit_price: auto
    quantity: auto
    subtotal: auto
    notes: auto
    addons: List[OrderItemAddonType]


@strawberry_django.type(models.StockMovement)
class StockMovementType:
    id: auto
    movement_type: auto
    ingredient: IngredientType
    quantity_changed: auto
    quantity_before: auto
    quantity_after: auto
    order: Optional["OrderType"]
    reference_code: auto
    notes: auto
    created_at: auto


@strawberry_django.type(models.Order)
class OrderType:
    id: auto
    order_code: auto
    shift: ShiftType
    table_number: auto
    is_takeaway: auto
    status: auto
    payment_method: auto
    total_amount: auto
    discount_amount: auto
    note: auto
    created_at: auto
    updated_at: auto
    items: List[OrderItemType]
    stock_movements: List[StockMovementType]


@strawberry.type
class ShiftSummaryType:
    shift_id: int
    cashier_name: str
    status: str
    opened_at: datetime
    closed_at: Optional[datetime]
    opening_cash: Decimal
    closing_cash: Optional[Decimal]
    cash_sales: Decimal
    transfer_sales: Decimal
    total_sales: Decimal
    expected_cash: Decimal
    cash_discrepancy: Decimal
    total_orders_count: int
    valid_orders_count: int
    cancelled_orders_count: int


@strawberry.input
class OrderItemInput:
    product_id: int
    quantity: int = 1
    notes: Optional[str] = ""
    addon_ids: Optional[List[int]] = None


@strawberry.input
class OrderInput:
    items: List[OrderItemInput]
    table_number: Optional[str] = ""
    is_takeaway: Optional[bool] = False
    payment_method: Optional[str] = "CASH"
    discount_amount: Optional[Decimal] = Decimal("0.00")
    note: Optional[str] = ""


@strawberry.input
class OrderFilterInput:
    order_code: Optional[str] = None
    status: Optional[str] = None
    table_number: Optional[str] = None
    payment_method: Optional[str] = None
    shift_id: Optional[int] = None
    is_takeaway: Optional[bool] = None
