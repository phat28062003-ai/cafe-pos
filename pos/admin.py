from django.contrib import admin
from .models import (
    Category,
    Product,
    Addon,
    Ingredient,
    ProductRecipe,
    Shift,
    Order,
    OrderItem,
    OrderItemAddon,
    StockMovement,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "created_at"]
    search_fields = ["name"]


class ProductRecipeInline(admin.TabularInline):
    model = ProductRecipe
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "category", "base_price", "is_available", "updated_at"]
    list_filter = ["category", "is_available"]
    search_fields = ["name"]
    inlines = [ProductRecipeInline]


@admin.register(Addon)
class AddonAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "extra_price", "is_available"]
    list_filter = ["is_available"]
    search_fields = ["name"]


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "current_quantity", "unit", "reorder_level", "is_low_stock"]
    search_fields = ["name"]


class OrderItemAddonInline(admin.TabularInline):
    model = OrderItemAddon
    extra = 0


class OrderItemInline(admin.StackedInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = [
        "order_code",
        "shift",
        "table_number",
        "is_takeaway",
        "status",
        "payment_method",
        "total_amount",
        "created_at",
    ]
    list_filter = ["status", "payment_method", "is_takeaway"]
    search_fields = ["order_code", "table_number"]
    inlines = [OrderItemInline]


@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "cashier_name",
        "status",
        "opening_cash",
        "closing_cash",
        "total_sales",
        "cash_discrepancy",
        "opened_at",
        "closed_at",
    ]
    list_filter = ["status"]
    search_fields = ["cashier_name"]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "movement_type",
        "ingredient",
        "quantity_changed",
        "quantity_before",
        "quantity_after",
        "order",
        "reference_code",
        "created_at",
    ]
    list_filter = ["movement_type"]
    search_fields = ["ingredient__name", "reference_code"]
