# Order Flow Documentation

> **Mục đích**: Document chi tiết các flow liên quan đến đơn hàng (Order) trong BizFlow Platform.

---

## Mục lục

1. [Tổng quan Order](#1-tổng-quan-order)
2. [Order Entity Design](#2-order-entity-design)
3. [Manual Order Flow](#3-manual-order-flow)
4. [AI Voice Order Flow](#4-ai-voice-order-flow)
5. [Order Lifecycle](#5-order-lifecycle)
6. [Edit Order Flows](#6-edit-order-flows)
7. [Payment Flows](#7-payment-flows)
8. [Stock & Debt Rules](#8-stock--debt-rules)

---

## 1. Tổng quan Order

### Context

Đơn hàng là core của hệ thống BizFlow - nơi ghi nhận mọi giao dịch bán hàng của HKD.

### Order Creation Methods

| Method | Mô tả | User |
|--------|-------|------|
| **Manual** | User chọn sản phẩm, nhập số lượng, tạo đơn | Owner, Employee |
| **AI Voice** | User nói/up file record cuộc gọi giữa owner và khách hàng, AI parse thành draft order | Owner, Employee |

### Order Status Flow

```
                         ┌─────────────┐
                         │   PENDING   │◄─── Đơn mới tạo (manual / AI confirmed)
                         └──────┬──────┘
                                │
                   ┌────────────┼────────────┐
                   │            │            │
                   ▼            ▼            ▼
           ┌───────────┐  ┌───────────┐  ┌───────────┐
           │ COMPLETED │  │ HOT DELETE│  │  (Edit)   │
           └─────┬─────┘  └───────────┘  └───────────┘
                 │                            │
                 │  ┌──────────────────────┐  │
                 └─►│ "Sửa đơn hoàn tất"   │  │ Edit trực tiếp
                    │ Cancel old + Clone   │  │ (pending only)
                    │ thành Pending mới    │  │
                    └──────────────────────┘  │
                                              ▼
                                        ┌──────────┐
                                        │ PENDING  │
                                        │ (updated)│
                                        └──────────┘
```

### Status Definitions

| Status | Code | Mô tả | Cho phép sửa? | Side effects? |
|--------|------|-------|:-------------:|:-------------:|
| **Pending** | `pending` | Đơn đã tạo, chờ hoàn tất | ✅ Edit trực tiếp | ❌ Chưa trừ kho, chưa ghi nợ |
| **Completed** | `completed` | Đã giao hàng + thanh toán | ❌ Phải cancel + clone | ✅ Đã trừ kho + ghi nợ |
| **Cancelled** | `cancelled` | Đã hủy | ❌ | ✅ Hoàn kho + hoàn nợ (nếu từ completed) |

> **Nguyên tắc quan trọng**: Stock deduction + Debt recording chỉ xảy ra khi chuyển sang **Completed**. Khi Cancel đơn Completed → rollback stock + debt.

---

## 2. Order Entity Design

### Tables

```sql
-- =============================================
-- ORDERS TABLE
-- =============================================
CREATE TABLE Orders (
    OrderId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    OrderCode VARCHAR(50) NOT NULL COMMENT 'Mã đơn hàng: ORD-YYYYMMDD-NNN',
    BusinessLocationId INT NOT NULL,
    
    -- Clone reference (nếu đơn này là clone từ đơn completed bị cancel)
    RefOrderId BIGINT DEFAULT NULL COMMENT 'Đơn gốc đã cancel (nếu là clone)',
    
    -- Khách hàng (optional - có thể khách lẻ)
    DebtorId BIGINT DEFAULT NULL COMMENT 'Nếu là khách quen có hồ sơ nợ',
    CustomerName VARCHAR(255) DEFAULT NULL COMMENT 'Tên khách (nếu không có debtor)',
    CustomerPhone VARCHAR(20) DEFAULT NULL,
    
    -- Tổng tiền
    SubTotal DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'Tổng tiền hàng (sum OrderDetails)',
    Discount DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'Giảm giá tổng đơn',
    TotalAmount DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'SubTotal - Discount',
    
    -- Thanh toán (3 fields, tổng = TotalAmount)
    CashAmount DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'Số tiền trả bằng tiền mặt',
    BankAmount DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'Số tiền trả bằng chuyển khoản',
    DebtAmount DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'Số tiền ghi nợ',
    -- Constraint: CashAmount + BankAmount + DebtAmount = TotalAmount
    
    -- Status & metadata  
    Status VARCHAR(20) NOT NULL DEFAULT 'pending',
    BillMetadata JSON DEFAULT NULL,
    Note TEXT DEFAULT NULL,
    
    -- AI metadata (nếu tạo từ voice)
    IsFromAI BOOLEAN NOT NULL DEFAULT FALSE,
    AIConfidence DECIMAL(3,2) DEFAULT NULL COMMENT '0.00 - 1.00',
    OriginalTranscript TEXT DEFAULT NULL COMMENT 'Câu nói gốc',
    
    -- Audit
    CreatedByUserId CHAR(36) NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CompletedAt DATETIME DEFAULT NULL,
    CancelledAt DATETIME DEFAULT NULL,
    CancelledByUserId CHAR(36) DEFAULT NULL,
    CancelReasonCode VARCHAR(50) DEFAULT NULL COMMENT 'customer_changed_mind, out_of_stock, wrong_info, edit_completed, other',
    CancelReason TEXT DEFAULT NULL COMMENT 'Chi tiết lý do (nếu chọn other hoặc ghi chú thêm)',
    
    -- Indexes & FKs
    CONSTRAINT fk_order_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    CONSTRAINT fk_order_debtor FOREIGN KEY (DebtorId) 
        REFERENCES Debtors(DebtorId),
    CONSTRAINT fk_order_ref FOREIGN KEY (RefOrderId)
        REFERENCES Orders(OrderId),
    UNIQUE INDEX idx_order_code (OrderCode),
    INDEX idx_order_location (BusinessLocationId),
    INDEX idx_order_status (Status),
    INDEX idx_order_created (CreatedAt),
    INDEX idx_order_debtor (DebtorId),
    INDEX idx_order_ref (RefOrderId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- ORDER DETAILS TABLE
-- =============================================
CREATE TABLE OrderDetails (
    OrderDetailId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    OrderId BIGINT NOT NULL,
    
    -- Sản phẩm
    SaleItemId BIGINT NOT NULL COMMENT 'Đơn vị bán của product',
    ProductId BIGINT NOT NULL COMMENT 'Denormalized for easy query',
    ProductName VARCHAR(255) NOT NULL COMMENT 'Snapshot tên tại thời điểm bán',
    Unit VARCHAR(50) NOT NULL COMMENT 'Snapshot đơn vị',
    
    -- Số lượng & giá
    Quantity INT NOT NULL DEFAULT 1,
    UnitPrice DECIMAL(15,2) NOT NULL COMMENT 'Giá tại thời điểm bán',
    Discount DECIMAL(15,2) NOT NULL DEFAULT 0,
    Amount DECIMAL(15,2) NOT NULL COMMENT 'Quantity × UnitPrice - Discount',
    
    -- Audit
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_order_detail_order FOREIGN KEY (OrderId) 
        REFERENCES Orders(OrderId) ON DELETE CASCADE,
    CONSTRAINT fk_order_detail_sale_item FOREIGN KEY (SaleItemId) 
        REFERENCES SaleItems(SaleItemId),
    INDEX idx_order_detail_order (OrderId),
    INDEX idx_order_detail_product (ProductId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### Entity Classes

```csharp
public class Order
{
    public long OrderId { get; set; }
    public string OrderCode { get; set; } = null!;
    public int BusinessLocationId { get; set; }
    public long? RefOrderId { get; set; }
    
    // Customer
    public long? DebtorId { get; set; }
    public string? CustomerName { get; set; }
    public string? CustomerPhone { get; set; }
    
    // Money
    public decimal SubTotal { get; set; }
    public decimal Discount { get; set; }
    public decimal TotalAmount { get; set; }
    
    // Payment breakdown
    public decimal CashAmount { get; set; }
    public decimal BankAmount { get; set; }
    public decimal DebtAmount { get; set; }
    
    // Status
    public string Status { get; set; } = "pending";
    public string? BillMetadata { get; set; }
    public string? Note { get; set; }
    
    // AI
    public bool IsFromAI { get; set; }
    public decimal? AIConfidence { get; set; }
    public string? OriginalTranscript { get; set; }
    
    // Audit
    public Guid CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
    public DateTime? CompletedAt { get; set; }
    public DateTime? CancelledAt { get; set; }
    public Guid? CancelledByUserId { get; set; }
    public string? CancelReasonCode { get; set; }
    public string? CancelReason { get; set; }
    
    // Navigation
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
    public virtual Debtor? Debtor { get; set; }
    public virtual Order? RefOrder { get; set; }
    public virtual User CreatedByUser { get; set; } = null!;
    public virtual ICollection<OrderDetail> OrderDetails { get; set; } = new List<OrderDetail>();
}

public class OrderDetail
{
    public long OrderDetailId { get; set; }
    public long OrderId { get; set; }
    
    // Product snapshot
    public long SaleItemId { get; set; }
    public long ProductId { get; set; }
    public string ProductName { get; set; } = null!;
    public string Unit { get; set; } = null!;
    
    // Quantity & price
    public int Quantity { get; set; }
    public decimal UnitPrice { get; set; }
    public decimal Discount { get; set; }
    public decimal Amount { get; set; }  // Quantity × UnitPrice - Discount
    
    public DateTime CreatedAt { get; set; }
    
    // Navigation
    public virtual Order Order { get; set; } = null!;
    public virtual SaleItem SaleItem { get; set; } = null!;
}

public enum OrderStatus
{
    Pending,
    Completed,
    Cancelled
}

/// Cancel reason presets cho FE
public static class CancelReasonCodes
{
    public const string CustomerChangedMind = "customer_changed_mind";
    public const string OutOfStock = "out_of_stock";
    public const string WrongInfo = "wrong_info";
    public const string EditCompleted = "edit_completed";  // Auto khi sửa đơn completed
    public const string Other = "other";
}
```

### Payment Constraint

```markdown
TotalAmount = CashAmount + BankAmount + DebtAmount

Ví dụ các scenarios:
┌───────────────────────────────────────────────────────────────────────┐
│ Full cash:      Total=1,000,000  Cash=1,000,000  Bank=0  Debt=0       │
│ Full bank:      Total=1,000,000  Cash=0  Bank=1,000,000  Debt=0       │
│ Full debt:      Total=1,000,000  Cash=0  Bank=0  Debt=1,000,000       │
│ Cash + debt:    Total=1,000,000  Cash=600,000  Bank=0  Debt=400,000   │
│ Bank + debt:    Total=1,000,000  Cash=0  Bank=600,000  Debt=400,000   │
│ Cash + bank:    Total=1,000,000  Cash=500,000  Bank=500,000  Debt=0   │
│ All three:      Total=1,000,000  Cash=300,000  Bank=300,000 Debt=400k │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 3. Manual Order Flow

### Overview

User tạo đơn hàng thủ công qua app/web.

### Sequence Diagram

```markdown
┌─────────┐     ┌─────────┐     ┌─────────────┐     ┌──────────┐
│  User   │     │  App    │     │  Backend    │     │    DB    │
└────┬────┘     └────┬────┘     └──────┬──────┘     └────┬─────┘
     │               │                 │                 │
     │ Chọn products │                 │                 │
     │──────────────►│                 │                 │
     │               │                 │                 │
     │ Nhập quantity │                 │                 │
     │──────────────►│                 │                 │
     │               │                 │                 │
     │ (Optional)    │                 │                 │
     │ Chọn debtor   │                 │                 │
     │──────────────►│                 │                 │
     │               │                 │                 │
     │ Chọn payment  │                 │                 │
     │ cash/bank/debt│                 │                 │
     │──────────────►│                 │                 │
     │               │                 │                 │
     │ Submit Order  │ POST /orders    │                 │
     │──────────────►│────────────────►│                 │
     │               │                 │                 │
     │               │                 │ Validate:       │
     │               │                 │ - Location      │
     │               │                 │ - Products      │
     │               │                 │ - Debtor exists │
     │               │                 │   (nếu có debt) │
     │               │                 │ - Payment sum   │
     │               │                 │                 │
     │               │                 │ Check Stock     │
     │               │                 │ (warning nếu    │
     │               │                 │  không đủ)      │
     │               │                 │                 │
     │        [Nếu cần confirm]        │                 │
     │               │◄────────────────│                 │
     │ Hiển thị      │ 200 + warnings  │                 │
     │ cảnh báo stock│                 │                 │
     │◄──────────────│                 │                 │
     │ User confirm  │ POST /orders    │                 │
     │──────────────►│ confirmLow=true │                 │
     │               │────────────────►│                 │
     │               │                 │                 │
     │        [Tạo order - KHÔNG trừ kho, KHÔNG ghi nợ]  │
     │               │                 │────────────────►│
     │               │                 │   INSERT Order  │
     │               │                 │   Status=pending│
     │               │                 │◄────────────────│
     │               │                 │                 │
     │               │◄────────────────│                 │
     │ Order created │  201 Created    │                 │
     │ (pending)     │                 │                 │
     │◄──────────────│                 │                 │
```

> **Lưu ý quan trọng**: Tạo order chỉ INSERT vào DB với Status = pending.
> **KHÔNG trừ kho, KHÔNG ghi nợ** tại bước này. Đây chỉ là "ghi chép" đơn hàng.
> Side effects (stock + debt) chỉ xảy ra khi **Complete**.

### API Contract

```yaml
Lần 1: FE gửi request (confirmLowStock = false hoặc không có)
  → BE validate stock → Phát hiện thiếu hàng
  → Trả 200 OK + requiresConfirmation: true + warnings[]
  → KHÔNG tạo order

Lần 2: FE hiển thị cảnh báo → User xác nhận → FE gửi lại request (confirmLowStock = true)
  → BE bỏ qua stock warning → Tạo order (pending, KHÔNG trừ kho, KHÔNG ghi nợ)


Authorization: Bearer {token}

// Lần 1 - Chưa confirm
POST /api/orders
{
  "businessLocationId": 1,
  "debtorId": null,
  "customerName": "Anh Ba",
  "customerPhone": "0901234567",
  "cashAmount": 5200000,              // Số tiền cash
  "bankAmount": 0,                    // Số tiền bank
  "debtAmount": 0,                    // Số tiền ghi nợ
  "discount": 0,
  "note": "Giao trước 5h chiều",
  "isFromAI": false,
  "confirmLowStock": false,
  "items": [
    {
      "saleItemId": 123,
      "productId": 10,
      "quantity": 50,               // stock chỉ còn 5
      "unitPrice": 95000,
      "discount": 0
    },
    {
      "saleItemId": 456,
      "productId": 20,
      "quantity": 3,
      "unitPrice": 150000,
      "discount": 0
    }
  ]
}

Response khi cần confirm (HTTP 200, chưa tạo order):
{
  "success": true,
  "messageCode": "ORDER_STOCK_WARNING",
  "message": "Một số sản phẩm không đủ tồn kho. Vui lòng xác nhận để tiếp tục.",
  "data": {
    "requiresConfirmation": true,
    "warnings": [
      {
        "code": "LOW_STOCK",
        "productId": 10,
        "productName": "Xi măng Hà Tiên",
        "unit": "bao",
        "currentStock": 5,
        "requestedQuantity": 50,
        "message": "Xi măng Hà Tiên còn 5 bao, đơn cần 50 bao"
      }
    ]
  },
  "timestamp": "2026-02-25T10:30:00Z"
}

Request lần 2 - User đã xác nhận
POST /api/orders
{
  "businessLocationId": 1,
  "customerName": "Anh Ba",
  "customerPhone": "0901234567",
  "cashAmount": 5200000,
  "bankAmount": 0,
  "debtAmount": 0,
  "discount": 0,
  "note": "Giao trước 5h chiều",
  "isFromAI": false,
  "confirmLowStock": true,            // đã xác nhận
  "items": [
    { "saleItemId": 123, "productId": 10, "quantity": 50, "unitPrice": 95000, "discount": 0 },
    { "saleItemId": 456, "productId": 20, "quantity": 3,  "unitPrice": 150000, "discount": 0 }
  ]
}

Response khi tạo thành công (HTTP 201):
{
  "success": true,
  "messageCode": "ORDER_CREATED",
  "message": "Tạo đơn hàng thành công",
  "data": {
    "requiresConfirmation": false,
    "order": {
      "orderId": 1001,
      "orderCode": "ORD-20260225-001",
      "status": "pending",
      "subTotal": 5200000,
      "discount": 0,
      "totalAmount": 5200000,
      "cashAmount": 5200000,
      "bankAmount": 0,
      "debtAmount": 0,
      "createdAt": "2026-02-25T10:31:00Z"
    },
    "warnings": [
      {
        "code": "LOW_STOCK",
        "productId": 10,
        "productName": "Xi măng Hà Tiên",
        "unit": "bao",
        "currentStock": 5,
        "requestedQuantity": 50,
        "message": "Xi măng Hà Tiên còn 5 bao, đơn cần 50 bao (chưa trừ kho - pending)"
      }
    ]
  },
  "timestamp": "2026-02-25T10:31:00Z"
}

Ví dụ khác: Đơn hàng với ghi nợ một phần (cash + debt)
POST /api/orders
{
  "businessLocationId": 1,
  "debtorId": 45,
  "customerName": "Anh Ba",
  "cashAmount": 600000,               // Trả 600k tiền mặt
  "bankAmount": 0,
  "debtAmount": 400000,               // Ghi nợ 400k
  "discount": 0,
  "confirmLowStock": false,
  "items": [
    { "saleItemId": 123, "productId": 10, "quantity": 5, "unitPrice": 200000, "discount": 0 }
  ]
}
// Constraint: cashAmount + bankAmount + debtAmount = totalAmount = 1,000,000
// debtAmount > 0 → debtorId bắt buộc phải có
```

### Business Rules

**RULE-ORDER-01: Validate Location Access**

```csharp
// User phải có quyền access location
var assignment = await _unitOfWork.UserLocationAssignments
    .GetByUserAndLocationAsync(userId, request.BusinessLocationId);
if (assignment == null || !assignment.IsActive)
    throw new ForbiddenException("No access to this location");
```

**RULE-ORDER-02: Validate Products Exist**

```csharp
foreach (var item in request.Items)
{
    var saleItem = await _unitOfWork.SaleItems.GetByIdAsync(item.SaleItemId);
    if (saleItem == null)
        throw new NotFoundException($"SaleItem {item.SaleItemId} not found");
    
    // SaleItem phải thuộc location này
    if (saleItem.Product.BusinessLocationId != request.BusinessLocationId)
        throw new ValidationException($"Product not in this location");
}
```

**RULE-ORDER-03: Stock Check + Warning (không block, cảnh báo)**

```csharp
// Check tồn kho khi tạo order và khi Complete
// Nếu stock không đủ và confirmLowStock = false → trả warning, KHÔNG tạo/complete
// Nếu confirmLowStock = true → bỏ qua warning, tiếp tục
var warnings = new List<Warning>();
foreach (var item in request.Items)
{
    var product = await _unitOfWork.Products.GetByIdAsync(item.ProductId);
    if (product.TrackInventory && product.Stock < item.Quantity)
    {
        warnings.Add(new Warning
        {
            Code = "LOW_STOCK",
            ProductId = product.ProductId,
            ProductName = product.ProductName,
            CurrentStock = product.Stock,
            RequestedQuantity = item.Quantity,
            Message = $"{product.ProductName} còn {product.Stock}, đơn cần {item.Quantity}"
        });
    }
}

if (warnings.Any() && !request.ConfirmLowStock)
{
    return new OrderResponse
    {
        RequiresConfirmation = true,
        Warnings = warnings
    };
    // KHÔNG tạo order / KHÔNG complete
}
```

**RULE-ORDER-04: Payment Validation**

```csharp
// CashAmount + BankAmount + DebtAmount phải = TotalAmount
var paymentSum = request.CashAmount + request.BankAmount + request.DebtAmount;
if (paymentSum != order.TotalAmount)
    throw new ValidationException(
        $"Payment sum ({paymentSum:N0}) does not match total ({order.TotalAmount:N0})");

// Nếu có DebtAmount > 0 thì bắt buộc có DebtorId
if (request.DebtAmount > 0 && request.DebtorId == null)
    throw new ValidationException("Debt payment requires a registered debtor");

// Validate debtor exists và active
if (request.DebtorId.HasValue)
{
    var debtor = await _unitOfWork.Debtors.GetByIdAsync(request.DebtorId.Value);
    if (debtor == null || !debtor.IsActive)
        throw new ValidationException("Debtor not found or inactive");
}
```

---

## 4. AI Voice Order Flow

### Overview

User nói/nhắn tin tự nhiên → AI parse → App hiển thị draft → User confirm → Tạo order.

**Đặc điểm quan trọng**: Draft KHÔNG lưu vào DB, chỉ trả về cho app.

### Example Inputs

| Input (Voice/Text) | AI Output |
|-------------------|-----------|
| "Lấy 5 bao xi măng cho anh Ba, ghi nợ nha" | Product: Xi măng, Qty: 5, Customer: Anh Ba, Payment: debt |
| "Bán 2 thùng bia và 3 két nước ngọt, tiền mặt" | Products: [Bia x2, Nước ngọt x3], Payment: cash |
| "Order hôm nay của chị Lan: 10kg gạo, 5 lít dầu" | Products: [Gạo 10kg, Dầu 5 lít], Customer: Chị Lan |

### Sequence Diagram

```markdown
┌─────────┐     ┌─────────┐     ┌─────────────┐     ┌─────────────┐
│  User   │     │  App    │     │  AI Service │     │   Backend   │
└────┬────┘     └────┬────┘     └──────┬──────┘     └──────┬──────┘
     │               │                 │                   │
     │ Voice/Text    │                 │                   │
     │ "5 bao xi     │                 │                   │
     │  măng cho     │                 │                   │
     │  anh Ba"      │                 │                   │
     │──────────────►│                 │                   │
     │               │                 │                   │
     │               │ STT (if voice)  │                   │
     │               │────────────────►│                   │
     │               │                 │                   │
     │               │ Parse Order     │                   │
     │               │ (RAG + LLM)     │                   │
     │               │────────────────►│                   │
     │               │                 │                   │
     │               │                 │ Match products    │
     │               │                 │ from location     │
     │               │                 │─────────────────► │
     │               │                 │ GET /products     │
     │               │                 │◄───────────────── │
     │               │                 │                   │
     │               │ Draft Order     │                   │
     │               │ (không lưu DB)  │                   │
     │               │◄────────────────│                   │
     │               │                 │                   │
     │ Hiển thị draft│                 │                   │
     │◄──────────────│                 │                   │
     │               │                 │                   │
     │ User review   │                 │                   │
     │ & edit        │                 │                   │
     │──────────────►│                 │                   │
     │               │                 │                   │
     │ Confirm Order │                 │                   │
     │──────────────►│ POST /orders    │                   │
     │               │ (isFromAI=true) │                   │
     │               │─────────────────────────────────────►
     │               │                 │                   │
     │               │◄─────────────────────────────────────
     │ Order created │                 │                   │
     │◄──────────────│                 │                   │
```

### AI Service API

```yaml
POST /api/ai/parse-order
Authorization: Bearer {token}

Request:
{
  "businessLocationId": 1,
  "input": "Lấy 5 bao xi măng và 2 thùng gạch cho anh Ba, ghi nợ",
  "inputType": "text"    // "text" | "audio_base64"
}

Response:
{
  "success": true,
  "confidence": 0.92,
  "originalTranscript": "Lấy 5 bao xi măng và 2 thùng gạch cho anh Ba, ghi nợ",
  "parsedOrder": {
    "customerName": "Anh Ba",
    "customerPhone": null,
    "suggestedDebtorId": 45,      // Nếu match được debtor
    "paymentMethod": "debt",
    "items": [
      {
        "matchedSaleItemId": 123,
        "matchedProductName": "Xi măng Hà Tiên",
        "quantity": 5,
        "unit": "bao",
        "unitPrice": 95000,
        "confidence": 0.95,
        "originalText": "5 bao xi măng"
      },
      {
        "matchedSaleItemId": null,   // Không match được
        "matchedProductName": null,
        "quantity": 2,
        "unit": "thùng",
        "unitPrice": null,
        "confidence": 0.0,
        "originalText": "2 thùng gạch",
        "error": "Product not found: gạch"
      }
    ]
  },
  "warnings": [
    {
      "code": "PRODUCT_NOT_FOUND",
      "message": "Không tìm thấy sản phẩm: gạch"
    }
  ]
}
```

### App Draft Display

Khi nhận draft từ AI, app hiển thị:

```markdown
┌─────────────────────────────────────────────────────────┐
│    "Lấy 5 bao xi măng và 2 thùng gạch cho anh Ba..."    │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Khách hàng: [Anh Ba         ▼]  ← Dropdown debtors     │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │    Xi măng Hà Tiên                              │    │
│  │    5 x 95,000đ = 475,000đ           [ Edit ]    │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │    "2 thùng gạch" - Không tìm thấy              │    │
│  │    [Chọn sản phẩm ▼]                [ Xóa ]     │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  ───────────────────────────────────────────────────    │
│  Tổng tiền: 475,000đ                                    │
│  Thanh toán: [Ghi nợ ▼]                                 │
│                                                         │
│  [ Hủy ]                           [ Xác nhận đơn ]     │
└─────────────────────────────────────────────────────────┘
```

### Business Rules for AI

**RULE-AI-01: Always require user confirmation**

```csharp
// AI chỉ parse và suggest, KHÔNG tự động tạo order
// Draft phải được user review và confirm
```

**RULE-AI-02: Flag AI-created orders**

```csharp
// Khi user confirm draft từ AI
var order = new Order
{
    // ... other fields
    IsFromAI = true,
    AIConfidence = draftResponse.Confidence,
    OriginalTranscript = draftResponse.OriginalTranscript
};
```

**RULE-AI-03: Fallback to manual**

```csharp
// Nếu AI service không available hoặc fail
if (!aiResponse.Success)
{
    return new AiParseResponse
    {
        Success = false,
        Error = "AI service unavailable",
        FallbackMessage = "Vui lòng tạo đơn thủ công"
    };
}
```

---

## 5. Order Lifecycle

### State Transitions

```csharp
public enum OrderStatus
{
    Pending,    // Mới tạo, chờ hoàn tất
    Completed,  // Đã giao hàng + thanh toán xong
    Cancelled   // Đã hủy
}
```

### Valid Transitions

| From | To | Action | Who can do | Side Effects |
|------|-----|--------|------------|-------------|
| `pending` | `completed` | Complete order | Owner, Employee (own) | ✅ Trừ kho + Ghi nợ |
| `pending` | `cancelled` | Cancel order | Owner (any), Employee (own) | ❌ Không (chưa có side effect) |
| `completed` | `cancelled` + clone | "Sửa đơn hoàn tất" | Owner | ✅ Hoàn kho + Hoàn nợ |
| `cancelled` | - | N/A | - | - |

### Complete Order Flow

```markdown
┌────────────────┐
│ Order Pending  │
└───────┬────────┘
        │
        ▼
┌────────────────────────┐
│ User clicks "Complete" │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Validate:              │
│ - Status == Pending    │
│ - User has permission  │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│  Check Stock lần nữa   │◄─── Stock có thể thay đổi từ lúc tạo đơn
│ (cùng logic warning    │     Ví dụ: đơn khác đã complete trước
│  như khi tạo order)    │
└───────────┬────────────┘
            │
     ┌─────┼───────┐
     │             │
     ▼             ▼
[Stock OK]    [Stock thiếu + confirmLowStock=false]
     │             │
     │             ▼
     │        Trả 200 + warnings
     │        (KHÔNG complete)
     │        FE hiển cảnh báo
     │        User confirm → gửi lại với confirmLowStock=true
     │             │
     ▼             ▼
┌────────────────────────┐      ┌─────────────────────┐
│ Deduct Stock           │◄─────│ Only if             │
│ (for each item)        │      │ TrackInventory=true │
└───────────┬────────────┘      └─────────────────────┘
            │
            ▼
┌────────────────────────┐
│ Record Debt            │◄─── Nếu DebtAmount > 0
│ Debtor.Balance -= Debt │     Cập nhật Debtor.CurrentBalance
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Update Order:          │
│ - Status = Completed   │
│ - CompletedAt = now    │
└───────────┬────────────┘
            │
            ▼
        ✅ Done
```

### Complete Order API

```yaml
POST /api/orders/{id}/complete
Authorization: Bearer {token}

Request:
{
  "confirmLowStock": false    // Lần 1: false, Lần 2 (nếu cần): true
}

# Response khi stock OK (200):
{
  "success": true,
  "messageCode": "ORDER_COMPLETED",
  "data": {
    "orderId": 1001,
    "status": "completed",
    "completedAt": "2026-02-25T15:00:00Z",
    "stockDeducted": [
      { "productId": 10, "productName": "Xi măng", "quantity": 50, "stockAfter": -45 }
    ],
    "debtRecorded": {
      "debtorId": 45,
      "debtAmount": 400000,
      "balanceAfter": -1900000
    }
  }
}

# Response khi stock thiếu + chưa confirm (200, KHÔNG complete):
{
  "success": true,
  "messageCode": "ORDER_STOCK_WARNING",
  "data": {
    "requiresConfirmation": true,
    "warnings": [ ... ]
  }
}
```

### Cancel Order Flow

#### Cancel Pending Order

Không có side effect nào cần rollback (chưa trừ kho, chưa ghi nợ).

```markdown
┌────────────────┐
│ Order Pending  │
└───────┬────────┘
        │
        ▼
┌────────────────────────┐
│ User clicks "Cancel"   │
│ + Chọn cancel reason   │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Validate:              │
│ - Status == Pending    │
│ - User has permission  │
│   (Owner OR own order) │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Update Order:          │
│ - Status = Cancelled   │
│ - CancelledAt = now    │
│ - CancelledByUserId    │
│ - CancelReasonCode     │
│ - CancelReason (opt)   │
└───────────┬────────────┘
            │
            ▼
        ✅ Done (không cần rollback gì)
```

#### Cancel Completed Order ("Sửa đơn hoàn tất")

Phải rollback stock + debt, sau đó clone thành đơn mới.

```markdown
┌──────────────────┐
│ Order Completed  │
└────────┬─────────┘
         │
         ▼
┌────────────────────────────┐
│ Owner clicks               │
│ "Sửa đơn hoàn tất"         │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ 1. Rollback Stock          │
│    Product.Stock += Qty    │◄── Hoàn lại tồn kho đã trừ
│    (nếu TrackInventory)    │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ 2. Rollback Debt           │
│    Debtor.Balance += Debt  │◄── Hoàn lại nợ đã ghi
│    (nếu có DebtAmount > 0) │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ 3. Cancel Old Order        │
│    Status = Cancelled      │
│    CancelReasonCode =      │
│      "edit_completed"      │
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ 4. Clone → New Order       │
│    Status = Pending        │
│    RefOrderId = old.Id     │◄── Liên kết đơn gốc
│    Copy tất cả items       │
│    Check stock + warning   │◄── Như tạo mới
└────────────┬───────────────┘
             │
             ▼
┌────────────────────────────┐
│ 5. FE nhận đơn mới         │
│    Mở màn hình edit        │
│    User sửa + Complete     │
└────────────┬───────────────┘
             │
             ▼
         ✅ Done
```

### Cancel Reason Presets

```markdown
┌──────────────────────────────────────────────┐
│  Lý do hủy đơn:                              │
│                                              │
│  ○ Khách đổi ý       (customer_changed_mind) │
│  ○ Hết hàng           (out_of_stock)         │
│  ○ Nhập sai thông tin  (wrong_info)          │
│  ○ Khác: [________________]  (other)         │
│                                              │
│            [ Hủy ]    [ Xác nhận hủy ]       │
└──────────────────────────────────────────────┘
```

| CancelReasonCode | Hiển thị (VI) | Ghi chú |
|-----------------|--------------|--------|
| `customer_changed_mind` | Khách đổi ý | Preset |
| `out_of_stock` | Hết hàng | Preset |
| `wrong_info` | Nhập sai thông tin | Preset |
| `edit_completed` | Sửa đơn hoàn tất | Auto (BE tự set) |
| `other` | Khác | Bắt buộc nhập CancelReason |

### Cancel API

```yaml
POST /api/orders/{id}/cancel
Authorization: Bearer {token}

# Cancel pending order
Request:
{
  "cancelReasonCode": "customer_changed_mind",
  "cancelReason": null    // Optional khi chọn preset
}

# Cancel completed order ("sửa đơn") - Chỉ Owner
POST /api/orders/{id}/cancel-and-clone
Request:
{
  "cancelReasonCode": "edit_completed"    // Auto, FE không cần hiện form lý do
}

Response:
{
  "success": true,
  "messageCode": "ORDER_CANCELLED_AND_CLONED",
  "data": {
    "cancelledOrder": {
      "orderId": 1001,
      "status": "cancelled",
      "cancelReasonCode": "edit_completed",
      "stockRolledBack": true,
      "debtRolledBack": true
    },
    "clonedOrder": {
      "orderId": 1005,
      "orderCode": "ORD-20260225-005",
      "refOrderId": 1001,
      "status": "pending",
      "warnings": [ ... ]    // Stock warnings nếu có
    }
  }
}
```

---

## 6. Edit Order Flows

### 6.1 Edit Pending Order (Trực tiếp)

Khi đơn đang `pending`, user có thể edit trực tiếp mà không cần cancel + clone (vì chưa có side effect nào).

**Cho phép sửa**:
- Thêm/xóa/sửa items (sản phẩm, số lượng, giá)
- Đổi payment breakdown (cash/bank/debt)
- Đổi debtor
- Đổi customer info
- Sửa discount, note

**Quyền**:
- Owner: sửa mọi đơn pending trong location
- Employee: chỉ sửa đơn mình tạo

```yaml
PUT /api/orders/{id}
Authorization: Bearer {token}

Request:
{
  "debtorId": 45,
  "customerName": "Anh Ba",
  "customerPhone": "0901234567",
  "cashAmount": 600000,
  "bankAmount": 0,
  "debtAmount": 400000,
  "discount": 50000,
  "note": "Giao 5h chiều",
  "confirmLowStock": false,
  "items": [
    { "saleItemId": 123, "productId": 10, "quantity": 10, "unitPrice": 95000, "discount": 0 },
    { "saleItemId": 789, "productId": 30, "quantity": 2,  "unitPrice": 50000, "discount": 0 }
  ]
}

Response (200 OK):
{
  "success": true,
  "messageCode": "ORDER_UPDATED",
  "data": {
    "order": {
      "orderId": 1001,
      "status": "pending",
      "subTotal": 1050000,
      "discount": 50000,
      "totalAmount": 1000000,
      "cashAmount": 600000,
      "bankAmount": 0,
      "debtAmount": 400000,
      "updatedAt": "2026-02-25T12:00:00Z"
    },
    "warnings": []
  }
}
```

**Business Rules**:

```csharp
// RULE: Chỉ edit đơn pending
if (order.Status != OrderStatus.Pending)
    throw new ValidationException("Only pending orders can be edited directly");

// RULE: Employee chỉ sửa đơn của mình
if (!isOwner && order.CreatedByUserId != currentUserId)
    throw new ForbiddenException("Can only edit your own orders");

// RULE: Re-validate payment sum
var paymentSum = request.CashAmount + request.BankAmount + request.DebtAmount;
var newTotal = CalculateTotal(request.Items, request.Discount);
if (paymentSum != newTotal)
    throw new ValidationException("Payment sum does not match total");

// RULE: Check stock + warning (cùng logic như tạo mới)
// KHÔNG trừ kho - vẫn pending
```

### 6.2 Edit Completed Order (Cancel + Clone)

Khi đơn đã `completed`, không thể edit trực tiếp vì đã có side effects (stock đã trừ, debt đã ghi).

**Flow**: Xem phần [Cancel Completed Order](#cancel-completed-order-"sửa-đơn-hoàn-tất")

**Quyền**: Chỉ Owner

**Lý do**: Đơn completed đã ảnh hưởng stock + debt. Chỉ Owner mới được rollback (đây là thao tác có rủi ro cao).

---

## 7. Payment Flows

### Payment Model

3 fields trên Order, tổng luôn = TotalAmount:

```markdown
TotalAmount = CashAmount + BankAmount + DebtAmount
```

### Payment Scenarios

| Scenario | CashAmount | BankAmount | DebtAmount | Debtor required? |
|----------|:----------:|:----------:|:----------:|:----------------:|
| Full cash | 1,000,000 | 0 | 0 | ❌ |
| Full bank | 0 | 1,000,000 | 0 | ❌ |
| Full debt | 0 | 0 | 1,000,000 | ✅ |
| Cash + bank | 500,000 | 500,000 | 0 | ❌ |
| Cash + debt | 600,000 | 0 | 400,000 | ✅ |
| Bank + debt | 0 | 600,000 | 400,000 | ✅ |
| Cash + bank + debt | 300,000 | 300,000 | 400,000 | ✅ |

### Payment Validation

```csharp
// RULE-PAY-01: Tổng payment = TotalAmount
var paymentSum = request.CashAmount + request.BankAmount + request.DebtAmount;
if (paymentSum != order.TotalAmount)
    throw new ValidationException("Payment breakdown does not match total");

// RULE-PAY-02: Các amount không được âm
if (request.CashAmount < 0 || request.BankAmount < 0 || request.DebtAmount < 0)
    throw new ValidationException("Payment amounts cannot be negative");

// RULE-PAY-03: DebtAmount > 0 → bắt buộc có Debtor
if (request.DebtAmount > 0 && request.DebtorId == null)
    throw new ValidationException("Debt payment requires a registered debtor");
```

### Khi nào Debt được ghi? (Quan trọng)

> **Debt chỉ ghi khi Order chuyển sang COMPLETED, KHÔNG phải khi tạo.**

```csharp
// KHI TẠO ORDER (pending):
order.DebtAmount = request.DebtAmount;  // Chỉ lưu số tiền
// KHÔNG update Debtor.CurrentBalance

// KHI COMPLETE ORDER:
if (order.DebtAmount > 0 && order.DebtorId.HasValue)
{
    var debtor = await _unitOfWork.Debtors.GetByIdAsync(order.DebtorId.Value);
    
    // Check credit limit (soft warning)
    var currentDebt = Math.Abs(Math.Min(0, debtor.CurrentBalance));
    var projectedDebt = currentDebt + order.DebtAmount;
    if (debtor.CreditLimit.HasValue && projectedDebt > debtor.CreditLimit.Value)
    {
        // Warning nhưng vẫn cho complete
        _logger.LogWarning($"Debtor {debtor.DebtorId} over limit: {projectedDebt:N0}/{debtor.CreditLimit:N0}");
    }
    
    debtor.CurrentBalance -= order.DebtAmount;  // Ghi nợ
}

// KHI CANCEL ORDER (đã completed):
if (order.DebtAmount > 0 && order.DebtorId.HasValue)
{
    var debtor = await _unitOfWork.Debtors.GetByIdAsync(order.DebtorId.Value);
    debtor.CurrentBalance += order.DebtAmount;  // Hoàn nợ
}
```

### Báo cáo luồng tiền

Với 3 fields riêng biệt, query báo cáo rất dễ:

```sql
-- Tổng hợp luồng tiền theo ngày (chỉ tính đơn completed)
SELECT 
    DATE(CompletedAt) AS SaleDate,
    SUM(CashAmount) AS TotalCash,
    SUM(BankAmount) AS TotalBank,
    SUM(DebtAmount) AS TotalDebt,
    SUM(TotalAmount) AS TotalRevenue,
    COUNT(*) AS OrderCount
FROM Orders
WHERE Status = 'completed'
  AND BusinessLocationId = @locationId
GROUP BY DATE(CompletedAt)
ORDER BY SaleDate DESC;
```

---

## 8. Stock & Debt Rules

### Stock Deduction

**Nguyên tắc**: Stock chỉ bị trừ khi order được **Complete**, KHÔNG trừ khi tạo.

```csharp
public async Task CompleteOrderAsync(long orderId, CompleteOrderRequest request, Guid userId)
{
    var order = await _unitOfWork.Orders
        .Include(o => o.OrderDetails)
        .GetByIdAsync(orderId);
    
    if (order.Status != OrderStatus.Pending)
        throw new ValidationException("Order is not pending");
    
    // === Check stock lần nữa (stock có thể thay đổi từ lúc tạo đơn) ===
    var warnings = new List<Warning>();
    foreach (var detail in order.OrderDetails)
    {
        var product = await _unitOfWork.Products.GetByIdAsync(detail.ProductId);
        if (product.TrackInventory && product.Stock < detail.Quantity)
        {
            warnings.Add(new Warning
            {
                Code = "LOW_STOCK",
                ProductId = product.ProductId,
                ProductName = product.ProductName,
                CurrentStock = product.Stock,
                RequestedQuantity = detail.Quantity
            });
        }
    }
    
    if (warnings.Any() && !request.ConfirmLowStock)
    {
        return new CompleteOrderResponse
        {
            RequiresConfirmation = true,
            Warnings = warnings
        };
        // KHÔNG complete
    }
    
    // === Deduct stock ===
    foreach (var detail in order.OrderDetails)
    {
        var product = await _unitOfWork.Products.GetByIdAsync(detail.ProductId);
        if (product.TrackInventory)
        {
            product.Stock -= detail.Quantity;
            // Cho phép âm - đã warning rồi
        }
    }
    
    // === Record debt ===
    if (order.DebtAmount > 0 && order.DebtorId.HasValue)
    {
        var debtor = await _unitOfWork.Debtors.GetByIdAsync(order.DebtorId.Value);
        debtor.CurrentBalance -= order.DebtAmount;
    }
    
    // === Update order ===
    order.Status = OrderStatus.Completed;
    order.CompletedAt = DateTime.UtcNow;
    
    await _unitOfWork.SaveChangesAsync();
}
```

### Stock Rollback (Cancel Completed)

```csharp
public async Task CancelCompletedOrderAsync(long orderId, Guid userId)
{
    var order = await _unitOfWork.Orders
        .Include(o => o.OrderDetails)
        .GetByIdAsync(orderId);
    
    if (order.Status != OrderStatus.Completed)
        throw new ValidationException("Only completed orders can use cancel-and-clone");
    
    // === Rollback stock ===
    foreach (var detail in order.OrderDetails)
    {
        var product = await _unitOfWork.Products.GetByIdAsync(detail.ProductId);
        if (product.TrackInventory)
        {
            product.Stock += detail.Quantity;  // Hoàn lại
        }
    }
    
    // === Rollback debt ===
    if (order.DebtAmount > 0 && order.DebtorId.HasValue)
    {
        var debtor = await _unitOfWork.Debtors.GetByIdAsync(order.DebtorId.Value);
        debtor.CurrentBalance += order.DebtAmount;  // Hoàn lại
    }
    
    // === Cancel old order ===
    order.Status = OrderStatus.Cancelled;
    order.CancelledAt = DateTime.UtcNow;
    order.CancelledByUserId = userId;
    order.CancelReasonCode = CancelReasonCodes.EditCompleted;
    order.CancelReason = "Sửa đơn hoàn tất - tạo đơn thay thế";
    
    // === Clone thành đơn mới ===
    var clonedOrder = new Order
    {
        OrderCode = GenerateNewOrderCode(),
        BusinessLocationId = order.BusinessLocationId,
        RefOrderId = order.OrderId,  // Link về đơn gốc
        DebtorId = order.DebtorId,
        CustomerName = order.CustomerName,
        CustomerPhone = order.CustomerPhone,
        SubTotal = order.SubTotal,
        Discount = order.Discount,
        TotalAmount = order.TotalAmount,
        CashAmount = order.CashAmount,
        BankAmount = order.BankAmount,
        DebtAmount = order.DebtAmount,
        Status = OrderStatus.Pending,  // Pending để user sửa
        Note = order.Note,
        CreatedByUserId = userId,
        CreatedAt = DateTime.UtcNow
    };
    
    // Clone items
    foreach (var detail in order.OrderDetails)
    {
        clonedOrder.OrderDetails.Add(new OrderDetail
        {
            SaleItemId = detail.SaleItemId,
            ProductId = detail.ProductId,
            ProductName = detail.ProductName,
            Unit = detail.Unit,
            Quantity = detail.Quantity,
            UnitPrice = detail.UnitPrice,
            Discount = detail.Discount,
            Amount = detail.Amount
        });
    }
    
    await _unitOfWork.Orders.AddAsync(clonedOrder);
    await _unitOfWork.SaveChangesAsync();
}
```

### TrackInventory Flag

```csharp
// Không phải product nào cũng cần track inventory
// Ví dụ: Dịch vụ cắt tóc, F&B làm tại chỗ
if (!product.TrackInventory)
{
    // Không trừ stock, chỉ ghi nhận doanh thu
    continue;
}
```

### Tổng kết Side Effects theo Status

| Action | Stock | Debt | Rollback khi Cancel? |
|--------|:-----:|:----:|:--------------------:|
| Tạo order (pending) | ❌ | ❌ | Không cần |
| Edit pending | ❌ | ❌ | Không cần |
| Complete order | ✅ Trừ | ✅ Ghi | - |
| Cancel pending | ❌ | ❌ | Không cần |
| Cancel completed | ✅ Hoàn | ✅ Hoàn | ✅ |
| Clone (từ cancel completed) | ❌ | ❌ | Đơn mới = pending |

---

## 9. API Endpoints Summary

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/orders` | Tạo order mới (manual/AI confirmed) | Owner, Employee |
| `GET` | `/api/orders` | List orders (filter: location, status, date) | Owner, Employee |
| `GET` | `/api/orders/{id}` | Get order detail | Owner, Employee |
| `PUT` | `/api/orders/{id}` | Edit pending order | Owner (all), Employee (own) |
| `POST` | `/api/orders/{id}/complete` | Complete order (trừ kho + ghi nợ) | Owner, Employee |
| `POST` | `/api/orders/{id}/cancel` | Cancel pending order | Owner (all), Employee (own) |
| `POST` | `/api/orders/{id}/cancel-and-clone` | Cancel completed + clone mới | Owner only |
| `POST` | `/api/ai/parse-order` | Parse voice/text → draft order | Owner, Employee |

---

## Appendix: Error Codes

| Code | HTTP | Message |
|------|------|---------|
| `ORDER_NOT_FOUND` | 404 | Order không tồn tại |
| `ORDER_NOT_EDITABLE` | 400 | Order đã complete/cancel, không thể sửa trực tiếp |
| `ORDER_NOT_PENDING` | 400 | Order không ở trạng thái pending |
| `ORDER_NOT_COMPLETED` | 400 | Order phải ở trạng thái completed để thực hiện cancel-and-clone |
| `PAYMENT_SUM_MISMATCH` | 400 | CashAmount + BankAmount + DebtAmount ≠ TotalAmount |
| `PAYMENT_NEGATIVE` | 400 | Số tiền thanh toán không được âm |
| `PRODUCT_NOT_IN_LOCATION` | 400 | Sản phẩm không thuộc location này |
| `DEBTOR_REQUIRED` | 400 | DebtAmount > 0 nhưng chưa chọn debtor |
| `DEBTOR_NOT_FOUND` | 404 | Debtor không tồn tại hoặc inactive |
| `CANCEL_REASON_REQUIRED` | 400 | Chọn "other" nhưng chưa nhập lý do |
| `NO_PERMISSION` | 403 | Không có quyền thực hiện action này |
| `AI_SERVICE_UNAVAILABLE` | 503 | AI service không khả dụng |
| `ORDER_STOCK_WARNING` | 200 | Cảnh báo tồn kho - cần user confirm |
