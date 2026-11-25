import asyncio
from decimal import Decimal
from typing import AsyncGenerator, List, Optional
import strawberry
import strawberry_django
from django.db import models
from strawberry_django.optimizer import DjangoOptimizerExtension

from .models import (
    Addon,
    Category,
    Ingredient,
    Order,
    Product,
    ProductRecipe,
    Shift,
    StockMovement,
)
from .services import (
    InventoryService,
    OrderError,
    OrderEventBroadcaster,
    OrderService,
    PosError,
    ShiftError,
    ShiftService,
)
from .types import (
    AddonType,
    CategoryType,
    IngredientType,
    OrderFilterInput,
    OrderInput,
    OrderType,
    ProductRecipeType,
    ProductType,
    ShiftSummaryType,
    ShiftType,
    StockMovementType,
)


@strawberry.type
class Query:
    # --- Danh mục & Món ---
    @strawberry_django.field
    def categories(self) -> List[CategoryType]:
        return Category.objects.all()

    @strawberry_django.field
    def category(self, id: int) -> Optional[CategoryType]:
        return Category.objects.filter(id=id).first()

    @strawberry_django.field
    def products(
        self,
        category_id: Optional[int] = None,
        is_available: Optional[bool] = None,
    ) -> List[ProductType]:
        qs = Product.objects.all()
        if category_id is not None:
            qs = qs.filter(category_id=category_id)
        if is_available is not None:
            qs = qs.filter(is_available=is_available)
        return qs

    @strawberry_django.field
    def product(self, id: int) -> Optional[ProductType]:
        return Product.objects.filter(id=id).select_related("category").first()

    @strawberry_django.field
    def addons(self, is_available: Optional[bool] = None) -> List[AddonType]:
        qs = Addon.objects.all()
        if is_available is not None:
            qs = qs.filter(is_available=is_available)
        return qs

    # --- Kho nguyên liệu ---
    @strawberry_django.field
    def ingredients(self, low_stock_only: Optional[bool] = False) -> List[IngredientType]:
        qs = Ingredient.objects.all()
        if low_stock_only:
            # Lọc các nguyên liệu có tồn kho <= ngưỡng báo
            qs = qs.filter(current_quantity__lte=models.F("reorder_level"))
        return qs

    @strawberry_django.field
    def ingredient(self, id: int) -> Optional[IngredientType]:
        return Ingredient.objects.filter(id=id).first()

    @strawberry_django.field
    def stock_movements(
        self,
        ingredient_id: Optional[int] = None,
        movement_type: Optional[str] = None,
        order_code: Optional[str] = None,
    ) -> List[StockMovementType]:
        qs = StockMovement.objects.select_related("ingredient", "order")
        if ingredient_id is not None:
            qs = qs.filter(ingredient_id=ingredient_id)
        if movement_type:
            qs = qs.filter(movement_type=movement_type)
        if order_code:
            qs = qs.filter(order__order_code=order_code)
        return qs

    # --- Ca làm việc ---
    @strawberry_django.field
    def shifts(self, status: Optional[str] = None) -> List[ShiftType]:
        qs = Shift.objects.all()
        if status:
            qs = qs.filter(status=status)
        return qs

    @strawberry_django.field
    def active_shift(self) -> Optional[ShiftType]:
        return ShiftService.get_active_shift()

    @strawberry.field
    def shift_summary(self, shift_id: Optional[int] = None) -> ShiftSummaryType:
        if shift_id is None:
            active = ShiftService.get_active_shift()
            if not active:
                raise ShiftError("Hiện tại không có ca nào đang mở.")
            target_id = active.id
        else:
            target_id = shift_id

        summary = ShiftService.get_shift_summary(target_id)
        return ShiftSummaryType(**summary)

    # --- Đơn hàng ---
    @strawberry_django.field
    def orders(self, filter: Optional[OrderFilterInput] = None) -> List[OrderType]:
        qs = Order.objects.all().order_by("-created_at")
        if filter:
            if filter.order_code:
                qs = qs.filter(order_code__icontains=filter.order_code)
            if filter.status:
                qs = qs.filter(status=filter.status)
            if filter.table_number:
                qs = qs.filter(table_number__icontains=filter.table_number)
            if filter.payment_method:
                qs = qs.filter(payment_method=filter.payment_method)
            if filter.shift_id:
                qs = qs.filter(shift_id=filter.shift_id)
            if filter.is_takeaway is not None:
                qs = qs.filter(is_takeaway=filter.is_takeaway)
        return qs

    @strawberry_django.field
    def order(
        self, order_code: Optional[str] = None, id: Optional[int] = None
    ) -> Optional[OrderType]:
        qs = Order.objects.all()
        if id:
            return qs.filter(id=id).first()
        if order_code:
            return qs.filter(order_code=order_code).first()
        return None


@strawberry.type
class Mutation:
    # --- Thực đơn & Công thức ---
    @strawberry.mutation
    def create_category(self, name: str, description: Optional[str] = "") -> CategoryType:
        category, created = Category.objects.get_or_create(
            name=name.strip(),
            defaults={"description": description or ""},
        )
        return category

    @strawberry.mutation
    def create_product(
        self,
        category_id: int,
        name: str,
        base_price: Decimal,
        description: Optional[str] = "",
        is_available: bool = True,
    ) -> ProductType:
        try:
            category = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            raise PosError(f"Không tìm thấy danh mục ID #{category_id}.")

        product = Product.objects.create(
            category=category,
            name=name.strip(),
            base_price=base_price,
            description=description or "",
            is_available=is_available,
        )
        return product

    @strawberry.mutation
    def update_product(
        self,
        id: int,
        name: Optional[str] = None,
        base_price: Optional[Decimal] = None,
        description: Optional[str] = None,
        is_available: Optional[bool] = None,
    ) -> ProductType:
        try:
            product = Product.objects.get(id=id)
        except Product.DoesNotExist:
            raise PosError(f"Không tìm thấy món ID #{id}.")

        if name is not None:
            product.name = name.strip()
        if base_price is not None:
            product.base_price = base_price
        if description is not None:
            product.description = description.strip()
        if is_available is not None:
            product.is_available = is_available
        product.save()
        return product

    @strawberry.mutation
    def create_addon(
        self,
        name: str,
        extra_price: Decimal = Decimal("0.00"),
        is_available: bool = True,
    ) -> AddonType:
        addon = Addon.objects.create(
            name=name.strip(),
            extra_price=extra_price,
            is_available=is_available,
        )
        return addon

    @strawberry.mutation
    def add_recipe_item(
        self,
        product_id: int,
        ingredient_id: int,
        quantity_needed: Decimal,
    ) -> ProductRecipeType:
        """Gán định mức tiêu hao nguyên liệu cho 1 đơn vị món"""
        if quantity_needed <= Decimal("0.000"):
            raise PosError("Định mức tiêu hao phải lớn hơn 0.")

        try:
            product = Product.objects.get(id=product_id)
        except Product.DoesNotExist:
            raise PosError(f"Không tìm thấy món ID #{product_id}.")

        try:
            ingredient = Ingredient.objects.get(id=ingredient_id)
        except Ingredient.DoesNotExist:
            raise PosError(f"Không tìm thấy nguyên liệu ID #{ingredient_id}.")

        recipe, created = ProductRecipe.objects.update_or_create(
            product=product,
            ingredient=ingredient,
            defaults={"quantity_needed": quantity_needed},
        )
        return recipe

    # --- Kho nguyên liệu ---
    @strawberry.mutation
    def create_ingredient(
        self,
        name: str,
        current_quantity: Decimal = Decimal("0.000"),
        unit: str = "g",
        reorder_level: Decimal = Decimal("10.000"),
    ) -> IngredientType:
        ingredient = Ingredient.objects.create(
            name=name.strip(),
            current_quantity=current_quantity,
            unit=unit.strip(),
            reorder_level=reorder_level,
        )
        return ingredient

    @strawberry.mutation
    def restock_ingredient(
        self,
        ingredient_id: int,
        quantity_added: Decimal,
        reference_code: Optional[str] = "",
        notes: Optional[str] = "",
    ) -> IngredientType:
        """Nhập hàng vào kho và ghi nhật ký IMPORT"""
        return InventoryService.restock_ingredient(
            ingredient_id=ingredient_id,
            quantity_added=quantity_added,
            reference_code=reference_code or "",
            notes=notes or "",
        )

    # --- Ca làm việc & Két tiền ---
    @strawberry.mutation
    def open_shift(
        self,
        cashier_name: str,
        opening_cash: Decimal,
        notes: Optional[str] = "",
    ) -> ShiftType:
        """Mở ca làm việc mới"""
        return ShiftService.open_shift(
            cashier_name=cashier_name,
            opening_cash=opening_cash,
            notes=notes or "",
        )

    @strawberry.mutation
    def close_shift(
        self,
        shift_id: Optional[int] = None,
        closing_cash: Decimal = Decimal("0.00"),
        notes: Optional[str] = "",
    ) -> ShiftType:
        """Chốt ca làm việc và đối soát tiền thực tế vs dự kiến"""
        return ShiftService.close_shift(
            shift_id=shift_id,
            closing_cash=closing_cash,
            notes=notes or "",
        )

    # --- Đơn hàng & Điều phối ---
    @strawberry.mutation
    def create_order(self, input: OrderInput) -> OrderType:
        """
        Tạo đơn hàng mới:
        - Kiểm tra ca mở
        - Snapshot giá món và topping
        - Trừ kho tự động theo định mức
        - Đẩy dữ liệu qua WebSocket
        """
        items_payload = []
        for itm in input.items:
            items_payload.append({
                "product_id": itm.product_id,
                "quantity": itm.quantity,
                "notes": itm.notes or "",
                "addon_ids": itm.addon_ids or [],
            })

        order = OrderService.create_order(
            items_data=items_payload,
            table_number=input.table_number or "",
            is_takeaway=input.is_takeaway or False,
            payment_method=input.payment_method or Order.PAYMENT_CASH,
            discount_amount=input.discount_amount or Decimal("0.00"),
            note=input.note or "",
        )
        return order

    @strawberry.mutation
    def update_order_status(
        self,
        order_id: int,
        new_status: str,
        note: Optional[str] = "",
    ) -> OrderType:
        """
        Cập nhật trạng thái đơn (PENDING -> PREPARING -> READY -> COMPLETED / CANCELLED).
        Nếu chuyển sang CANCELLED, tự động hoàn kho.
        """
        return OrderService.update_order_status(
            order_id=order_id,
            new_status=new_status,
            note=note or "",
        )


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def order_events(self) -> AsyncGenerator[OrderType, None]:
        """
        Subscription đẩy sự kiện đơn hàng thời gian thực tới màn hình quầy pha chế / thu ngân
        mỗi khi có đơn mới tạo hoặc đổi trạng thái.
        """
        queue: asyncio.Queue = asyncio.Queue()
        OrderEventBroadcaster.register_queue(queue)
        try:
            while True:
                order = await queue.get()
                yield order
        finally:
            OrderEventBroadcaster.unregister_queue(queue)


# Khởi tạo Strawberry Schema kết hợp DjangoOptimizerExtension
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    subscription=Subscription,
    extensions=[DjangoOptimizerExtension],
)
