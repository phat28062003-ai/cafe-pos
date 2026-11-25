# Dự Án Cafe POS, Inventory & Real-Time Order API (Bản v2)

Hệ thống backend lõi cho quán cà phê và cửa hàng đồ uống xây dựng trên nền tảng **Django**, **Strawberry GraphQL** và **Django Channels (ASGI)**.

Hệ thống tích hợp toàn diện quy trình vận hành thực tế qua một GraphQL endpoint duy nhất (`/graphql/`), hỗ trợ đồng thời cả **HTTP (Query / Mutation)** và **WebSocket (Subscription)**.

---

## 1. Kiến Trúc Dự Án & Các Tầng Xử Lý

```
storecf/
├── cafe_pos/
│   ├── asgi.py             # Cấu hình ASGI ProtocolTypeRouter (HTTP + WebSocket trên /graphql/)
│   ├── settings.py         # Cấu hình Django, Channels InMemoryLayer, Strawberry Django
│   ├── urls.py             # HTTP Route mapping cho GraphQLView
│   └── wsgi.py
├── pos/
│   ├── models.py           # Tầng dữ liệu: Menu, Topping, Định mức, Kho, Ca làm việc, Đơn hàng
│   ├── services.py         # Tầng giao dịch: transaction.atomic, select_for_update, logic hoàn/trừ kho
│   ├── types.py            # Tầng GraphQL Types & Inputs (Strawberry Django)
│   ├── schema.py           # Tầng GraphQL Schema: Query, Mutation, Subscription, DjangoOptimizer
│   ├── admin.py            # Giao diện quản trị Django Admin
│   └── tests.py            # Bộ kiểm thử tự động toàn diện (Unit & Integration tests)
├── seed_data.py            # Kịch bản nạp dữ liệu mẫu thực tế
├── manage.py
└── README.md
```

### Các Tầng Trọng Tâm

1. **Tầng Dữ Liệu & Định Lượng (`pos/models.py`)**:
   - `Category`, `Product`, `Addon`: Thực đơn phân cấp, quản lý giá gốc, giá topping và trạng thái khả dụng (`is_available`).
   - `Ingredient`: Quản lý số lượng tồn, đơn vị tính, ngưỡng báo hết hàng (`reorder_level`), tự động phát cờ `is_low_stock`.
   - `ProductRecipe`: Thiết lập định mức nguyên liệu tiêu hao cho 1 đơn vị món (ví dụ 1 ly bạc xỉu cần 15g Robusta, 40ml sữa đặc, 60ml sữa tươi).
   - `Shift`: Quản lý ca làm việc, lưu số tiền mặt đầu ca (`opening_cash`), số tiền đếm khi chốt ca (`closing_cash`), tự tính doanh thu tiền mặt, chuyển khoản và mức chênh lệch két (`cash_discrepancy`).
   - `Order`, `OrderItem`, `OrderItemAddon`: Đơn hàng chốt cứng (snapshot) đơn giá gốc của món và topping tại thời điểm đặt, lưu ghi chú từng ly, số bàn, mang đi, giảm giá, phương thức thanh toán. Tự sinh mã `ORD-XXXXXX`.
   - `StockMovement`: Nhật ký biến động kho (`IMPORT`, `ORDER_DEDUCT`, `ORDER_REFUND`, `ADJUST`), lưu tồn trước/sau và mã đối soát.

2. **Tầng Nghiệp Vụ Giao Dịch (`pos/services.py`)**:
   - Sử dụng `@transaction.atomic` và khóa dòng `select_for_update()` để chống race condition và xung đột khi nhiều thu ngân hoặc khách đặt món đồng thời.
   - Các nguyên liệu được sắp xếp ID tăng dần (`order_by('id')`) trước khi khóa dòng nhằm triệt tiêu hoàn toàn nguy cơ Deadlock đa luồng.
   - Kiểm tra tồn kho trước khi tạo đơn: nếu thiếu nguyên liệu, transaction lập tức rollback toàn bộ và thông báo chi tiết nguyên liệu còn thiếu.
   - Tự động hoàn kho khi đơn chuyển sang `CANCELLED`: quét đúng các dòng `ORDER_DEDUCT` đã trừ trước đó để hoàn lại, chống hoàn lặp.
   - Quản lý vòng đời trạng thái đơn hàng nghiêm ngặt: `PENDING -> PREPARING -> READY -> COMPLETED / CANCELLED`. Chặn thay đổi trạng thái của đơn đã hoàn tất hoặc đã hủy.

3. **Tầng GraphQL & Real-time (`pos/types.py`, `pos/schema.py`, `cafe_pos/asgi.py`)**:
   - Tích hợp `DjangoOptimizerExtension` của Strawberry Django giúp tự động tối ưu các câu truy vấn quan hệ lồng nhau (`orders -> items -> addons`, `products -> recipes -> ingredient`), giải quyết triệt để bài toán N+1 query.
   - Subscription `orderEvents`: Bộ phát sự kiện `OrderEventBroadcaster` đẩy dữ liệu đơn hàng ngay lập tức qua WebSocket tới màn hình quầy bar và quầy thu ngân.

---

## 2. Hướng Dẫn Cài Đặt & Chạy Ứng Dụng

### Yêu cầu môi trường
- Python >= 3.10
- Django >= 5.0
- Strawberry GraphQL & strawberry-graphql-django
- Django Channels & Uvicorn

### Khởi chạy môi trường & Database

```bash
# Áp dụng migrations
python manage.py migrate

# Nạp dữ liệu mẫu thực tế
python seed_data.py

# Chạy test suite kiểm thử
python manage.py test pos
```

### Khởi động ASGI Server (Hỗ trợ cả HTTP & WebSocket)

```bash
uvicorn cafe_pos.asgi:application --host 0.0.0.0 --port 8000 --reload
```

Truy cập GraphiQL Playground trực quan tại: `http://localhost:8000/graphql/`

---

## 3. Tài Liệu API GraphQL Chi Tiết

Endpoint duy nhất:
- **HTTP**: `http://localhost:8000/graphql/` (Query & Mutation)
- **WebSocket**: `ws://localhost:8000/graphql/` (Subscription)

### A. Quản Lý Thực Đơn & Công Thức

#### 1. Tạo danh mục và món:
```graphql
mutation CreateMenu {
  createCategory(name: "Trà sữa Ô long", description: "Dòng trà sữa đậm vị") {
    id
    name
  }
  
  createProduct(
    categoryId: 1
    name: "Trà sữa Ô long nướng"
    basePrice: "42000"
    description: "Vị trà đậm, sữa thanh ngậy"
    isAvailable: true
  ) {
    id
    name
    basePrice
  }
}
```

#### 2. Thêm topping:
```graphql
mutation CreateAddon {
  createAddon(name: "Trân châu hoàng kim", extraPrice: "10000", isAvailable: true) {
    id
    name
    extraPrice
  }
}
```

#### 3. Khai báo định mức nguyên liệu tiêu hao cho 1 ly:
```graphql
mutation SetupRecipe {
  addRecipeItem(
    productId: 1
    ingredientId: 5
    quantityNeeded: "20.000" # 20g trà Ô long cho 1 ly
  ) {
    id
    product {
      name
    }
    ingredient {
      name
      unit
    }
    quantityNeeded
  }
}
```

---

### B. Quản Lý Kho & Biến Động

#### 1. Tạo nguyên liệu kho & Xem cảnh báo sắp hết:
```graphql
mutation CreateIngredient {
  createIngredient(
    name: "Bột Matcha Kyoto"
    currentQuantity: "250.000"
    unit: "g"
    reorderLevel: "500.000"
  ) {
    id
    name
    currentQuantity
    isLowStock
  }
}

query CheckLowStock {
  ingredients(lowStockOnly: true) {
    id
    name
    currentQuantity
    unit
    reorderLevel
    isLowStock
  }
}
```

#### 2. Nhập kho nguyên liệu (IMPORT):
```graphql
mutation Restock {
  restockIngredient(
    ingredientId: 1
    quantityAdded: "5000.000"
    referenceCode: "PO-2026-11-001"
    notes: "Nhập 5kg hạt Robusta từ nông trại Buôn Ma Thuột"
  ) {
    id
    name
    currentQuantity
    unit
  }
}
```

#### 3. Truy vết nhật ký biến động kho:
```graphql
query AuditStockMovements {
  stockMovements(orderCode: "ORD-38D29E") {
    id
    movementType
    ingredient {
      name
      unit
    }
    quantityChanged
    quantityBefore
    quantityAfter
    referenceCode
    createdAt
  }
}
```

---

### C. Quản Lý Ca Làm Việc & Đối Soát Két Tiền

#### 1. Mở ca làm việc (Chặn mở chồng ca):
```graphql
mutation OpenShift {
  openShift(
    cashierName: "Lê Minh Trí"
    openingCash: "1500000.00"
    notes: "Ca sáng bắt đầu 07:00, đã kiểm tra tiền lẻ"
  ) {
    id
    cashierName
    status
    openingCash
    openedAt
  }
}
```

#### 2. Chốt ca & Đối soát doanh thu két tiền:
```graphql
mutation CloseShift {
  closeShift(
    shiftId: 1
    closingCash: "1650000.00" # Số tiền mặt thực tế kiểm đếm lúc chốt ca
    notes: "Két tiền bàn giao lại cho ca chiều"
  ) {
    id
    status
    closedAt
    openingCash
    closingCash
    cashSales
    transferSales
    totalSales
    expectedCash
    cashDiscrepancy # Âm: hụt tiền, Dương: thừa tiền
  }
}
```

#### 3. Xem tóm tắt đối soát ca làm việc:
```graphql
query GetShiftSummary {
  shiftSummary(shiftId: 1) {
    shiftId
    cashierName
    status
    openingCash
    closingCash
    cashSales
    transferSales
    totalSales
    expectedCash
    cashDiscrepancy
    totalOrdersCount
    validOrdersCount
    cancelledOrdersCount
  }
}
```

---

### D. Xử Lý Đơn Hàng & Điều Phối Barista

#### 1. Tạo đơn hàng mới (Tự động trừ kho theo định mức):
```graphql
mutation CreateOrder {
  createOrder(input: {
    items: [
      {
        productId: 1
        quantity: 2
        notes: "Ít ngọt, 70% đá"
        addonIds: [1, 2]
      },
      {
        productId: 4
        quantity: 1
        notes: "Uống liền"
      }
    ]
    tableNumber: "Bàn 05"
    isTakeaway: false
    paymentMethod: "CASH"
    discountAmount: "5000.00"
    note: "Khách quen giảm 5k"
  }) {
    id
    orderCode
    status
    paymentMethod
    totalAmount
    discountAmount
    tableNumber
    items {
      productName
      quantity
      unitPrice
      subtotal
      notes
      addons {
        addonName
        extraPrice
      }
    }
  }
}
```

#### 2. Điều phối trạng thái đơn hàng (PENDING -> PREPARING -> READY -> COMPLETED / CANCELLED):
```graphql
mutation UpdateStatus {
  updateOrderStatus(
    orderId: 1
    newStatus: "PREPARING"
    note: "Barista bắt đầu pha"
  ) {
    orderCode
    status
  }
}
```

> **Lưu ý nghiệp vụ**:
> - Khi chuyển sang `CANCELLED`, hệ thống tự động hoàn lại số nguyên liệu đã trừ kho về đúng trạng thái ban đầu.
> - Khi đơn đã `COMPLETED` hoặc `CANCELLED`, hệ thống chặn hoàn toàn mọi nỗ lực chuyển ngược trạng thái.

#### 3. Lọc danh sách đơn hàng linh hoạt:
```graphql
query FilterOrders {
  orders(filter: {
    status: "PENDING"
    paymentMethod: "CASH"
    tableNumber: "Bàn"
  }) {
    orderCode
    status
    tableNumber
    totalAmount
    items {
      productName
      quantity
      subtotal
    }
  }
}
```

---

### E. Real-Time Order Subscription (WebSocket)

Lắng nghe sự kiện đơn hàng thời gian thực (được kích hoạt ngay khi tạo đơn mới hoặc đổi trạng thái):

```graphql
subscription OnOrderEvents {
  orderEvents {
    id
    orderCode
    status
    tableNumber
    isTakeaway
    paymentMethod
    totalAmount
    updatedAt
    items {
      productName
      quantity
      notes
      addons {
        addonName
      }
    }
  }
}
```

---

## 4. Kiểm Thử Tự Động (Automated Testing)

Toàn bộ các ca kiểm thử được viết trong `pos/tests.py`, kiểm chứng 100% các tình huống biên:
- Quản lý ca: Mở ca, chặn mở đè ca, tính doanh thu tiền mặt vs chuyển khoản, tính chênh lệch két tiền.
- Quản lý định mức & kho: Cảnh báo hết hàng (`is_low_stock`), nhập kho (`restockIngredient`), tự động trừ kho theo công thức khi đặt món.
- Chặn đơn khi kho không đủ: Kiểm tra tính nguyên tử (`transaction.atomic`), rollback toàn bộ dữ liệu.
- Hoàn kho khi hủy đơn: Kiểm tra cộng lại đúng lượng nguyên liệu, chống hoàn kho hai lần.
- Tính toàn vẹn snapshot giá: Đổi giá gốc sản phẩm/topping sau khi đặt đơn không làm lệch giá đơn hàng cũ.
- Máy trạng thái đơn hàng: Chặn các bước chuyển trạng thái sai quy tắc, khóa trạng thái hoàn tất/hủy.
- Tích hợp GraphQL Query & Mutation qua `schema.execute_sync()`.
- Tích hợp GraphQL Subscription qua WebSocket (`schema.subscribe()`).

Chạy lệnh kiểm thử:
```bash
python manage.py test pos
```
Kết quả:
```
Ran 11 tests in 0.145s
OK
```
