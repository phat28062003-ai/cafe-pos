"""
Script khởi tạo dữ liệu mẫu thực tế cho Cafe POS (seed_data.py)
Bao gồm:
- Danh mục sản phẩm (Category)
- Sản phẩm đồ uống & bánh (Product)
- Topping / Tùy chọn cộng thêm (Addon)
- Nguyên liệu kho & ngưỡng cảnh báo tồn (Ingredient)
- Định mức công thức pha chế (ProductRecipe)
- Ca làm việc khởi đầu (Shift)
- Một số đơn hàng mẫu với các trạng thái khác nhau (Order, OrderItem, OrderItemAddon)
- Nhật ký biến động kho tương ứng (StockMovement)
"""

import os
import django
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cafe_pos.settings")
django.setup()

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
from pos.services import InventoryService, OrderService, ShiftService


def run_seed():
    print("=== BẮT ĐẦU KHỞI TẠO DỮ LIỆU MẪU CHO CAFE POS ===")

    # 1. Danh mục sản phẩm
    cat_coffee, _ = Category.objects.get_or_create(
        name="Cà phê truyền thống",
        defaults={"description": "Cà phê pha phin và pha máy từ hạt Robusta & Arabica nguyên chất"},
    )
    cat_tea, _ = Category.objects.get_or_create(
        name="Trà trái cây & Trà sữa",
        defaults={"description": "Trà ủ lạnh, trà sữa Ô long và các loại trà thanh nhiệt"},
    )
    cat_bakery, _ = Category.objects.get_or_create(
        name="Bánh ngọt & Ăn kèm",
        defaults={"description": "Bánh tươi nướng trong ngày phục vụ kèm đồ uống"},
    )
    print(f"-> Đã tạo {Category.objects.count()} danh mục.")

    # 2. Topping & Tùy chọn (Addon)
    addons_data = [
        ("Thêm shot Espresso", Decimal("15000.00")),
        ("Kem Cheese béo ngậy", Decimal("12000.00")),
        ("Trân châu đường đen", Decimal("10000.00")),
        ("Thạch đào giòn", Decimal("10000.00")),
        ("Size Lớn (L)", Decimal("8000.00")),
    ]
    addon_objs = {}
    for name, price in addons_data:
        obj, _ = Addon.objects.get_or_create(
            name=name,
            defaults={"extra_price": price, "is_available": True},
        )
        addon_objs[name] = obj
    print(f"-> Đã tạo {Addon.objects.count()} loại topping.")

    # 3. Nguyên liệu kho (Ingredient)
    ingredients_data = [
        ("Hạt Robusta Buôn Ma Thuột", Decimal("5000.000"), "g", Decimal("1000.000")),
        ("Hạt Arabica Cầu Đất", Decimal("3000.000"), "g", Decimal("800.000")),
        ("Sữa đặc Phương Nam", Decimal("4000.000"), "ml", Decimal("1000.000")),
        ("Sữa tươi thanh trùng", Decimal("6000.000"), "ml", Decimal("1500.000")),
        ("Trà Ô long thượng hạng", Decimal("2000.000"), "g", Decimal("500.000")),
        ("Đào ngâm giòn", Decimal("1500.000"), "g", Decimal("400.000")),
        ("Bột Cheese cao cấp", Decimal("1000.000"), "g", Decimal("300.000")),
        ("Bột Matcha Nhật Bản", Decimal("200.000"), "g", Decimal("500.000")),  # Thử nghiệm low stock
    ]
    ing_objs = {}
    for name, qty, unit, reorder in ingredients_data:
        obj, _ = Ingredient.objects.get_or_create(
            name=name,
            defaults={"current_quantity": qty, "unit": unit, "reorder_level": reorder},
        )
        ing_objs[name] = obj
    print(f"-> Đã tạo {Ingredient.objects.count()} nguyên liệu kho.")

    # 4. Món (Product)
    products_data = [
        (cat_coffee, "Cà phê sữa đá Sài Gòn", Decimal("32000.00"), "Cà phê phin truyền thống đậm vị kết hợp sữa đặc"),
        (cat_coffee, "Bạc xỉu ba tầng", Decimal("38000.00"), "Cà phê sữa nhẹ nhàng, ngọt dịu phù hợp mọi người"),
        (cat_coffee, "Americano đá", Decimal("35000.00"), "Espresso từ hạt Arabica Cầu Đất thơm nhẹ"),
        (cat_tea, "Trà đào cam sả", Decimal("45000.00"), "Trà thảo mộc thơm cam vàng và sả tươi, kèm đào miếng"),
        (cat_tea, "Trà sữa Ô long nướng", Decimal("42000.00"), "Vị trà đậm, sữa thanh ngậy"),
        (cat_bakery, "Bánh Croissant bơ Pháp", Decimal("35000.00"), "Bánh sừng bò ngàn lớp thơm lừng bơ Pháp"),
    ]
    prod_objs = {}
    for cat, name, price, desc in products_data:
        obj, _ = Product.objects.get_or_create(
            name=name,
            defaults={"category": cat, "base_price": price, "description": desc, "is_available": True},
        )
        prod_objs[name] = obj
    print(f"-> Đã tạo {Product.objects.count()} món.")

    # 5. Định mức công thức pha chế (ProductRecipe)
    recipes_data = [
        # Cà phê sữa đá: 25g Robusta, 30ml Sữa đặc
        (prod_objs["Cà phê sữa đá Sài Gòn"], ing_objs["Hạt Robusta Buôn Ma Thuột"], Decimal("25.000")),
        (prod_objs["Cà phê sữa đá Sài Gòn"], ing_objs["Sữa đặc Phương Nam"], Decimal("30.000")),
        # Bạc xỉu: 15g Robusta, 40ml Sữa đặc, 60ml Sữa tươi
        (prod_objs["Bạc xỉu ba tầng"], ing_objs["Hạt Robusta Buôn Ma Thuột"], Decimal("15.000")),
        (prod_objs["Bạc xỉu ba tầng"], ing_objs["Sữa đặc Phương Nam"], Decimal("40.000")),
        (prod_objs["Bạc xỉu ba tầng"], ing_objs["Sữa tươi thanh trùng"], Decimal("60.000")),
        # Americano: 20g Arabica
        (prod_objs["Americano đá"], ing_objs["Hạt Arabica Cầu Đất"], Decimal("20.000")),
        # Trà đào: 15g Trà Ô long, 60g Đào ngâm
        (prod_objs["Trà đào cam sả"], ing_objs["Trà Ô long thượng hạng"], Decimal("15.000")),
        (prod_objs["Trà đào cam sả"], ing_objs["Đào ngâm giòn"], Decimal("60.000")),
        # Trà sữa Ô long: 20g Trà Ô long, 80ml Sữa tươi, 20ml Sữa đặc
        (prod_objs["Trà sữa Ô long nướng"], ing_objs["Trà Ô long thượng hạng"], Decimal("20.000")),
        (prod_objs["Trà sữa Ô long nướng"], ing_objs["Sữa tươi thanh trùng"], Decimal("80.000")),
        (prod_objs["Trà sữa Ô long nướng"], ing_objs["Sữa đặc Phương Nam"], Decimal("20.000")),
    ]
    for prod, ing, qty_needed in recipes_data:
        ProductRecipe.objects.get_or_create(
            product=prod,
            ingredient=ing,
            defaults={"quantity_needed": qty_needed},
        )
    print(f"-> Đã thiết lập {ProductRecipe.objects.count()} định mức công thức pha chế.")

    # 6. Mở ca làm việc mẫu (Shift)
    active_shift = ShiftService.get_active_shift()
    if not active_shift:
        active_shift = ShiftService.open_shift(
            cashier_name="Lê Minh Trí (Thu ngân ca sáng)",
            opening_cash=Decimal("1500000.00"),
            notes="Ca sáng bắt đầu 07:00, kiểm tra két đầy đủ tiền lẻ.",
        )
        print(f"-> Đã mở ca làm việc mới: #{active_shift.id} - {active_shift.cashier_name}")
    else:
        print(f"-> Sử dụng ca làm việc đang mở: #{active_shift.id}")

    # 7. Tạo một số đơn hàng mẫu
    if Order.objects.count() == 0:
        # Đơn 1: Tiền mặt, 2 ly cà phê sữa đá + kem cheese, bàn số 3
        order1 = OrderService.create_order(
            items_data=[
                {
                    "product_id": prod_objs["Cà phê sữa đá Sài Gòn"].id,
                    "quantity": 2,
                    "notes": "Nhiều đá, ít ngọt",
                    "addon_ids": [addon_objs["Kem Cheese béo ngậy"].id],
                }
            ],
            table_number="Bàn 03",
            payment_method=Order.PAYMENT_CASH,
            discount_amount=Decimal("0.00"),
            note="Khách tại bàn 3",
        )
        OrderService.update_order_status(order1.id, Order.STATUS_PREPARING)
        OrderService.update_order_status(order1.id, Order.STATUS_READY)
        OrderService.update_order_status(order1.id, Order.STATUS_COMPLETED)

        # Đơn 2: Chuyển khoản, 1 Trà đào cam sả + Thạch đào, mang đi
        order2 = OrderService.create_order(
            items_data=[
                {
                    "product_id": prod_objs["Trà đào cam sả"].id,
                    "quantity": 1,
                    "notes": "70% ngọt, lấy thêm ống hút to",
                    "addon_ids": [addon_objs["Thạch đào giòn"].id],
                }
            ],
            is_takeaway=True,
            payment_method=Order.PAYMENT_TRANSFER,
            discount_amount=Decimal("5000.00"),
            note="Mang đi gấp",
        )
        OrderService.update_order_status(order2.id, Order.STATUS_PREPARING)

        # Đơn 3: Chờ pha chế (PENDING)
        order3 = OrderService.create_order(
            items_data=[
                {
                    "product_id": prod_objs["Bạc xỉu ba tầng"].id,
                    "quantity": 1,
                    "notes": "Nóng",
                    "addon_ids": [],
                },
                {
                    "product_id": prod_objs["Bánh Croissant bơ Pháp"].id,
                    "quantity": 1,
                    "notes": "Hâm nóng bánh giòn",
                    "addon_ids": [],
                },
            ],
            table_number="Bàn 08",
            payment_method=Order.PAYMENT_CASH,
            note="Bàn đôi ban công",
        )

        print(f"-> Đã tạo 3 đơn hàng mẫu: {order1.order_code}, {order2.order_code}, {order3.order_code}.")

    print("=== KHỞI TẠO DỮ LIỆU HOÀN TẤT THÀNH CÔNG! ===")


if __name__ == "__main__":
    run_seed()
