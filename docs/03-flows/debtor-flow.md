# Debtor Flow Documentation

> **Mục đích**: Document chi tiết các flow quản lý công nợ (Debtor) trong BizFlow Platform.

---

## Mục lục

1. [Tổng quan Debtor](#1-tổng-quan-debtor)
2. [Entity Design](#2-entity-design)
3. [Create Debtor Flow](#3-create-debtor-flow)
4. [View Debtor Flow](#4-view-debtor-flow)
5. [Record Payment Flow](#5-record-payment-flow)
6. [Update/Delete Debtor Flow](#6-updatedelete-debtor-flow)
7. [Debt Reports](#7-debt-reports)
8. [Integration with Orders](#8-integration-with-orders)

---

## 1. Tổng quan Debtor

### Context - Nghiệp vụ công nợ HKD Việt Nam

Đối với hộ kinh doanh Việt Nam, đặc biệt **tạp hóa, VLXD, nông thôn**:

- Khách quen thường **mua chịu** (ghi nợ) - rất phổ biến
- Mua trả sau cuối tháng/đầu tháng lương
- Owner cần track: *"Ai nợ, nợ bao nhiêu, đã trả đến đâu"*
- Tin tưởng lẫn nhau - không cần hợp đồng chính thức

### Thuật ngữ

| Tiếng Việt | English | Code |
|------------|---------|------|
| Hồ sơ công nợ | Debtor Profile | `Debtor` |
| Số dư | Balance | `CurrentBalance` |
| Đang nợ | Outstanding Debt | `CurrentBalance < 0` |
| Có credit (trả trước) | Credit Balance | `CurrentBalance > 0` |
| Hết nợ | Cleared | `CurrentBalance = 0` |
| Giới hạn nợ | Credit Limit | `CreditLimit` |
| Giao dịch trả nợ | Payment Transaction | `DebtorPaymentTransaction` |

### Balance Concept

```
CurrentBalance (Số dư):
├── Negative (-) = Khách đang NỢ
│   Ví dụ: -500,000đ = Nợ 500k
├── Zero (0) = Hết nợ, không credit
│   Ví dụ: 0đ = Balance rỗng
└── Positive (+) = Khách có CREDIT (trả trước/dư)
    Ví dụ: +200,000đ = Có 200k credit
```

**Công thức tính**:
```
CurrentBalance = Tổng tiền đã trả - Tổng tiền mua chịu

Khi mua chịu:   CurrentBalance -= OrderDebtAmount
Khi trả nợ:     CurrentBalance += PaymentAmount
```

---

## 2. Entity Design

### Database Schema

```sql
-- =============================================
-- DEBTORS TABLE (Hồ sơ công nợ)
-- =============================================
CREATE TABLE Debtors (
    DebtorId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    BusinessLocationId INT NOT NULL COMMENT 'Thuộc location nào',
    
    -- Thông tin khách hàng
    Name VARCHAR(255) NOT NULL COMMENT 'Tên khách quen',
    Phone VARCHAR(20) DEFAULT NULL COMMENT 'SĐT (optional)',
    Address TEXT DEFAULT NULL COMMENT 'Địa chỉ (optional)', 
    Notes TEXT DEFAULT NULL COMMENT 'Ghi chú',
    
    -- Công nợ
    CreditLimit DECIMAL(15,2) DEFAULT NULL COMMENT 'Giới hạn nợ (NULL = unlimited)',
    CurrentBalance DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'Số dư: âm=nợ, dương=credit',
    
    -- Status
    IsActive BOOLEAN NOT NULL DEFAULT TRUE,
    DeletedAt DATETIME DEFAULT NULL COMMENT 'Soft delete',
    
    -- Audit
    CreatedByUserId CHAR(36) NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- Indexes & FKs
    CONSTRAINT fk_debtor_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    INDEX idx_debtor_location (BusinessLocationId),
    INDEX idx_debtor_name (Name),
    INDEX idx_debtor_phone (Phone),
    INDEX idx_debtor_balance (CurrentBalance),
    INDEX idx_debtor_active (IsActive)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- DEBTOR PAYMENT TRANSACTIONS TABLE (Lịch sử trả nợ)
-- =============================================
CREATE TABLE DebtorPaymentTransactions (
    TransactionId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    DebtorId BIGINT NOT NULL,
    
    -- Thanh toán
    Amount DECIMAL(15,2) NOT NULL COMMENT 'Số tiền trả (luôn dương)',
    PaymentMethod VARCHAR(20) NOT NULL COMMENT 'cash, bank',
    Notes TEXT DEFAULT NULL COMMENT 'Ghi chú',
    
    -- Balance snapshot
    BalanceBefore DECIMAL(15,2) NOT NULL COMMENT 'Balance trước khi trả',
    BalanceAfter DECIMAL(15,2) NOT NULL COMMENT 'Balance sau khi trả',
    
    -- Audit
    CreatedByUserId CHAR(36) NOT NULL,
    PaidAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_payment_debtor FOREIGN KEY (DebtorId) 
        REFERENCES Debtors(DebtorId),
    INDEX idx_payment_debtor (DebtorId),
    INDEX idx_payment_date (PaidAt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### Entity Classes

```csharp
public class Debtor
{
    public long DebtorId { get; set; }
    public int BusinessLocationId { get; set; }
    
    // Customer Info
    public string Name { get; set; } = null!;
    public string? Phone { get; set; }
    public string? Address { get; set; }
    public string? Notes { get; set; }
    
    // Debt
    public decimal? CreditLimit { get; set; }
    public decimal CurrentBalance { get; set; }
    
    // Status
    public bool IsActive { get; set; }
    public DateTime? DeletedAt { get; set; }
    
    // Audit
    public Guid CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime UpdatedAt { get; set; }
    
    // Navigation
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
    public virtual User CreatedByUser { get; set; } = null!;
    public virtual ICollection<DebtorPaymentTransaction> PaymentTransactions { get; set; } = new List<DebtorPaymentTransaction>();
    public virtual ICollection<Order> Orders { get; set; } = new List<Order>();
}

public class DebtorPaymentTransaction
{
    public long TransactionId { get; set; }
    public long DebtorId { get; set; }
    
    // Payment
    public decimal Amount { get; set; }
    public string PaymentMethod { get; set; } = null!;
    public string? Notes { get; set; }
    
    // Balance snapshot
    public decimal BalanceBefore { get; set; }
    public decimal BalanceAfter { get; set; }
    
    // Audit
    public Guid CreatedByUserId { get; set; }
    public DateTime PaidAt { get; set; }
    
    // Navigation
    public virtual Debtor Debtor { get; set; } = null!;
    public virtual User CreatedByUser { get; set; } = null!;
}
```

---

## 3. Create Debtor Flow

### Use Case

Owner tạo hồ sơ công nợ cho khách quen để có thể ghi nợ khi mua hàng.

### Sequence Diagram

```
┌─────────┐     ┌─────────┐     ┌─────────────┐     ┌──────────┐
│  Owner  │     │  App    │     │  Backend    │     │    DB    │
└────┬────┘     └────┬────┘     └──────┬──────┘     └────┬─────┘
     │               │                 │                 │
     │ Click "Thêm   │                 │                 │
     │  khách quen"  │                 │                 │
     │──────────────►│                 │                 │
     │               │                 │                 │
     │ Nhập thông tin│                 │                 │
     │ - Tên         │                 │                 │
     │ - SĐT         │                 │                 │
     │ - Limit (opt) │                 │                 │
     │──────────────►│                 │                 │
     │               │                 │                 │
     │ Submit        │ POST /debtors   │                 │
     │──────────────►│────────────────►│                 │
     │               │                 │                 │
     │               │                 │ Validate:       │
     │               │                 │ - IsOwner?      │
     │               │                 │ - Unique phone? │
     │               │                 │                 │
     │               │                 │ Create Debtor   │
     │               │                 │ Balance = 0     │
     │               │                 │────────────────►│
     │               │                 │◄────────────────│
     │               │                 │                 │
     │               │◄────────────────│                 │
     │ Debtor created│                 │                 │
     │◄──────────────│                 │                 │
```

### API Contract

```yaml
POST /api/v1/debtors
Authorization: Bearer {token}

Request:
{
  "businessLocationId": 1,
  "name": "Anh Ba",           # Required
  "phone": "0901234567",      # Optional - dùng để suggest
  "address": "123 Nguyễn Văn A, Q.1",  # Optional
  "creditLimit": 5000000,     # Optional - null = unlimited
  "notes": "Khách quen, mua xi măng thường xuyên"
}

Response (201 Created):
{
  "debtorId": 45,
  "businessLocationId": 1,
  "name": "Anh Ba",
  "phone": "0901234567",
  "address": "123 Nguyễn Văn A, Q.1",
  "creditLimit": 5000000,
  "currentBalance": 0,
  "outstandingDebt": 0,
  "isActive": true,
  "createdAt": "2026-02-25T10:30:00Z"
}
```

### Business Rules

#### **RULE-DEBTOR-01: Chỉ Owner tạo được Debtor**

```csharp
var assignment = await _unitOfWork.UserLocationAssignments
    .GetByUserAndLocationAsync(userId, request.BusinessLocationId);
    
if (assignment == null || !assignment.IsOwner)
    throw new ForbiddenException("Only owner can create debtors");
```

#### **RULE-DEBTOR-02: Phone unique trong location (nếu có)**

```csharp
if (!string.IsNullOrEmpty(request.Phone))
{
    var existing = await _unitOfWork.Debtors
        .FindAsync(d => d.BusinessLocationId == request.BusinessLocationId 
                     && d.Phone == request.Phone 
                     && d.DeletedAt == null);
    
    if (existing != null)
        throw new ConflictException($"Phone {request.Phone} already exists");
}
```

#### **RULE-DEBTOR-03: Balance bắt đầu = 0**

```csharp
var debtor = new Debtor
{
    BusinessLocationId = request.BusinessLocationId,
    Name = request.Name,
    Phone = request.Phone,
    Address = request.Address,
    CreditLimit = request.CreditLimit,  // null = unlimited
    CurrentBalance = 0,  // Always start at 0
    IsActive = true,
    CreatedByUserId = userId,
    CreatedAt = DateTime.UtcNow
};
```

---

## 4. View Debtor Flow

### List Debtors

```yaml
GET /api/v1/debtors?locationId=1&hasDebt=true&search=anh
Authorization: Bearer {token}

Query Parameters:
- locationId (required): Business location ID
- hasDebt (optional): true = chỉ lấy người đang nợ (balance < 0)
- search (optional): Tìm theo tên hoặc SĐT
- page (optional): Page number (default: 1)
- pageSize (optional): Items per page (default: 20)
- sortBy (optional): name, balance, createdAt (default: name)
- sortDir (optional): asc, desc (default: asc)

Response:
{
  "items": [
    {
      "debtorId": 45,
      "name": "Anh Ba",
      "phone": "0901234567",
      "currentBalance": -1500000,
      "outstandingDebt": 1500000,    # abs(min(0, balance))
      "creditLimit": 5000000,
      "lastOrderDate": "2026-02-20",
      "lastPaymentDate": "2026-02-15"
    },
    {
      "debtorId": 46,
      "name": "Chị Lan",
      "phone": "0909876543",
      "currentBalance": 200000,       # Có credit
      "outstandingDebt": 0,
      "creditLimit": null,            # Unlimited
      "lastOrderDate": "2026-02-24",
      "lastPaymentDate": "2026-02-24"
    }
  ],
  "totalCount": 25,
  "page": 1,
  "pageSize": 20,
  "totalDebt": 15000000   # Tổng nợ toàn location
}
```

### Debtor Detail

```yaml
GET /api/v1/debtors/45
Authorization: Bearer {token}

Response:
{
  "debtorId": 45,
  "businessLocationId": 1,
  "name": "Anh Ba",
  "phone": "0901234567",
  "address": "123 Nguyễn Văn A, Q.1",
  "creditLimit": 5000000,
  "currentBalance": -1500000,
  "outstandingDebt": 1500000,
  "notes": "Khách quen, mua xi măng",
  "isActive": true,
  "createdAt": "2026-01-15T08:00:00Z",
  
  # Lịch sử mua hàng (ghi nợ)
  "recentOrders": [
    {
      "orderId": 1001,
      "orderDate": "2026-02-20T14:30:00Z",
      "totalAmount": 2000000,
      "debtAmount": 500000,
      "paidAmount": 1500000,
      "status": "completed"
    }
  ],
  
  # Lịch sử trả nợ
  "recentPayments": [
    {
      "transactionId": 101,
      "amount": 1000000,
      "paymentMethod": "cash",
      "paidAt": "2026-02-15T10:00:00Z",
      "notes": "Trả một phần",
      "createdByName": "Nguyễn Văn A"
    }
  ],
  
  # Thống kê
  "statistics": {
    "totalOrders": 15,
    "totalPurchaseAmount": 25000000,
    "totalPaidAmount": 23500000,
    "oldestUnpaidOrder": "2026-02-01"
  }
}
```

---

## 5. Record Payment Flow

### Use Case

Khi khách trả nợ, Owner hoặc Employee ghi nhận thanh toán.

### Sequence Diagram

```markdown
┌──────────────┐     ┌─────────┐     ┌─────────────┐     ┌──────────┐
│Owner/Employee│     │  App    │     │  Backend    │     │    DB    │
└──────┬───────┘     └───┬─────┘     └─────┬───────┘     └───┬──────┘
       │                 │                 │                 │
       │ Chọn debtor     │                 │                 │
       │────────────────►│                 │                 │
       │                 │                 │                 │
       │ Hiển thị:       │                 │                 │
       │ "Anh Ba"        │                 │                 │
       │ Nợ: 1,500,000đ  │                 │                 │
       │◄────────────────│                 │                 │
       │                 │                 │                 │
       │ Nhập số tiền:   │                 │                 │
       │ 1,000,000đ      │                 │                 │
       │ Method: Cash    │                 │                 │
       │────────────────►│                 │                 │
       │                 │                 │                 │
       │ Confirm         │ POST /debtors   │                 │
       │────────────────►│ /{id}/payments  │                 │
       │                 │────────────────►│                 │
       │                 │                 │                 │
       │                 │                 │ Create          │
       │                 │                 │ Transaction     │
       │                 │                 │────────────────►│
       │                 │                 │                 │
       │                 │                 │ Update Debtor   │
       │                 │                 │ Balance += amt  │
       │                 │                 │────────────────►│
       │                 │                 │◄────────────────│
       │                 │                 │                 │
       │                 │◄────────────────│                 │
       │ Payment recorded│                 │                 │
       │◄────────────────│                 │                 │
```

### API Contract

```yaml
POST /api/v1/debtors/45/payments
Authorization: Bearer {token}

Request:
{
  "amount": 1000000,          # Số tiền trả (luôn dương)
  "paymentMethod": "cash",    # cash | bank
  "notes": "Trả một phần, còn 500k"
}

Response (201 Created):
{
  "transactionId": 102,
  "debtorId": 45,
  "amount": 1000000,
  "paymentMethod": "cash",
  "balanceBefore": -1500000,
  "balanceAfter": -500000,
  "outstandingDebtAfter": 500000,
  "paidAt": "2026-02-25T14:00:00Z",
  "createdByName": "Nguyễn Văn A"
}
```

### Business Rules

#### **RULE-PAYMENT-01: Amount phải dương**

```csharp
if (request.Amount <= 0)
    throw new ValidationException("Payment amount must be positive");
```

#### **RULE-PAYMENT-02: Cho phép trả dư (tạo credit)**

```csharp
// Không validate amount vs outstanding debt
// Khách có thể trả trước nhiều hơn nợ → tạo credit
var balanceBefore = debtor.CurrentBalance;
debtor.CurrentBalance += request.Amount;
var balanceAfter = debtor.CurrentBalance;

// Ví dụ: 
// Debtor nợ 500k (balance = -500,000)
// Trả 700k
// Balance mới = -500,000 + 700,000 = +200,000 (có credit 200k)
```

#### **RULE-PAYMENT-03: Lưu balance snapshot**

```csharp
var transaction = new DebtorPaymentTransaction
{
    DebtorId = debtor.DebtorId,
    Amount = request.Amount,
    PaymentMethod = request.PaymentMethod,
    Notes = request.Notes,
    BalanceBefore = balanceBefore,   // Snapshot
    BalanceAfter = balanceAfter,     // Snapshot
    CreatedByUserId = currentUserId,
    PaidAt = DateTime.UtcNow
};
```

#### **RULE-PAYMENT-04: Owner + Employee đều được ghi nhận**

```csharp
// Cả Owner và Employee đều có quyền record payment
// (Đã thống nhất trong phân tích Roles & Permissions)
var assignment = await _unitOfWork.UserLocationAssignments
    .GetByUserAndLocationAsync(userId, debtor.BusinessLocationId);
    
if (assignment == null || !assignment.IsActive)
    throw new ForbiddenException("No access to this location");
// Không cần check IsOwner
```

---

## 6. Update/Delete Debtor Flow

### Update Debtor

```yaml
PUT /api/v1/debtors/45
Authorization: Bearer {token}

Request:
{
  "name": "Anh Ba (Xi Măng)",    # Update tên
  "phone": "0901234567",
  "address": "456 Đường mới, Q.2",
  "creditLimit": 10000000,       # Tăng limit
  "notes": "Khách VIP"
}

Response (200 OK):
{
  "debtorId": 45,
  "name": "Anh Ba (Xi Măng)",
  "phone": "0901234567",
  "address": "456 Đường mới, Q.2",
  "creditLimit": 10000000,
  "currentBalance": -500000,
  "updatedAt": "2026-02-25T15:00:00Z"
}
```

**Rule**: Chỉ Owner được update.

### Delete (Soft Delete) Debtor

```yaml
DELETE /api/v1/debtors/45
Authorization: Bearer {token}

Response (204 No Content)
```

**Rules**:

- Chỉ Owner được xóa
- Soft delete (set DeletedAt)
- Phải hết nợ mới được xóa (hoặc confirm forgivable)

```csharp
if (debtor.CurrentBalance < 0)
{
    throw new ValidationException(
        $"Cannot delete debtor with outstanding debt of {Math.Abs(debtor.CurrentBalance):N0}đ. " +
        "Please clear the debt first or use force delete.");
}

debtor.DeletedAt = DateTime.UtcNow;
debtor.IsActive = false;
```

### Force Delete (Xóa khi còn nợ)

```yaml
DELETE /api/v1/debtors/45?force=true&reason=bad_debt
Authorization: Bearer {token}

Query Parameters:
- force: true
- reason: bad_debt | customer_gone | owner_forgave

Response (204 No Content)
```

```csharp
if (request.Force)
{
    // Log for audit
    _logger.LogWarning($"Force deleted debtor {debtorId} with balance {debtor.CurrentBalance}. Reason: {request.Reason}");
    
    // Có thể tạo record riêng cho bad debt reporting
    await CreateBadDebtRecordAsync(debtor, request.Reason);
}

debtor.DeletedAt = DateTime.UtcNow;
debtor.IsActive = false;
```

---

## 7. Debt Reports

### Location Debt Summary

```yaml
GET /api/v1/debtors/summary?locationId=1
Authorization: Bearer {token}

Response:
{
  "businessLocationId": 1,
  "totalDebtors": 45,
  "debtorsWithDebt": 28,          # Đang có người nợ
  "debtorsWithCredit": 5,         # Có credit
  "totalOutstandingDebt": 15000000,   # Tổng nợ
  "totalCredit": 800000,              # Tổng credit
  "netDebt": 14200000,                # Outstanding - Credit
  
  "topDebtors": [
    {
      "debtorId": 45,
      "name": "Anh Ba",
      "outstandingDebt": 5000000,
      "lastPaymentDate": "2026-02-15"
    },
    {
      "debtorId": 52,
      "name": "Công ty ABC",
      "outstandingDebt": 3500000,
      "lastPaymentDate": "2026-02-10"
    }
  ],
  
  "overdueDebtors": [   # Nợ quá 30 ngày không thanh toán
    {
      "debtorId": 60,
      "name": "Anh Tư",
      "outstandingDebt": 2000000,
      "daysSinceLastPayment": 45
    }
  ]
}
```

### Debt Aging Report

```yaml
GET /api/v1/debtors/aging?locationId=1
Authorization: Bearer {token}

Response:
{
  "businessLocationId": 1,
  "reportDate": "2026-02-25",
  "aging": {
    "current": {           # 0-30 ngày
      "count": 15,
      "amount": 5000000
    },
    "days30to60": {
      "count": 8,
      "amount": 4000000
    },
    "days60to90": {
      "count": 3,
      "amount": 3000000
    },
    "over90Days": {
      "count": 2,
      "amount": 3000000
    }
  },
  "totalOutstanding": 15000000
}
```

---

## 8. Integration with Orders

### Create Order with Debt

Khi tạo order với `paymentMethod = debt` hoặc `mixed`:

```csharp
// 1. Validate debtor exists
if (request.DebtorId == null)
    throw new ValidationException("Debt payment requires a debtor");

var debtor = await _unitOfWork.Debtors.GetByIdAsync(request.DebtorId.Value);
if (debtor == null || !debtor.IsActive)
    throw new NotFoundException("Debtor not found or inactive");

// 2. Check credit limit (soft warning)
var currentDebt = Math.Abs(Math.Min(0, debtor.CurrentBalance));
var newDebt = request.PaymentMethod == "debt" 
    ? order.TotalAmount 
    : order.TotalAmount - request.PaidAmount;  // mixed
var projectedDebt = currentDebt + newDebt;

if (debtor.CreditLimit.HasValue && projectedDebt > debtor.CreditLimit.Value)
{
    response.Warnings.Add(new Warning
    {
        Code = "DEBT_OVER_LIMIT",
        Message = $"Vượt giới hạn nợ: {projectedDebt:N0}đ / {debtor.CreditLimit:N0}đ"
    });
}

// 3. Use credit first (if any)
decimal debtToRecord = newDebt;
if (debtor.CurrentBalance > 0)
{
    var creditUsed = Math.Min(debtor.CurrentBalance, newDebt);
    debtToRecord = newDebt - creditUsed;
    response.Info.Add($"Đã trừ {creditUsed:N0}đ từ credit có sẵn");
}

// 4. Update debtor balance
debtor.CurrentBalance -= newDebt;

// 5. Save order with debtor reference
order.DebtorId = debtor.DebtorId;
order.DebtAmount = debtToRecord;
```

### Cancel Order with Debt - Reverse Balance

```csharp
// Khi cancel order có ghi nợ → hoàn lại balance
if (order.DebtAmount > 0 && order.DebtorId.HasValue)
{
    var debtor = await _unitOfWork.Debtors.GetByIdAsync(order.DebtorId.Value);
    debtor.CurrentBalance += order.DebtAmount;  // Hoàn lại
    
    // Log for audit
    _logger.LogInformation($"Reversed debt {order.DebtAmount:N0}đ for debtor {debtor.DebtorId} due to order {order.OrderId} cancellation");
}

order.Status = OrderStatus.Cancelled;
order.CancelledAt = DateTime.UtcNow;
order.CancelReason = request.Reason;
```

---

## 9. API Endpoints Summary

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/debtors` | Tạo debtor mới | Owner |
| `GET` | `/api/debtors` | List debtors | Owner, Employee |
| `GET` | `/api/debtors/{id}` | Debtor detail | Owner, Employee |
| `PUT` | `/api/debtors/{id}` | Update debtor | Owner |
| `DELETE` | `/api/debtors/{id}` | Soft delete | Owner |
| `POST` | `/api/debtors/{id}/payments` | Record payment | Owner, Employee |
| `GET` | `/api/debtors/{id}/payments` | Payment history | Owner, Employee |
| `GET` | `/api/debtors/summary` | Debt summary | Owner |
| `GET` | `/api/debtors/aging` | Aging report | Owner |

---

## 10. UI States

### Debtor Card Display

```markdown
┌─────────────────────────────────────────────────────────┐
│  👤 Anh Ba                                   📞 0901...│
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [State: Đang nợ]                                       │
│     Nợ: 1,500,000đ                                      │
│  Limit: 5,000,000đ                                      │
│  ━━━━━━━━━━━━━━━░░░░░░░░░░  30%                         │
│                                                         │
│  Đơn gần nhất: 20/02/2026                               │
│  Trả gần nhất: 15/02/2026                               │
│                                                         │
│  [Thu tiền]  [Xem chi tiết]                             │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  👤 Chị Lan                                  📞 0909...│
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [State: Có credit]                                     │
│     Dư: 200,000đ                                        │
│                                                         │
│  [Xem chi tiết]                                         │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│  👤 Anh Năm                                  📞 0908...│
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [State: Hết nợ]                                        │
│     Balance: 0đ                                         │
│                                                         │
│  [Xem chi tiết]                                         │
└─────────────────────────────────────────────────────────┘
```

### Balance States

| CurrentBalance | State | Color | Icon |
|----------------|-------|-------|------|
| `< 0` | Đang nợ | 🔴 Red | ⚠️ |
| `= 0` | Hết nợ | ⚪ Gray | ✓ |
| `> 0` | Có credit | 🟢 Green | 💰 |

### Credit Limit Bar

```markdown
Nợ: 1,500,000đ / Limit: 5,000,000đ
━━━━━━━━━━━━━━━░░░░░░░░░░░  30%  (Xanh)

Nợ: 4,500,000đ / Limit: 5,000,000đ  
━━━━━━━━━━━━━━━━━━━━━━━━━━░  90%  (Cam - Warning)

Nợ: 6,000,000đ / Limit: 5,000,000đ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 120% (Đỏ - Over limit)
```
