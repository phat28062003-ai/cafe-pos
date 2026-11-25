import asyncio
from decimal import Decimal
from django.test import TestCase, TransactionTestCase
from pos.models import (
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
from pos.schema import schema
from asgiref.sync import sync_to_async
from pos.services import (
    InventoryError,
    InventoryService,
    OrderError,
    OrderEventBroadcaster,
    OrderService,
    ShiftError,
    ShiftService,
)


class ShiftServiceTests(TestCase):
    def test_open_and_close_shift(self):
        # 1. Mở ca hợp lệ
        shift = ShiftService.open_shift(
            cashier_name="Nguyễn Văn A",
            opening_cash=Decimal("1000000.00"),
            notes="Ca sáng 6h-14h",
        )
        self.assertEqual(shift.status, Shift.STATUS_OPEN)
        self.assertEqual(shift.opening_cash, Decimal("1000000.00"))

        # 2. Ngăn mở chồng ca
        with self.assertRaises(ShiftError):
            ShiftService.open_shift(
                cashier_name="Trần Thị B",
                opening_cash=Decimal("500000.00"),
            )

        # 3. Chốt ca và tính toán đối soát tiền
        closed_shift = ShiftService.close_shift(
            shift_id=shift.id,
            closing_cash=Decimal("1500000.00"),
            notes="Đếm tiền két cuối ca",
        )
        self.assertEqual(closed_shift.status, Shift.STATUS_CLOSED)
        self.assertIsNotNone(closed_shift.closed_at)
        self.assertEqual(closed_shift.closing_cash, Decimal("1500000.00"))


class InventoryAndRecipeTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Cà phê")
        self.product = Product.objects.create(
            category=self.category,
            name="Cà phê sữa đá",
            base_price=Decimal("35000.00"),
        )
        self.coffee_bean = Ingredient.objects.create(
            name="Hạt cà phê Robusta",
            current_quantity=Decimal("1000.000"),  # 1000g
            unit="g",
            reorder_level=Decimal("200.000"),
        )
        self.condensed_milk = Ingredient.objects.create(
            name="Sữa đặc",
            current_quantity=Decimal("500.000"),  # 500ml
            unit="ml",
            reorder_level=Decimal("100.000"),
        )
        # 1 ly tốn 25g cà phê và 30ml sữa
        ProductRecipe.objects.create(
            product=self.product,
            ingredient=self.coffee_bean,
            quantity_needed=Decimal("25.000"),
        )
        ProductRecipe.objects.create(
            product=self.product,
            ingredient=self.condensed_milk,
            quantity_needed=Decimal("30.000"),
        )

    def test_ingredient_low_stock_property(self):
        self.assertFalse(self.coffee_bean.is_low_stock)
        self.coffee_bean.current_quantity = Decimal("150.000")
        self.coffee_bean.save()
        self.assertTrue(self.coffee_bean.is_low_stock)

    def test_restock_ingredient(self):
        restocked = InventoryService.restock_ingredient(
            ingredient_id=self.coffee_bean.id,
            quantity_added=Decimal("500.000"),
            reference_code="PO-2026-001",
            notes="Nhập hạt Buôn Ma Thuột",
        )
        self.assertEqual(restocked.current_quantity, Decimal("1500.000"))
        # Kiểm tra nhật ký biến động
        movement = StockMovement.objects.filter(
            ingredient=self.coffee_bean, movement_type=StockMovement.TYPE_IMPORT
        ).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.quantity_changed, Decimal("500.000"))
        self.assertEqual(movement.reference_code, "PO-2026-001")


class OrderProcessingAndInventoryDeductionTests(TestCase):
    def setUp(self):
        self.shift = ShiftService.open_shift(
            cashier_name="Thu ngân 1",
            opening_cash=Decimal("500000.00"),
        )
        self.category = Category.objects.create(name="Trà & Cà phê")
        self.product = Product.objects.create(
            category=self.category,
            name="Bạc xỉu",
            base_price=Decimal("40000.00"),
        )
        self.addon_foam = Addon.objects.create(
            name="Kem Cheese",
            extra_price=Decimal("10000.00"),
        )
        self.coffee = Ingredient.objects.create(
            name="Cốt cà phê",
            current_quantity=Decimal("100.000"),
            unit="ml",
            reorder_level=Decimal("20.000"),
        )
        # Công thức: 1 ly bạc xỉu cần 30ml cốt cà phê
        ProductRecipe.objects.create(
            product=self.product,
            ingredient=self.coffee,
            quantity_needed=Decimal("30.000"),
        )

    def test_create_order_auto_deducts_stock(self):
        # Đặt 2 ly bạc xỉu -> tiêu tốn 60ml cốt cà phê (100ml - 60ml = 40ml còn lại)
        order = OrderService.create_order(
            items_data=[
                {
                    "product_id": self.product.id,
                    "quantity": 2,
                    "notes": "Ít ngọt nhiều đá",
                    "addon_ids": [self.addon_foam.id],
                }
            ],
            table_number="Bàn 05",
            payment_method=Order.PAYMENT_CASH,
            discount_amount=Decimal("5000.00"),
            note="Khách quen",
        )

        # Kiểm tra đơn hàng
        self.assertTrue(order.order_code.startswith("ORD-"))
        self.assertEqual(order.status, Order.STATUS_PENDING)
        # 2 ly * (40k + 10k) - 5k = 95k
        self.assertEqual(order.total_amount, Decimal("95000.00"))

        # Kiểm tra tồn kho đã bị trừ đúng 60ml
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.current_quantity, Decimal("40.000"))

        # Kiểm tra nhật ký StockMovement
        deduct_mov = StockMovement.objects.get(
            order=order, movement_type=StockMovement.TYPE_ORDER_DEDUCT
        )
        self.assertEqual(deduct_mov.quantity_changed, Decimal("-60.000"))

    def test_insufficient_stock_blocks_order(self):
        # Đặt 4 ly bạc xỉu -> cần 120ml, nhưng kho chỉ có 100ml -> phải chặn và rollback
        with self.assertRaises(InventoryError) as ctx:
            OrderService.create_order(
                items_data=[
                    {
                        "product_id": self.product.id,
                        "quantity": 4,
                    }
                ],
                table_number="Bàn 01",
            )
        self.assertIn("không đủ tồn kho", str(ctx.exception))
        # Đảm bảo kho không suy suyển
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.current_quantity, Decimal("100.000"))
        # Không có đơn hàng nào bị lưu
        self.assertEqual(Order.objects.count(), 0)

    def test_cancel_order_auto_refunds_stock(self):
        # Đặt 2 ly (trừ 60ml, còn 40ml)
        order = OrderService.create_order(
            items_data=[{"product_id": self.product.id, "quantity": 2}],
            table_number="Bàn 02",
        )
        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.current_quantity, Decimal("40.000"))

        # Hủy đơn -> Hoàn lại 60ml -> Tồn kho trở về 100ml
        cancelled_order = OrderService.update_order_status(
            order_id=order.id,
            new_status=Order.STATUS_CANCELLED,
            note="Khách đổi ý không lấy nữa",
        )
        self.assertEqual(cancelled_order.status, Order.STATUS_CANCELLED)

        self.coffee.refresh_from_db()
        self.assertEqual(self.coffee.current_quantity, Decimal("100.000"))

        # Kiểm tra nhật ký ORDER_REFUND
        refund_mov = StockMovement.objects.get(
            order=order, movement_type=StockMovement.TYPE_ORDER_REFUND
        )
        self.assertEqual(refund_mov.quantity_changed, Decimal("60.000"))

    def test_price_snapshot_integrity(self):
        # Đặt đơn khi giá đang là 40k
        order = OrderService.create_order(
            items_data=[{"product_id": self.product.id, "quantity": 1}],
        )
        item = order.items.first()
        self.assertEqual(item.unit_price, Decimal("40000.00"))

        # Đổi giá sản phẩm thành 60k
        self.product.base_price = Decimal("60000.00")
        self.product.save()

        # Kiểm tra giá trên đơn cũ không bị thay đổi!
        item.refresh_from_db()
        self.assertEqual(item.unit_price, Decimal("40000.00"))

    def test_order_status_state_machine(self):
        order = OrderService.create_order(
            items_data=[{"product_id": self.product.id, "quantity": 1}],
        )
        self.assertEqual(order.status, Order.STATUS_PENDING)

        # Chuyển sang PREPARING -> Hợp lệ
        OrderService.update_order_status(order.id, Order.STATUS_PREPARING)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_PREPARING)

        # Chuyển sang READY -> Hợp lệ
        OrderService.update_order_status(order.id, Order.STATUS_READY)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_READY)

        # Chuyển sang COMPLETED -> Hợp lệ
        OrderService.update_order_status(order.id, Order.STATUS_COMPLETED)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.STATUS_COMPLETED)

        # Cố chuyển từ COMPLETED ngược về PREPARING -> Bị chặn
        with self.assertRaises(OrderError):
            OrderService.update_order_status(order.id, Order.STATUS_PREPARING)


class ShiftSummaryTests(TestCase):
    def test_shift_reconciliation_calculations(self):
        shift = ShiftService.open_shift(
            cashier_name="Thu ngân 2",
            opening_cash=Decimal("1000000.00"),
        )
        cat = Category.objects.create(name="Trà")
        prod = Product.objects.create(
            category=cat, name="Trà đào", base_price=Decimal("30000.00")
        )

        # 1 đơn tiền mặt 60k
        OrderService.create_order(
            items_data=[{"product_id": prod.id, "quantity": 2}],
            payment_method=Order.PAYMENT_CASH,
        )

        # 1 đơn chuyển khoản 30k
        OrderService.create_order(
            items_data=[{"product_id": prod.id, "quantity": 1}],
            payment_method=Order.PAYMENT_TRANSFER,
        )

        # 1 đơn hủy (không tính vào doanh thu)
        order_to_cancel = OrderService.create_order(
            items_data=[{"product_id": prod.id, "quantity": 1}],
            payment_method=Order.PAYMENT_CASH,
        )
        OrderService.update_order_status(order_to_cancel.id, Order.STATUS_CANCELLED)

        # Chốt ca với số tiền thực đếm là 1.050.000đ
        # Dự kiến: 1.000.000đ (đầu ca) + 60.000đ (tiền mặt) = 1.060.000đ
        # Chênh lệch: 1.050.000đ - 1.060.000đ = -10.000đ (hụt 10k)
        ShiftService.close_shift(shift_id=shift.id, closing_cash=Decimal("1050000.00"))

        summary = ShiftService.get_shift_summary(shift.id)
        self.assertEqual(summary["cash_sales"], Decimal("60000.00"))
        self.assertEqual(summary["transfer_sales"], Decimal("30000.00"))
        self.assertEqual(summary["total_sales"], Decimal("90000.00"))
        self.assertEqual(summary["expected_cash"], Decimal("1060000.00"))
        self.assertEqual(summary["cash_discrepancy"], Decimal("-10000.00"))
        self.assertEqual(summary["valid_orders_count"], 2)
        self.assertEqual(summary["cancelled_orders_count"], 1)


class GraphQLApiIntegrationTests(TestCase):
    def test_graphql_queries_and_mutations(self):
        # 1. Mutation mở ca qua GraphQL
        mutation_open_shift = """
        mutation {
            openShift(cashierName: "Thu ngân GraphQL", openingCash: "2000000") {
                id
                cashierName
                status
                openingCash
            }
        }
        """
        result = schema.execute_sync(mutation_open_shift)
        self.assertIsNone(result.errors, result.errors)
        shift_data = result.data["openShift"]
        self.assertEqual(shift_data["cashierName"], "Thu ngân GraphQL")
        self.assertEqual(shift_data["status"], "OPEN")

        # 2. Mutation tạo danh mục và món
        mutation_create_cat = """
        mutation {
            createCategory(name: "Trà sữa", description: "Các loại trà sữa trân châu") {
                id
                name
            }
        }
        """
        res_cat = schema.execute_sync(mutation_create_cat)
        cat_id = res_cat.data["createCategory"]["id"]

        mutation_create_prod = f"""
        mutation {{
            createProduct(
                categoryId: {cat_id},
                name: "Trà sữa Ô long",
                basePrice: "45000",
                description: "Vị trà đậm đà"
            ) {{
                id
                name
                basePrice
            }}
        }}
        """
        res_prod = schema.execute_sync(mutation_create_prod)
        self.assertIsNone(res_prod.errors, res_prod.errors)
        prod_id = res_prod.data["createProduct"]["id"]

        # 3. Mutation tạo đơn hàng qua GraphQL
        mutation_create_order = f"""
        mutation {{
            createOrder(input: {{
                items: [
                    {{ productId: {prod_id}, quantity: 2, notes: "50% đường 50% đá" }}
                ],
                tableNumber: "VIP-1",
                paymentMethod: "CASH"
            }}) {{
                id
                orderCode
                totalAmount
                status
                items {{
                    productName
                    quantity
                    subtotal
                    notes
                }}
            }}
        }}
        """
        res_order = schema.execute_sync(mutation_create_order)
        self.assertIsNone(res_order.errors, res_order.errors)
        order_data = res_order.data["createOrder"]
        self.assertEqual(order_data["status"], "PENDING")
        self.assertEqual(order_data["totalAmount"], "90000.00")
        self.assertEqual(len(order_data["items"]), 1)
        self.assertEqual(order_data["items"][0]["notes"], "50% đường 50% đá")

        # 4. Query danh sách đơn có lọc
        query_orders = """
        query {
            orders(filter: { paymentMethod: "CASH" }) {
                orderCode
                totalAmount
                status
            }
        }
        """
        res_query = schema.execute_sync(query_orders)
        self.assertIsNone(res_query.errors, res_query.errors)
        self.assertEqual(len(res_query.data["orders"]), 1)


class OrderSubscriptionTests(TestCase):
    async def test_order_events_subscription(self):
        sub_generator = await schema.subscribe(
            """
            subscription {
                orderEvents {
                    orderCode
                    status
                    totalAmount
                }
            }
            """
        )

        # Khởi chạy generator để register queue vào broadcaster
        listen_task = asyncio.create_task(anext(sub_generator))
        await asyncio.sleep(0.05)

        mock_order = Order(
            id=999,
            order_code="ORD-SUB99",
            status=Order.STATUS_PENDING,
            total_amount=Decimal("50000.00"),
        )
        OrderEventBroadcaster.broadcast(mock_order, event_type="ORDER_CREATED")

        event = await listen_task
        self.assertIsNone(event.errors, event.errors)
        self.assertEqual(event.data["orderEvents"]["orderCode"], "ORD-SUB99")
        self.assertEqual(event.data["orderEvents"]["status"], "PENDING")
        self.assertEqual(event.data["orderEvents"]["totalAmount"], "50000.00")

        await sub_generator.aclose()

