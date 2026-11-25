import asyncio
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, AsyncGenerator, Dict, List, Optional, Set
from django.db import transaction
from django.utils import timezone
from .models import (
    Addon,
    Category,
    Ingredient,
    Order,
    OrderItem,
    OrderItemAddon,
    Product,
    ProductRecipe,
    Shift,
    StockMovement,
)


class PosError(Exception):
    """Base exception cho nghiệp vụ POS"""
    pass


class ShiftError(PosError):
    """Lỗi liên quan đến ca làm việc và két tiền"""
    pass


class InventoryError(PosError):
    """Lỗi liên quan đến tồn kho và định mức nguyên liệu"""
    pass


class OrderError(PosError):
    """Lỗi liên quan đến đơn hàng và điều phối trạng thái"""
    pass


class OrderEventBroadcaster:
    """
    Bộ phát sự kiện thời gian thực (Real-time Event Broadcaster)
    Được thiết kế để kết nối giữa Django Mutation (Sync/Async) và Strawberry GraphQL Subscription (Async).
    """
    _queues: Set[asyncio.Queue] = set()

    @classmethod
    def register_queue(cls, queue: asyncio.Queue) -> None:
        cls._queues.add(queue)

    @classmethod
    def unregister_queue(cls, queue: asyncio.Queue) -> None:
        cls._queues.discard(queue)

    @classmethod
    def broadcast(cls, order: Order, event_type: str = "ORDER_UPDATED") -> None:
        """Đẩy order tới tất cả subscriber đang lắng nghe qua WebSocket"""
        dead_queues = set()
        for q in list(cls._queues):
            try:
                # Nếu có running event loop ở thread này
                try:
                    loop = asyncio.get_running_loop()
                    loop.call_soon_threadsafe(q.put_nowait, order)
                except RuntimeError:
                    # Nếu chạy trong sync thread không có running loop
                    q.put_nowait(order)
            except Exception:
                dead_queues.add(q)
        for dq in dead_queues:
            cls.unregister_queue(dq)


class ShiftService:
    @staticmethod
    def get_active_shift() -> Optional[Shift]:
        """Lấy ca làm việc đang mở gần nhất"""
        return Shift.objects.filter(status=Shift.STATUS_OPEN).first()

    @staticmethod
    @transaction.atomic
    def open_shift(cashier_name: str, opening_cash: Decimal, notes: str = "") -> Shift:
        """
        Mở ca làm việc mới:
        - Kiểm tra và ngăn mở chồng ca nếu đang có ca OPEN.
        - Khóa bảng kiểm tra để chống race condition.
        """
        active_shift = Shift.objects.select_for_update().filter(status=Shift.STATUS_OPEN).first()
        if active_shift:
            raise ShiftError(
                f"Ca làm việc #{active_shift.id} của thu ngân '{active_shift.cashier_name}' vẫn đang mở. "
                "Vui lòng chốt ca hiện tại trước khi mở ca mới."
            )

        if opening_cash < Decimal("0.00"):
            raise ShiftError("Tiền mặt đầu ca không được là số âm.")

        shift = Shift.objects.create(
            cashier_name=cashier_name.strip() or "Thu ngân",
            opening_cash=opening_cash,
            status=Shift.STATUS_OPEN,
            notes=notes.strip(),
        )
        return shift

    @staticmethod
    @transaction.atomic
    def close_shift(
        shift_id: Optional[int] = None,
        closing_cash: Decimal = Decimal("0.00"),
        notes: str = "",
    ) -> Shift:
        """
        Chốt ca làm việc và đối soát két tiền:
        - Tách doanh thu tiền mặt và chuyển khoản.
        - Tính tiền dự kiến và mức chênh lệch.
        """
        if shift_id:
            try:
                shift = Shift.objects.select_for_update().get(id=shift_id)
            except Shift.DoesNotExist:
                raise ShiftError(f"Không tìm thấy ca làm việc với ID #{shift_id}.")
        else:
            shift = Shift.objects.select_for_update().filter(status=Shift.STATUS_OPEN).first()
            if not shift:
                raise ShiftError("Hiện tại không có ca làm việc nào đang mở để chốt.")

        if shift.status == Shift.STATUS_CLOSED:
            raise ShiftError(f"Ca làm việc #{shift.id} đã được chốt trước đó vào lúc {shift.closed_at}.")

        if closing_cash < Decimal("0.00"):
            raise ShiftError("Tiền mặt thực đếm khi chốt ca không được là số âm.")

        shift.closing_cash = closing_cash
        shift.closed_at = timezone.now()
        shift.status = Shift.STATUS_CLOSED
        if notes:
            shift.notes = f"{shift.notes}\nChốt ca: {notes}".strip()
        shift.save()
        return shift

    @staticmethod
    def get_shift_summary(shift_id: int) -> Dict[str, Any]:
        """Báo cáo đối soát chi tiết của ca làm việc"""
        try:
            shift = Shift.objects.get(id=shift_id)
        except Shift.DoesNotExist:
            raise ShiftError(f"Không tìm thấy ca #{shift_id}.")

        orders = shift.orders.all()
        completed_orders = orders.exclude(status=Order.STATUS_CANCELLED)
        cancelled_orders = orders.filter(status=Order.STATUS_CANCELLED)

        return {
            "shift_id": shift.id,
            "cashier_name": shift.cashier_name,
            "status": shift.status,
            "opened_at": shift.opened_at,
            "closed_at": shift.closed_at,
            "opening_cash": shift.opening_cash,
            "closing_cash": shift.closing_cash,
            "cash_sales": shift.cash_sales,
            "transfer_sales": shift.transfer_sales,
            "total_sales": shift.total_sales,
            "expected_cash": shift.expected_cash,
            "cash_discrepancy": shift.cash_discrepancy,
            "total_orders_count": orders.count(),
            "valid_orders_count": completed_orders.count(),
            "cancelled_orders_count": cancelled_orders.count(),
        }


class InventoryService:
    @staticmethod
    @transaction.atomic
    def restock_ingredient(
        ingredient_id: int,
        quantity_added: Decimal,
        reference_code: str = "",
        notes: str = "",
    ) -> Ingredient:
        """
        Nhập thêm nguyên liệu vào kho (IMPORT):
        - Dùng select_for_update() để khóa dòng nguyên liệu.
        - Ghi nhật ký StockMovement để đối soát.
        """
        if quantity_added <= Decimal("0.000"):
            raise InventoryError("Số lượng nhập kho phải lớn hơn 0.")

        try:
            ingredient = Ingredient.objects.select_for_update().get(id=ingredient_id)
        except Ingredient.DoesNotExist:
            raise InventoryError(f"Không tìm thấy nguyên liệu với ID #{ingredient_id}.")

        before = ingredient.current_quantity
        after = before + quantity_added
        ingredient.current_quantity = after
        ingredient.save(update_fields=["current_quantity", "updated_at"])

        StockMovement.objects.create(
            movement_type=StockMovement.TYPE_IMPORT,
            ingredient=ingredient,
            quantity_changed=quantity_added,
            quantity_before=before,
            quantity_after=after,
            reference_code=reference_code or f"RESTOCK-{timezone.now():%Y%m%d%H%M%S}",
            notes=notes or f"Nhập kho thêm {quantity_added}{ingredient.unit} {ingredient.name}",
        )
        return ingredient

    @staticmethod
    def calculate_required_stock(items_specs: List[Dict[str, Any]]) -> Dict[int, Decimal]:
        """
        Tính toán tổng lượng nguyên liệu cần thiết cho danh sách món đặt dựa trên định mức công thức (ProductRecipe)
        items_specs: list of {'product_id': int, 'quantity': int}
        """
        product_quantities: Dict[int, int] = {}
        for item in items_specs:
            pid = item["product_id"]
            product_quantities[pid] = product_quantities.get(pid, 0) + item.get("quantity", 1)

        recipes = ProductRecipe.objects.filter(product_id__in=product_quantities.keys())
        required_stock: Dict[int, Decimal] = {}
        for recipe in recipes:
            qty_needed_per_cup = recipe.quantity_needed
            total_cups = product_quantities[recipe.product_id]
            total_needed = qty_needed_per_cup * Decimal(total_cups)
            required_stock[recipe.ingredient_id] = (
                required_stock.get(recipe.ingredient_id, Decimal("0.000")) + total_needed
            )
        return required_stock

    @staticmethod
    @transaction.atomic
    def deduct_stock_for_order(order: Order, items_specs: List[Dict[str, Any]]) -> None:
        """
        Tự động trừ kho theo công thức pha chế:
        - Tính tổng lượng nguyên liệu cần.
        - Khóa dòng nguyên liệu bằng select_for_update() theo thứ tự ID để chống deadlock.
        - Kiểm tra tồn kho, nếu thiếu lập tức chặn và báo lỗi chi tiết.
        - Ghi log StockMovement với movement_type=ORDER_DEDUCT.
        """
        required_stock = InventoryService.calculate_required_stock(items_specs)
        if not required_stock:
            return  # Không có nguyên liệu nào cần trừ (món không khai báo công thức)

        # Khóa nguyên liệu theo thứ tự id tăng dần để tránh deadlock giữa các giao dịch song song
        sorted_ingredient_ids = sorted(required_stock.keys())
        locked_ingredients = {
            ing.id: ing
            for ing in Ingredient.objects.select_for_update()
            .filter(id__in=sorted_ingredient_ids)
            .order_by("id")
        }

        # 1. Kiểm tra toàn bộ tồn kho trước khi trừ
        insufficient_errors = []
        for ing_id, needed_qty in required_stock.items():
            ing = locked_ingredients.get(ing_id)
            if not ing:
                insufficient_errors.append(f"Nguyên liệu ID #{ing_id} không tồn tại.")
                continue
            if ing.current_quantity < needed_qty:
                insufficient_errors.append(
                    f"Nguyên liệu '{ing.name}' không đủ tồn kho (cần {needed_qty:g}{ing.unit}, hiện có {ing.current_quantity:g}{ing.unit})."
                )

        if insufficient_errors:
            raise InventoryError(" | ".join(insufficient_errors))

        # 2. Thực hiện trừ kho và ghi nhận nhật ký
        for ing_id, needed_qty in required_stock.items():
            ing = locked_ingredients[ing_id]
            before = ing.current_quantity
            after = before - needed_qty
            ing.current_quantity = after
            ing.save(update_fields=["current_quantity", "updated_at"])

            StockMovement.objects.create(
                movement_type=StockMovement.TYPE_ORDER_DEDUCT,
                ingredient=ing,
                quantity_changed=-needed_qty,
                quantity_before=before,
                quantity_after=after,
                order=order,
                reference_code=order.order_code,
                notes=f"Trừ kho tự động cho đơn hàng {order.order_code}",
            )

    @staticmethod
    @transaction.atomic
    def refund_stock_for_order(order: Order) -> None:
        """
        Tự động hoàn kho khi đơn hàng bị hủy:
        - Quét các biến động ORDER_DEDUCT trước đó của đơn.
        - Chống hoàn kho lặp (nếu đã có ORDER_REFUND thì bỏ qua).
        - Cộng lại đúng lượng nguyên liệu đã trừ, ghi log ORDER_REFUND.
        """
        # Kiểm tra xem đã hoàn kho cho đơn này chưa
        already_refunded = StockMovement.objects.filter(
            order=order, movement_type=StockMovement.TYPE_ORDER_REFUND
        ).exists()
        if already_refunded:
            return

        deductions = StockMovement.objects.filter(
            order=order, movement_type=StockMovement.TYPE_ORDER_DEDUCT
        )
        if not deductions.exists():
            return

        # Khóa các nguyên liệu liên quan theo thứ tự ID
        ingredient_ids = sorted(list(set(d.ingredient_id for d in deductions)))
        locked_ingredients = {
            ing.id: ing
            for ing in Ingredient.objects.select_for_update()
            .filter(id__in=ingredient_ids)
            .order_by("id")
        }

        for deduction in deductions:
            ing = locked_ingredients[deduction.ingredient_id]
            refund_qty = abs(deduction.quantity_changed)
            before = ing.current_quantity
            after = before + refund_qty
            ing.current_quantity = after
            ing.save(update_fields=["current_quantity", "updated_at"])

            StockMovement.objects.create(
                movement_type=StockMovement.TYPE_ORDER_REFUND,
                ingredient=ing,
                quantity_changed=refund_qty,
                quantity_before=before,
                quantity_after=after,
                order=order,
                reference_code=order.order_code,
                notes=f"Hoàn kho do hủy đơn hàng {order.order_code}",
            )


class OrderService:
    VALID_STATUS_TRANSITIONS = {
        Order.STATUS_PENDING: [Order.STATUS_PREPARING, Order.STATUS_CANCELLED],
        Order.STATUS_PREPARING: [Order.STATUS_READY, Order.STATUS_CANCELLED],
        Order.STATUS_READY: [Order.STATUS_COMPLETED, Order.STATUS_CANCELLED],
        Order.STATUS_COMPLETED: [],  # Trạng thái cuối, không thể đổi
        Order.STATUS_CANCELLED: [],  # Trạng thái cuối, không thể đổi
    }

    @staticmethod
    @transaction.atomic
    def create_order(
        items_data: List[Dict[str, Any]],
        table_number: str = "",
        is_takeaway: bool = False,
        payment_method: str = Order.PAYMENT_CASH,
        discount_amount: Decimal = Decimal("0.00"),
        note: str = "",
    ) -> Order:
        """
        Tạo đơn hàng mới:
        - Bắt buộc phải có ca làm việc đang mở (Shift).
        - Kiểm tra tính hợp lệ và trạng thái còn bán của món & topping.
        - Chốt cứng đơn giá gốc của món và topping tại thời điểm đặt.
        - Tự động trừ kho theo định mức công thức pha chế.
        - Phát sự kiện thời gian thực tới subscriber.
        """
        # 1. Kiểm tra ca làm việc
        active_shift = ShiftService.get_active_shift()
        if not active_shift:
            raise OrderError(
                "Không thể tạo đơn hàng khi chưa mở ca làm việc. Vui lòng mở ca trước."
            )

        if not items_data:
            raise OrderError("Đơn hàng phải có ít nhất 1 món.")

        if discount_amount < Decimal("0.00"):
            raise OrderError("Số tiền giảm giá không được là số âm.")

        # 2. Chuẩn bị thông tin các dòng món và snapshot giá
        items_specs_for_inventory = []
        prepared_items = []
        total_subtotal = Decimal("0.00")

        # Lấy danh sách Product và Addon từ DB
        product_ids = [item["product_id"] for item in items_data]
        products_map = {
            p.id: p for p in Product.objects.filter(id__in=product_ids)
        }

        all_addon_ids = []
        for item in items_data:
            all_addon_ids.extend(item.get("addon_ids", []))
        addons_map = {
            a.id: a for a in Addon.objects.filter(id__in=all_addon_ids)
        }

        for item_data in items_data:
            pid = item_data["product_id"]
            qty = int(item_data.get("quantity", 1))
            item_notes = item_data.get("notes", "").strip()
            addon_ids = item_data.get("addon_ids", [])

            if qty <= 0:
                raise OrderError("Số lượng từng món phải lớn hơn 0.")

            product = products_map.get(pid)
            if not product:
                raise OrderError(f"Món với ID #{pid} không tồn tại.")
            if not product.is_available:
                raise OrderError(f"Món '{product.name}' hiện đang tạm ngừng bán.")

            # Snapshot giá món
            product_unit_price = product.base_price
            unit_total = product_unit_price

            prepared_addons = []
            for aid in addon_ids:
                addon = addons_map.get(aid)
                if not addon:
                    raise OrderError(f"Topping với ID #{aid} không tồn tại.")
                if not addon.is_available:
                    raise OrderError(f"Topping '{addon.name}' hiện đang tạm hết.")
                unit_total += addon.extra_price
                prepared_addons.append({
                    "addon": addon,
                    "addon_name": addon.name,
                    "extra_price": addon.extra_price,
                })

            item_subtotal = unit_total * Decimal(qty)
            total_subtotal += item_subtotal

            prepared_items.append({
                "product": product,
                "product_name": product.name,
                "unit_price": product_unit_price,
                "quantity": qty,
                "subtotal": item_subtotal,
                "notes": item_notes,
                "addons": prepared_addons,
            })

            items_specs_for_inventory.append({
                "product_id": product.id,
                "quantity": qty,
            })

        final_total = total_subtotal - discount_amount
        if final_total < Decimal("0.00"):
            final_total = Decimal("0.00")

        # 3. Tạo đơn hàng
        order = Order.objects.create(
            order_code=Order.generate_order_code(),
            shift=active_shift,
            table_number=table_number.strip(),
            is_takeaway=is_takeaway,
            status=Order.STATUS_PENDING,
            payment_method=payment_method,
            total_amount=final_total,
            discount_amount=discount_amount,
            note=note.strip(),
        )

        # 4. Lưu chi tiết dòng món và topping đã snapshot
        for p_item in prepared_items:
            order_item = OrderItem.objects.create(
                order=order,
                product=p_item["product"],
                product_name=p_item["product_name"],
                unit_price=p_item["unit_price"],
                quantity=p_item["quantity"],
                subtotal=p_item["subtotal"],
                notes=p_item["notes"],
            )
            for p_addon in p_item["addons"]:
                OrderItemAddon.objects.create(
                    order_item=order_item,
                    addon=p_addon["addon"],
                    addon_name=p_addon["addon_name"],
                    extra_price=p_addon["extra_price"],
                )

        # 5. Tự động trừ kho theo công thức pha chế (nếu thiếu kho sẽ ném InventoryError và rollback toàn bộ)
        InventoryService.deduct_stock_for_order(order, items_specs_for_inventory)

        # 6. Phát sự kiện real-time
        OrderEventBroadcaster.broadcast(order, event_type="ORDER_CREATED")

        return order

    @staticmethod
    @transaction.atomic
    def update_order_status(order_id: int, new_status: str, note: str = "") -> Order:
        """
        Điều phối trạng thái đơn hàng theo vòng đời:
        - Quản lý luồng trạng thái (PENDING -> PREPARING -> READY -> COMPLETED, hoặc CANCELLED).
        - Khóa dòng đơn hàng select_for_update() để đảm bảo tính toàn vẹn khi nhiều bên cùng thao tác.
        - Chặn chuyển sai quy tắc (COMPLETED / CANCELLED là trạng thái cuối không thể đổi ngược lại).
        - Nếu chuyển sang CANCELLED: tự động hoàn lại đúng nguyên liệu đã trừ kho.
        - Phát sự kiện thời gian thực.
        """
        try:
            order = Order.objects.select_for_update().get(id=order_id)
        except Order.DoesNotExist:
            raise OrderError(f"Không tìm thấy đơn hàng với ID #{order_id}.")

        current_status = order.status
        valid_next_statuses = OrderService.VALID_STATUS_TRANSITIONS.get(current_status, [])

        if current_status in [Order.STATUS_COMPLETED, Order.STATUS_CANCELLED]:
            raise OrderError(
                f"Đơn hàng {order.order_code} đã ở trạng thái '{order.get_status_display()}', không thể thay đổi thêm."
            )

        if new_status not in valid_next_statuses:
            raise OrderError(
                f"Quy trình không hợp lệ: Không thể chuyển từ trạng thái '{order.get_status_display()}' "
                f"sang '{new_status}'."
            )

        # Nếu hủy đơn -> Hoàn lại nguyên liệu kho
        if new_status == Order.STATUS_CANCELLED:
            InventoryService.refund_stock_for_order(order)

        order.status = new_status
        if note.strip():
            order.note = f"{order.note}\nCập nhật trạng thái: {note.strip()}".strip()
        order.save(update_fields=["status", "note", "updated_at"])

        # Phát sự kiện real-time
        OrderEventBroadcaster.broadcast(order, event_type="ORDER_STATUS_UPDATED")

        return order
