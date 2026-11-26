"""
Script nạp toàn bộ thực đơn đa dạng & phong phú cho Cafe POS (seed_data.py)
Bao gồm:
- 4 Danh mục chuyên nghiệp
- 18 Món đồ uống & bánh ngọt hot-trend
- 7 Topping cộng thêm
- 12 Loại nguyên liệu kho định mức đầy đủ
- 25+ Định mức công thức pha chế chi tiết
- 1 Ca làm việc sẵn sàng hoạt động
"""

import os
import django
from decimal import Decimal

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cafe_pos.settings")
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
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
    print("=== BẮT ĐẦU NẠP THỰC ĐƠN ĐẦY ĐỦ CHO CAFE POS PRO ===")

    # 1. Danh mục sản phẩm (Categories)
    categories_data = [
        ("Cà phê truyền thống & Hiện đại", "Cà phê phin Robusta đậm đà và các dòng pha máy Ý thơm lừng"),
        ("Trà trái cây tươi & Thanh nhiệt", "Trà ủ lạnh trái cây nhiệt đới, đào, cam sả, dâu tằm, ổi hồng"),
        ("Trà sữa & Cacao Macchiato", "Trà sữa Ô long nướng, trà lài sữa, Matcha Kyoto và cacao đậm vị"),
        ("Bánh ngọt & Đồ ăn kèm", "Bánh tươi nướng nóng giòn và các món ăn vặt thư giãn cùng đồ uống"),
    ]
    category_objs = {}
    for name, desc in categories_data:
        cat, _ = Category.objects.get_or_create(name=name, defaults={"description": desc})
        category_objs[name] = cat
    print(f"-> Đã chuẩn bị {Category.objects.count()} danh mục.")

    # 2. Topping & Tùy chọn (Addons)
    addons_data = [
        ("Thêm shot Espresso đậm", Decimal("15000.00")),
        ("Kem Cheese béo ngậy", Decimal("12000.00")),
        ("Trân châu đường đen", Decimal("10000.00")),
        ("Trân châu hoàng kim", Decimal("10000.00")),
        ("Thạch đào giòn sần sật", Decimal("10000.00")),
        ("Thạch nha đam thanh mát", Decimal("8000.00")),
        ("Nâng cấp Size Lớn (L)", Decimal("8000.00")),
    ]
    addon_objs = {}
    for name, price in addons_data:
        obj, _ = Addon.objects.get_or_create(
            name=name,
            defaults={"extra_price": price, "is_available": True},
        )
        addon_objs[name] = obj
    print(f"-> Đã chuẩn bị {Addon.objects.count()} loại topping.")

    # 3. Nguyên liệu kho (Ingredients)
    ingredients_data = [
        ("Hạt Robusta Buôn Ma Thuột", Decimal("10000.000"), "g", Decimal("1000.000")),
        ("Hạt Arabica Cầu Đất", Decimal("8000.000"), "g", Decimal("800.000")),
        ("Sữa đặc Phương Nam", Decimal("10000.000"), "ml", Decimal("1500.000")),
        ("Sữa tươi thanh trùng", Decimal("15000.000"), "ml", Decimal("2000.000")),
        ("Trà Ô long thượng hạng", Decimal("5000.000"), "g", Decimal("800.000")),
        ("Trà hoa lài thanh hương", Decimal("4000.000"), "g", Decimal("600.000")),
        ("Đào ngâm giòn", Decimal("5000.000"), "g", Decimal("800.000")),
        ("Sốt dâu tằm tươi", Decimal("3000.000"), "ml", Decimal("500.000")),
        ("Sốt ổi hồng nhiệt đới", Decimal("3000.000"), "ml", Decimal("500.000")),
        ("Bột Matcha Kyoto", Decimal("2000.000"), "g", Decimal("400.000")),
        ("Bột Cacao nguyên chất", Decimal("3000.000"), "g", Decimal("500.000")),
        ("Bột Cheese cao cấp", Decimal("4000.000"), "g", Decimal("500.000")),
    ]
    ing_objs = {}
    for name, qty, unit, reorder in ingredients_data:
        obj, created = Ingredient.objects.get_or_create(
            name=name,
            defaults={"current_quantity": qty, "unit": unit, "reorder_level": reorder},
        )
        # Đảm bảo kho luôn có lượng tồn dồi dào
        if obj.current_quantity < Decimal("1000.000"):
            obj.current_quantity = qty
            obj.save()
        ing_objs[name] = obj
    print(f"-> Đã chuẩn bị {Ingredient.objects.count()} nguyên liệu kho.")

    # 4. Món đồ uống & bánh ngọt (Products)
    cat_coffee = category_objs["Cà phê truyền thống & Hiện đại"]
    cat_fruit = category_objs["Trà trái cây tươi & Thanh nhiệt"]
    cat_milk = category_objs["Trà sữa & Cacao Macchiato"]
    cat_bakery = category_objs["Bánh ngọt & Đồ ăn kèm"]

    products_data = [
        # Nhóm Cà phê
        (cat_coffee, "Cà phê sữa đá Sài Gòn", Decimal("32000.00"), "Cà phê phin truyền thống đậm vị kết hợp sữa đặc béo ngậy"),
        (cat_coffee, "Cà phê đen đá Buôn Mê", Decimal("28000.00"), "Cà phê đen nguyên chất sánh đậm, hương thơm ngào ngạt"),
        (cat_coffee, "Bạc xỉu ba tầng", Decimal("38000.00"), "Hòa quyện tinh tế giữa sữa tươi thanh trùng, sữa đặc và cốt cà phê"),
        (cat_coffee, "Cà phê Muối xứ Huế", Decimal("38000.00"), "Vị đắng thơm của Robusta kết hợp lớp kem mặn béo mịn màng"),
        (cat_coffee, "Americano đá", Decimal("35000.00"), "Espresso từ hạt Arabica Cầu Đất dịu nhẹ, thanh mát sảng khoái"),
        (cat_coffee, "Latte bọt sữa nghệ thuật", Decimal("45000.00"), "Cà phê sữa tươi kiểu Ý với lớp bọt microfoam mềm mại"),

        # Nhóm Trà trái cây
        (cat_fruit, "Trà đào cam sả tươi", Decimal("45000.00"), "Trà Ô long thảo mộc thơm sả và cam vàng, kèm 3 miếng đào giòn ngọt"),
        (cat_fruit, "Trà dâu tằm tuyết lựu", Decimal("45000.00"), "Chua ngọt tự nhiên từ trái dâu tằm rừng và trà ủ lạnh"),
        (cat_fruit, "Trà ổi hồng chanh leo", Decimal("42000.00"), "Hương thơm quyến rũ từ ổi hồng nhiệt đới hòa quyện cốt chanh leo tươi"),
        (cat_fruit, "Trà lài vải hoa hồng", Decimal("45000.00"), "Trà lài thanh mát kết hợp trái vải mọng nước và cánh hồng thơm ngát"),

        # Nhóm Trà sữa & Cacao
        (cat_milk, "Trà sữa Ô long nướng", Decimal("42000.00"), "Cốt trà Ô long sao nướng đậm vị, béo ngậy sữa bột nhập khẩu"),
        (cat_milk, "Trà lài sữa kem cheese", Decimal("48000.00"), "Hương lài thơm ngát kết hợp lớp váng phô mai béo ngậy muối hồng"),
        (cat_milk, "Matcha Latte Kyoto", Decimal("50000.00"), "Bột trà xanh Nhật Bản nguyên bản kết hợp sữa tươi thanh trùng béo ngậy"),
        (cat_milk, "Cacao đá kem Marshmallow", Decimal("42000.00"), "Cacao nguyên chất đậm đà phủ kẹo dẻo marshmallow nướng"),

        # Nhóm Bánh & Ăn kèm
        (cat_bakery, "Bánh Croissant bơ Pháp", Decimal("35000.00"), "Bánh sừng bò ngàn lớp nướng nóng giòn, thơm nức bơ Pháp"),
        (cat_bakery, "Bánh Tiramisu Ý", Decimal("45000.00"), "Bánh kem phô mai Mascarpone đượm vị rượu Rum và cốt cà phê espresso"),
        (cat_bakery, "Bánh Basque Burnt Cheesecake", Decimal("48000.00"), "Bánh phô mai nướng cháy xém phong cách Tây Ban Nha, lõi chảy béo ngậy"),
        (cat_bakery, "Khô bò miếng vắt chanh", Decimal("45000.00"), "Món nhắm ăn vặt đậm đà gia vị kèm đồ uống mát lạnh"),
    ]

    prod_objs = {}
    for cat, name, price, desc in products_data:
        obj, _ = Product.objects.update_or_create(
            name=name,
            defaults={"category": cat, "base_price": price, "description": desc, "is_available": True},
        )
        prod_objs[name] = obj
    print(f"-> Đã nạp thành công {Product.objects.count()} món đồ uống và bánh ngọt.")

    # 5. Gán định mức công thức pha chế (ProductRecipe)
    recipes_specs = [
        # Cà phê sữa đá: 25g Robusta, 30ml Sữa đặc
        ("Cà phê sữa đá Sài Gòn", "Hạt Robusta Buôn Ma Thuột", Decimal("25.000")),
        ("Cà phê sữa đá Sài Gòn", "Sữa đặc Phương Nam", Decimal("30.000")),

        # Cà phê đen đá: 30g Robusta
        ("Cà phê đen đá Buôn Mê", "Hạt Robusta Buôn Ma Thuột", Decimal("30.000")),

        # Bạc xỉu: 15g Robusta, 40ml Sữa đặc, 60ml Sữa tươi
        ("Bạc xỉu ba tầng", "Hạt Robusta Buôn Ma Thuột", Decimal("15.000")),
        ("Bạc xỉu ba tầng", "Sữa đặc Phương Nam", Decimal("40.000")),
        ("Bạc xỉu ba tầng", "Sữa tươi thanh trùng", Decimal("60.000")),

        # Cà phê muối: 25g Robusta, 20ml Sữa đặc, 30g Bột Cheese
        ("Cà phê Muối xứ Huế", "Hạt Robusta Buôn Ma Thuột", Decimal("25.000")),
        ("Cà phê Muối xứ Huế", "Sữa đặc Phương Nam", Decimal("20.000")),
        ("Cà phê Muối xứ Huế", "Bột Cheese cao cấp", Decimal("30.000")),

        # Americano: 20g Arabica
        ("Americano đá", "Hạt Arabica Cầu Đất", Decimal("20.000")),

        # Latte: 20g Arabica, 120ml Sữa tươi
        ("Latte bọt sữa nghệ thuật", "Hạt Arabica Cầu Đất", Decimal("20.000")),
        ("Latte bọt sữa nghệ thuật", "Sữa tươi thanh trùng", Decimal("120.000")),

        # Trà đào: 15g Ô long, 60g Đào ngâm
        ("Trà đào cam sả tươi", "Trà Ô long thượng hạng", Decimal("15.000")),
        ("Trà đào cam sả tươi", "Đào ngâm giòn", Decimal("60.000")),

        # Trà dâu tằm: 15g Ô long, 40ml Sốt dâu tằm
        ("Trà dâu tằm tuyết lựu", "Trà Ô long thượng hạng", Decimal("15.000")),
        ("Trà dâu tằm tuyết lựu", "Sốt dâu tằm tươi", Decimal("40.000")),

        # Trà ổi hồng: 15g Lài, 40ml Sốt ổi hồng
        ("Trà ổi hồng chanh leo", "Trà hoa lài thanh hương", Decimal("15.000")),
        ("Trà ổi hồng chanh leo", "Sốt ổi hồng nhiệt đới", Decimal("40.000")),

        # Trà lài vải: 15g Lài
        ("Trà lài vải hoa hồng", "Trà hoa lài thanh hương", Decimal("15.000")),

        # Trà sữa Ô long: 20g Ô long, 60ml Sữa tươi, 25ml Sữa đặc
        ("Trà sữa Ô long nướng", "Trà Ô long thượng hạng", Decimal("20.000")),
        ("Trà sữa Ô long nướng", "Sữa tươi thanh trùng", Decimal("60.000")),
        ("Trà sữa Ô long nướng", "Sữa đặc Phương Nam", Decimal("25.000")),

        # Trà lài sữa kem cheese: 15g Lài, 50ml Sữa tươi, 30g Bột Cheese
        ("Trà lài sữa kem cheese", "Trà hoa lài thanh hương", Decimal("15.000")),
        ("Trà lài sữa kem cheese", "Sữa tươi thanh trùng", Decimal("50.000")),
        ("Trà lài sữa kem cheese", "Bột Cheese cao cấp", Decimal("30.000")),

        # Matcha Latte: 20g Bột Matcha, 120ml Sữa tươi, 20ml Sữa đặc
        ("Matcha Latte Kyoto", "Bột Matcha Kyoto", Decimal("20.000")),
        ("Matcha Latte Kyoto", "Sữa tươi thanh trùng", Decimal("120.000")),
        ("Matcha Latte Kyoto", "Sữa đặc Phương Nam", Decimal("20.000")),

        # Cacao đá: 25g Bột Cacao, 80ml Sữa tươi, 30ml Sữa đặc
        ("Cacao đá kem Marshmallow", "Bột Cacao nguyên chất", Decimal("25.000")),
        ("Cacao đá kem Marshmallow", "Sữa tươi thanh trùng", Decimal("80.000")),
        ("Cacao đá kem Marshmallow", "Sữa đặc Phương Nam", Decimal("30.000")),
    ]

    for prod_name, ing_name, qty in recipes_specs:
        if prod_name in prod_objs and ing_name in ing_objs:
            ProductRecipe.objects.update_or_create(
                product=prod_objs[prod_name],
                ingredient=ing_objs[ing_name],
                defaults={"quantity_needed": qty},
            )
    print(f"-> Đã thiết lập xong {ProductRecipe.objects.count()} định mức công thức pha chế.")

    # 6. Mở ca làm việc (Shift)
    active_shift = ShiftService.get_active_shift()
    if not active_shift:
        active_shift = ShiftService.open_shift(
            cashier_name="Lê Minh Trí (Thu ngân ca chính)",
            opening_cash=Decimal("1500000.00"),
            notes="Ca làm việc sẵn sàng tiếp nhận khách hàng.",
        )
        print(f"-> Đã mở ca làm việc: #{active_shift.id} - {active_shift.cashier_name}")
    else:
        print(f"-> Ca làm việc #{active_shift.id} của {active_shift.cashier_name} đang hoạt động.")

    print("=== NẠP TOÀN BỘ THỰC ĐƠN HOÀN TẤT THÀNH CÔNG! ===")


if __name__ == "__main__":
    run_seed()
