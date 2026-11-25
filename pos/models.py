import uuid
from decimal import Decimal
from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Tên danh mục")
    description = models.TextField(blank=True, default="", verbose_name="Mô tả")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời gian cập nhật")

    class Meta:
        verbose_name = "Danh mục"
        verbose_name_plural = "Danh mục"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="products", verbose_name="Danh mục"
    )
    name = models.CharField(max_length=150, verbose_name="Tên món")
    description = models.TextField(blank=True, default="", verbose_name="Mô tả")
    base_price = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Giá gốc"
    )
    is_available = models.BooleanField(default=True, verbose_name="Còn bán")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời gian cập nhật")

    class Meta:
        verbose_name = "Món"
        verbose_name_plural = "Món"
        ordering = ["category", "name"]

    def __str__(self):
        return f"{self.name} ({self.base_price:,.0f}đ)"


class Addon(models.Model):
    name = models.CharField(max_length=100, verbose_name="Tên Topping / Tùy chọn")
    extra_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Giá cộng thêm"
    )
    is_available = models.BooleanField(default=True, verbose_name="Còn phục vụ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời gian cập nhật")

    class Meta:
        verbose_name = "Topping / Tùy chọn"
        verbose_name_plural = "Topping / Tùy chọn"
        ordering = ["name"]

    def __str__(self):
        return f"+{self.name} (+{self.extra_price:,.0f}đ)"


class Ingredient(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Tên nguyên liệu")
    current_quantity = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal("0.000"), verbose_name="Tồn kho hiện tại"
    )
    unit = models.CharField(
        max_length=20, default="g", verbose_name="Đơn vị tính (g, ml, cái...)"
    )
    reorder_level = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal("10.000"), verbose_name="Ngưỡng cảnh báo hết hàng"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời gian cập nhật")

    class Meta:
        verbose_name = "Nguyên liệu kho"
        verbose_name_plural = "Nguyên liệu kho"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.current_quantity}{self.unit})"

    @property
    def is_low_stock(self) -> bool:
        """Cờ báo hết hoặc sắp hết nguyên liệu"""
        return self.current_quantity <= self.reorder_level


class ProductRecipe(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="recipes", verbose_name="Món"
    )
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE, related_name="used_in_recipes", verbose_name="Nguyên liệu"
    )
    quantity_needed = models.DecimalField(
        max_digits=12, decimal_places=3, verbose_name="Định mức tiêu hao cho 1 ly"
    )

    class Meta:
        verbose_name = "Định mức công thức"
        verbose_name_plural = "Định mức công thức"
        unique_together = ("product", "ingredient")

    def __str__(self):
        return f"{self.product.name} -> {self.quantity_needed}{self.ingredient.unit} {self.ingredient.name}"


class Shift(models.Model):
    STATUS_OPEN = "OPEN"
    STATUS_CLOSED = "CLOSED"
    STATUS_CHOICES = [
        (STATUS_OPEN, "Đang mở"),
        (STATUS_CLOSED, "Đã chốt"),
    ]

    cashier_name = models.CharField(max_length=100, verbose_name="Tên thu ngân")
    opening_cash = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Tiền mặt đầu ca"
    )
    closing_cash = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, verbose_name="Tiền mặt thực đếm khi chốt ca"
    )
    opened_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời điểm mở ca")
    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="Thời điểm chốt ca")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN, verbose_name="Trạng thái ca"
    )
    notes = models.TextField(blank=True, default="", verbose_name="Ghi chú ca")

    class Meta:
        verbose_name = "Ca làm việc"
        verbose_name_plural = "Ca làm việc"
        ordering = ["-opened_at"]

    def __str__(self):
        return f"Ca #{self.id} - {self.cashier_name} ({self.get_status_display()})"

    @property
    def cash_sales(self) -> Decimal:
        """Tổng doanh thu tiền mặt (loại trừ đơn hủy)"""
        val = self.orders.filter(
            payment_method=Order.PAYMENT_CASH
        ).exclude(
            status=Order.STATUS_CANCELLED
        ).aggregate(total=models.Sum("total_amount"))["total"]
        return val or Decimal("0.00")

    @property
    def transfer_sales(self) -> Decimal:
        """Tổng doanh thu chuyển khoản/QR (loại trừ đơn hủy)"""
        val = self.orders.filter(
            payment_method=Order.PAYMENT_TRANSFER
        ).exclude(
            status=Order.STATUS_CANCELLED
        ).aggregate(total=models.Sum("total_amount"))["total"]
        return val or Decimal("0.00")

    @property
    def total_sales(self) -> Decimal:
        """Tổng doanh thu trong ca"""
        return self.cash_sales + self.transfer_sales

    @property
    def expected_cash(self) -> Decimal:
        """Tiền mặt dự kiến có trong két: opening_cash + cash_sales"""
        return self.opening_cash + self.cash_sales

    @property
    def cash_discrepancy(self) -> Decimal:
        """Mức chênh lệch tiền mặt: closing_cash - expected_cash (âm: hụt, dương: dư)"""
        if self.closing_cash is None:
            return Decimal("0.00")
        return self.closing_cash - self.expected_cash


class Order(models.Model):
    STATUS_PENDING = "PENDING"
    STATUS_PREPARING = "PREPARING"
    STATUS_READY = "READY"
    STATUS_COMPLETED = "COMPLETED"
    STATUS_CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Chờ pha chế"),
        (STATUS_PREPARING, "Đang pha chế"),
        (STATUS_READY, "Đã pha xong / Sẵn sàng"),
        (STATUS_COMPLETED, "Hoàn tất"),
        (STATUS_CANCELLED, "Đã hủy"),
    ]

    PAYMENT_CASH = "CASH"
    PAYMENT_TRANSFER = "TRANSFER"

    PAYMENT_CHOICES = [
        (PAYMENT_CASH, "Tiền mặt"),
        (PAYMENT_TRANSFER, "Chuyển khoản / QR"),
    ]

    order_code = models.CharField(
        max_length=32, unique=True, editable=False, verbose_name="Mã đơn hàng"
    )
    shift = models.ForeignKey(
        Shift, on_delete=models.PROTECT, related_name="orders", verbose_name="Ca làm việc"
    )
    table_number = models.CharField(
        max_length=50, blank=True, default="", verbose_name="Số bàn (nếu ngồi tại quán)"
    )
    is_takeaway = models.BooleanField(default=False, verbose_name="Mang đi")
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, verbose_name="Trạng thái"
    )
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_CHOICES, default=PAYMENT_CASH, verbose_name="Phương thức thanh toán"
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Tổng tiền thanh toán"
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00"), verbose_name="Số tiền giảm giá"
    )
    note = models.TextField(blank=True, default="", verbose_name="Ghi chú đơn")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian tạo")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Thời gian cập nhật")

    class Meta:
        verbose_name = "Đơn hàng"
        verbose_name_plural = "Đơn hàng"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order_code} - {self.get_status_display()} ({self.total_amount:,.0f}đ)"

    @classmethod
    def generate_order_code(cls) -> str:
        """Tự sinh mã đơn dạng ORD-XXXXXX"""
        random_suffix = uuid.uuid4().hex[:6].upper()
        code = f"ORD-{random_suffix}"
        while cls.objects.filter(order_code=code).exists():
            random_suffix = uuid.uuid4().hex[:6].upper()
            code = f"ORD-{random_suffix}"
        return code


class OrderItem(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="items", verbose_name="Đơn hàng"
    )
    product = models.ForeignKey(
        Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="order_items", verbose_name="Món"
    )
    product_name = models.CharField(
        max_length=150, verbose_name="Tên món (chốt cứng tại thời điểm đặt)"
    )
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Đơn giá gốc món tại thời điểm đặt"
    )
    quantity = models.PositiveIntegerField(default=1, verbose_name="Số lượng ly")
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Thành tiền dòng món"
    )
    notes = models.CharField(
        max_length=255, blank=True, default="", verbose_name="Ghi chú từng ly (ít ngọt, nhiều đá...)"
    )

    class Meta:
        verbose_name = "Chi tiết món đặt"
        verbose_name_plural = "Chi tiết món đặt"

    def __str__(self):
        return f"{self.quantity}x {self.product_name} ({self.subtotal:,.0f}đ)"


class OrderItemAddon(models.Model):
    order_item = models.ForeignKey(
        OrderItem, on_delete=models.CASCADE, related_name="addons", verbose_name="Dòng món"
    )
    addon = models.ForeignKey(
        Addon, on_delete=models.SET_NULL, null=True, blank=True, related_name="order_item_addons", verbose_name="Topping"
    )
    addon_name = models.CharField(
        max_length=100, verbose_name="Tên topping tại thời điểm đặt"
    )
    extra_price = models.DecimalField(
        max_digits=12, decimal_places=2, verbose_name="Đơn giá topping tại thời điểm đặt"
    )

    class Meta:
        verbose_name = "Topping dòng món"
        verbose_name_plural = "Topping dòng món"

    def __str__(self):
        return f"+{self.addon_name} (+{self.extra_price:,.0f}đ)"


class StockMovement(models.Model):
    TYPE_IMPORT = "IMPORT"
    TYPE_ORDER_DEDUCT = "ORDER_DEDUCT"
    TYPE_ORDER_REFUND = "ORDER_REFUND"
    TYPE_ADJUST = "ADJUST"

    TYPE_CHOICES = [
        (TYPE_IMPORT, "Nhập kho"),
        (TYPE_ORDER_DEDUCT, "Trừ kho theo đơn"),
        (TYPE_ORDER_REFUND, "Hoàn kho khi hủy đơn"),
        (TYPE_ADJUST, "Điều chỉnh kiểm kê"),
    ]

    movement_type = models.CharField(
        max_length=30, choices=TYPE_CHOICES, verbose_name="Loại biến động"
    )
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.PROTECT, related_name="movements", verbose_name="Nguyên liệu"
    )
    quantity_changed = models.DecimalField(
        max_digits=12, decimal_places=3, verbose_name="Lượng biến động (+/-)"
    )
    quantity_before = models.DecimalField(
        max_digits=12, decimal_places=3, verbose_name="Tồn kho trước biến động"
    )
    quantity_after = models.DecimalField(
        max_digits=12, decimal_places=3, verbose_name="Tồn kho sau biến động"
    )
    order = models.ForeignKey(
        Order, on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements", verbose_name="Đơn hàng liên quan"
    )
    reference_code = models.CharField(
        max_length=100, blank=True, default="", verbose_name="Mã đối soát / tham chiếu"
    )
    notes = models.TextField(blank=True, default="", verbose_name="Ghi chú biến động")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Thời gian ghi nhận")

    class Meta:
        verbose_name = "Biến động kho"
        verbose_name_plural = "Biến động kho"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_movement_type_display()}] {self.ingredient.name}: {self.quantity_changed:+}{self.ingredient.unit} ({self.created_at:%d/%m %H:%M})"
