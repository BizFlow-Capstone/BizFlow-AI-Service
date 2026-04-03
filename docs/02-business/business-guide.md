# BizFlow Business Guide

> **Mục đích**: Tài liệu tổng hợp nghiệp vụ, quy tắc kinh doanh cho BizFlow Platform.

---

## Mục lục

1. [Tổng quan dự án](#1-tổng-quan-dự-án)
2. [Thuật ngữ nghiệp vụ](#2-thuật-ngữ-nghiệp-vụ)
3. [User Roles & Permissions](#3-user-roles--permissions)
4. [Business Rules](#4-business-rules)
5. [Thông tư 152/2025/TT-BTC](#5-thông-tư-1522025tt-btc)
6. [Features Overview](#6-features-overview)

---

## 1. Tổng quan Dự án

- **Target Users**: Hộ kinh doanh Việt Nam (revenue < 1 tỷ VND/năm)
- **Pain Points**:
  - Quản lý thủ công (sổ tay, Excel) dễ sai sót
  - Đơn hàng qua điện thoại/Zalo → phải ghi nhớ
  - Thông tư 152: Bắt buộc tự kê khai thuế (không còn thuế khoán)
- **Solution**: Platform quản lý đơn hàng + kho + nợ + báo cáo kế toán + AI voice order

### Tech Stack

- **Backend**: ASP.NET Core 8 + MySQL
- **Frontend**: Flutter (Mobile) + ReactJS (Web)
- **AI Service**: Python (STT + RAG + LLM)

---

## 2. Thuật ngữ Nghiệp vụ

### Đối tượng

| Tiếng Việt | English | Code | Mô tả |
|------------|---------|------|-------|
| Hộ kinh doanh | Household Business | - | Doanh thu < 1 tỷ/năm |
| Chủ hộ KD | Business Owner | `Role: User` | Người sở hữu |
| Nhân viên | Employee | `Role: User` (via Hire) | Được chủ hộ mời |
| Quản trị viên | Admin | `Role: Admin` | Quản lý platform |
| Tư vấn viên | Consultant | `Role: Consultant` | Quản lý templates kế toán |
| Khách hàng | Customer | `customers` | Khách quen, có thể ghi nợ |

### Cấu trúc

| Tiếng Việt | English | Table | Mô tả |
|------------|---------|-------|-------|
| Địa điểm KD | Business Location | `BusinessLocations` | Cửa hàng/kho |
| Loại hình KD | Business Type | `BusinessTypes` | Bán lẻ, dịch vụ, F&B... |

**Note**: 1 User có thể có nhiều Locations. Mỗi Location có data riêng (multi-tenant).

### Product Management

| Tiếng Việt | English | Table/Field | Mô tả |
|------------|---------|-------------|-------|
| Sản phẩm | Product | `Products` | Hàng hóa |
| SKU | Stock Keeping Unit | `SKU` | Mã tracking |
| Đơn vị tính nhỏ nhất | Base Unit | `Unit` | Bao, kg, thùng... |
| Giá vốn | Cost Price | `CostPrice` | Giá nhập |
| Đơn vị bán | Sale Item | `SaleItems` | 1 product nhiều units |
| Tồn kho | Stock | `Stock` | Số lượng hiện có |
| Giá bán ra của sản phẩm | Product Price | `ProductPricePolicy` | Giá cả có thể thay đổi theo thị trường |

**Note**: Product là quản lí món hàng trong inventory (business location), chứ các thông tin chung. Sale items là quản lí  món hàng trong việc bán hàng (Order), gồm đơn vị (base unit và các unit khác) và giá bán của đơn vị đó. Đối với sale item của ngành dịch vụ và F&B thì không có quản lí tồn kho.

Ví dụ:

```merdmaid
Product: Xi măng Hà Tiên
├─ Sale Item 1: Bao (50kg) - Giá: 95,000đ (base unit)
├─ Sale Item 2: Bao (50kg) x10 - Giá: 93,000đ/bao (tier)
└─ Stock: 150 bao
```

### Order Management

| Thuật ngữ (VI) | Tiếng Anh | Database/Code | Mô tả |
|----------------|-----------|---------------|-------|
| Đơn hàng | Order | `Orders` | Giao dịch bán hàng |
| Chi tiết đơn hàng | Order Detail | `OrderDetails` | Từng sản phẩm trong đơn |
| Đơn hàng nháp | Draft Order | `Status: null` | Đơn do AI tạo, chờ user confirm |
| Xác nhận đơn | Confirm Order | `Status: Pending` | User đã review và approve |
| Thanh toán | Payment | - | Phương thức thanh toán |
| Thanh toán tiền mặt | Cash Payment | `PaymentType: cash` | Khách trả tiền mặt ngay |
| Thanh toán qua bank | Bank Payment | `PaymentType: bank` | Khách trả chuyển khoản quan bank |
| Ghi nợ | Credit/Debt | `PaymentType: debt` | Khách mua chịu, trả sau |
| Hồ sơ công nợ | Debtor | `Debtor` | Khách hàng ghi nợ |
| Thanh toán công nợ | Debt Payment Transaction | `DebtorPaymentTransaction` | Giao dịch thanh toán nợ của khách hàng |
| Công nợ | Outstanding Debt | - | Tổng nợ chưa trả |

### 📊 Kho & Kế toán

| Tiếng Việt | English | Mô tả |
|------------|---------|-------|
| Nhập kho | Stock Import | Nhập hàng |
| Xuất kho | Stock Export | Trừ tự động khi bán |
| Phiếu mua hàng hóa không hóa đơn | Stock Import Template | Phiếu lưu thông tin mua hàng hóa không hóa đơn theo quy định |
| Sổ KT đơn giản | Simplified Accounting Book | Theo Thông tư 152 |
| Nhóm hộ kinh doanh | Business Household group | Chia theo doanh thu và phương thức nộp thuế |
| Bút toán | Accounting Entry | Ghi sổ Nợ/Có |

---

## 3. User Roles & Permissions

### 3.1 Roles Overview

Hệ thống có 3 roles chính trong table `Roles`:

| Role | Target User | Mô tả |
|------|-------------|-------|
| **User** | Chủ hộ KD / Nhân viên | Người dùng chính - quản lý cửa hàng |
| **Admin** | Quản trị BizFlow | Quản lý platform toàn diện |
| **Consultant** | Tư vấn viên | Hỗ trợ template kế toán, thông báo quy định |

**Lưu ý quan trọng**: Trong Role = User, phân biệt **Owner** vs **Employee** qua relationship:

```
User (Role = User)
├── Owner: Tạo & sở hữu BusinessLocation
│   └── Check: UserLocationAssignment.IsOwner = true
└── Employee: Được Owner mời làm việc
    └── Check: Hire record + UserLocationAssignment.IsOwner = false
```

### 3.2 Permission Matrix

#### Legend
- ✅ = Được phép
- ❌ = Không được phép
- 🔒 = Chỉ với data của mình (own data only)

#### Business Location Management

| Action | Owner | Employee | Admin | Consultant |
|--------|:-----:|:--------:|:-----:|:----------:|
| Tạo mới location | ✅ | ❌ | ❌ | ❌ |
| Xem thông tin location | ✅ | ✅ | ❌ | ❌ |
| Chỉnh sửa location info | ✅ | ❌ | ❌ | ❌ |
| Xóa/Deactivate location | ✅ | ❌ | ❌ | ❌ |

#### Employee Management (Hire)

| Action | Owner | Employee | Admin | Consultant |
|--------|:-----:|:--------:|:-----:|:----------:|
| Mời nhân viên (Hire) | ✅ | ❌ | ❌ | ❌ |
| Xem danh sách nhân viên | ✅ | ❌ | ❌ | ❌ |
| Hủy/Xóa nhân viên | ✅ | ❌ | ❌ | ❌ |
| Assign nhân viên vào location | ✅ | ❌ | ❌ | ❌ |

#### Product & Inventory Management

| Action | Owner | Employee | Admin | Consultant |
|--------|:-----:|:--------:|:-----:|:----------:|
| Xem danh sách sản phẩm | ✅ | ✅ | ❌ | ❌ |
| Tạo sản phẩm mới | ✅ | ❌ | ❌ | ❌ |
| Chỉnh sửa sản phẩm | ✅ | ❌ | ❌ | ❌ |
| Xóa/Disable sản phẩm | ✅ | ❌ | ❌ | ❌ |
| Quản lý SaleItems (đơn vị bán) | ✅ | ❌ | ❌ | ❌ |
| Quản lý giá (PricePolicy) | ✅ | ❌ | ❌ | ❌ |
| Nhập kho (Import) | ✅ | ❌ | ❌ | ❌ |
| Xem tồn kho | ✅ | ✅ | ❌ | ❌ |

#### Order Management

| Action | Owner | Employee | Admin | Consultant |
|--------|:-----:|:--------:|:-----:|:----------:|
| Tạo đơn hàng (thủ công) | ✅ | ✅ | ❌ | ❌ |
| Tạo đơn qua AI voice | ✅ | ✅ | ❌ | ❌ |
| Xác nhận draft order từ AI | ✅ | ✅ | ❌ | ❌ |
| Xem tất cả đơn hàng trong location | ✅ | ✅ | ❌ | ❌ |
| Sửa đơn hàng của mình | ✅ | 🔒 | ❌ | ❌ |
| Sửa đơn hàng của người khác | ✅ | ❌ | ❌ | ❌ |
| Hủy đơn hàng của mình | ✅ | 🔒 | ❌ | ❌ |
| Hủy đơn hàng của người khác | ✅ | ❌ | ❌ | ❌ |

#### Debt Management (Công nợ)

| Action | Owner | Employee | Admin | Consultant |
|--------|:-----:|:--------:|:-----:|:----------:|
| Tạo hồ sơ công nợ (Debtor) | ✅ | ❌ | ❌ | ❌ |
| Xem danh sách công nợ | ✅ | ✅ | ❌ | ❌ |
| Xem chi tiết công nợ | ✅ | ✅ | ❌ | ❌ |
| Ghi nhận thanh toán nợ | ✅ | ✅ | ❌ | ❌ |
| Chỉnh sửa thông tin Debtor | ✅ | ❌ | ❌ | ❌ |
| Xóa Debtor | ✅ | ❌ | ❌ | ❌ |

#### Reports & Analytics

| Action | Owner | Employee | Admin | Consultant |
|--------|:-----:|:--------:|:-----:|:----------:|
| Xem báo cáo doanh thu (location) | ✅ | ❌ | ❌ | ❌ |
| Xem thống kê bán hàng | ✅ | ❌ | ❌ | ❌ |
| Xuất sổ kế toán (TT152) | ✅ | ❌ | ❌ | ❌ |
| Xem platform analytics | ❌ | ❌ | ✅ | ❌ |

#### Admin Features

| Action | Owner | Employee | Admin | Consultant |
|--------|:-----:|:--------:|:-----:|:----------:|
| Quản lý tất cả User accounts | ❌ | ❌ | ✅ | ❌ |
| Activate/Deactivate accounts | ❌ | ❌ | ✅ | ❌ |
| Quản lý subscription pricing | ❌ | ❌ | ✅ | ❌ |
| System configuration | ❌ | ❌ | ✅ | ❌ |

#### Accounting Templates (Thông tư 152)

| Action | Owner | Employee | Admin | Consultant |
|--------|:-----:|:--------:|:-----:|:----------:|
| Xem template kế toán | ✅ | ✅ | ✅ | ✅ |
| Cập nhật template (TT152) | ❌ | ❌ | ✅ | ✅ |
| Tạo thông báo cập nhật quy định | ❌ | ❌ | ✅ | ✅ |

### 3.3 Authorization Rules

#### Multi-location Context

```csharp
// Employee chỉ được access các location mình được assign
var accessibleLocations = await _unitOfWork.UserLocationAssignments
    .GetByUserIdAsync(userId);
    
// Mọi request từ Employee phải validate location access
if (!accessibleLocations.Any(a => a.BusinessLocationId == requestLocationId))
    throw new ForbiddenException("No access to this location");
```

#### Own Data Restriction (🔒)

```csharp
// Employee chỉ sửa/hủy đơn do chính mình tạo
var order = await _unitOfWork.Orders.GetByIdAsync(orderId);
if (order.CreatedByUserId != currentUserId && !isOwner)
    throw new ForbiddenException("Can only modify your own orders");
```

#### Owner Validation

```csharp
// Kiểm tra user có phải Owner của location không
var assignment = await _unitOfWork.UserLocationAssignments
    .GetByUserAndLocationAsync(userId, locationId);
    
bool isOwner = assignment?.IsOwner == true;
```

## 4. Business Rules

### Pricing Rules

- **Multi-unit Pricing**: Sản phẩm có thể bán theo nhiều đơn vị (bao, thùng, tấn)

### Inventory Rules

- **Auto Deduction**: Khi order confirmed:
  - Nếu `track_inventory = true` → trừ stock
  - Nếu `false` → không trừ (dịch vụ, hàng không cần quản lý kho)
- **Low Stock Alert**: Stock < threshold → thông báo
- **Prevent Negative Stock**: Cảnh báo lúc tạo order nếu stock không đủ, vẫn cho tạo order

### Debt Rules

#### Tổng quan

Công nợ (debt/credit) là tính năng quan trọng cho HKD Việt Nam, đặc biệt **tạp hóa, VLXD, nông thôn** - nơi khách quen thường mua chịu.

#### Entities

```
Debtors (Hồ sơ công nợ)
├── DebtorId (PK, BIGINT)
├── BusinessLocationId (FK) ─── Thuộc location nào
├── Name ─────────────────────── Tên khách hàng
├── Phone ────────────────────── SĐT (optional)
├── Address ──────────────────── Địa chỉ (optional)
├── Notes ────────────────────── Ghi chú
├── CreditLimit ──────────────── Giới hạn nợ (nullable = unlimited)
├── CurrentBalance ───────────── Số dư hiện tại (âm = nợ, dương = có credit)
├── IsActive
└── CreatedAt, CreatedByUserId

DebtorPaymentTransactions (Lịch sử trả nợ)
├── TransactionId (PK, BIGINT)
├── DebtorId (FK)
├── Amount ───────────────────── Số tiền trả (luôn dương)
├── PaymentMethod ────────────── 'cash' | 'bank'
├── Notes ────────────────────── Ghi chú
├── PaidAt ───────────────────── Thời điểm trả
└── CreatedByUserId ──────────── Nhân viên ghi nhận
```

#### Rules

**RULE-DEBT-01: Chỉ Debtor đã đăng ký mới được ghi nợ**

```csharp
// Khi tạo order với PaymentType = 'debt'
if (request.PaymentType == PaymentType.Debt)
{
    if (request.DebtorId == null)
        throw new ValidationException("Debt payment requires a registered debtor");
        
    var debtor = await _unitOfWork.Debtors.GetByIdAsync(request.DebtorId.Value);
    if (debtor == null || !debtor.IsActive)
        throw new ValidationException("Debtor not found or inactive");
}
```

**RULE-DEBT-02: Credit Limit là soft limit (cảnh báo, không block)**

```csharp
// Khi tạo order ghi nợ
var newDebtAmount = order.TotalAmount;
var currentDebt = Math.Abs(Math.Min(0, debtor.CurrentBalance)); // Chỉ tính nợ âm
var projectedDebt = currentDebt + newDebtAmount;

if (debtor.CreditLimit.HasValue && projectedDebt > debtor.CreditLimit.Value)
{
    // Trả về warning nhưng vẫn cho phép tạo order
    response.Warnings.Add(new Warning
    {
        Code = "DEBT_OVER_LIMIT",
        Message = $"Khách {debtor.Name} sẽ nợ {projectedDebt:N0}đ, vượt limit {debtor.CreditLimit:N0}đ"
    });
}
// Order vẫn được tạo bình thường
```

**RULE-DEBT-03: Trả nợ theo tổng (không phải từng đơn)**

```csharp
// Ghi nhận thanh toán
var transaction = new DebtorPaymentTransaction
{
    DebtorId = request.DebtorId,
    Amount = request.Amount,    // Số tiền khách trả
    PaymentMethod = request.PaymentMethod,
    Notes = request.Notes,
    PaidAt = DateTime.UtcNow,
    CreatedByUserId = currentUserId
};

// Cập nhật balance của debtor
debtor.CurrentBalance += request.Amount;  // Balance tăng (bớt nợ)
```

**RULE-DEBT-04: Cho phép trả dư (balance dương)**

```csharp
// CurrentBalance có thể dương (credit) hoặc âm (nợ)
// Ví dụ:
//   -500,000  = đang nợ 500k
//   +200,000  = đang có credit 200k (trả trước)
//   0         = hết nợ, không credit

// Khi khách mua tiếp với PaymentType = 'debt':
if (debtor.CurrentBalance > 0)
{
    // Trừ vào credit trước
    var creditUsed = Math.Min(debtor.CurrentBalance, order.TotalAmount);
    var remainingDebt = order.TotalAmount - creditUsed;
    debtor.CurrentBalance -= order.TotalAmount;
}
else
{
    // Ghi nợ thêm
    debtor.CurrentBalance -= order.TotalAmount;
}
```

**RULE-DEBT-05: Tính Outstanding Debt**

```csharp
// Tổng nợ của 1 debtor
var outstandingDebt = Math.Abs(Math.Min(0, debtor.CurrentBalance));

// Tổng nợ của 1 location
var totalLocationDebt = await _context.Debtors
    .Where(d => d.BusinessLocationId == locationId && d.CurrentBalance < 0)
    .SumAsync(d => Math.Abs(d.CurrentBalance));
```

#### Flow Diagrams

**Flow: Tạo Debtor Profile**

```
Owner/Employee tạo debtor
        │
        ▼
┌─────────────────────────┐
│ Input:                  │
│ - Name (required)       │
│ - Phone (optional)      │
│ - CreditLimit (optional)│
└───────────┬─────────────┘
            │
            ▼
    [Validate unique phone in location]
            │
            ▼
    [Create Debtor với CurrentBalance = 0]
            │
            ▼
        ✅ Done
```

**Flow: Order với Ghi nợ**

```
Tạo Order với PaymentType = 'debt'
        │
        ▼
┌─────────────────────────┐
│ Validate DebtorId       │◄─── RULE-DEBT-01
│ (bắt buộc có)           │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Check Credit Limit      │◄─── RULE-DEBT-02
│ (warning nếu vượt)      │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Create Order            │
│ OrderStatus = 'pending' │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Update Debtor           │◄─── RULE-DEBT-04
│ CurrentBalance -= Total │
└───────────┬─────────────┘
            │
            ▼
        ✅ Done
```

**Flow: Trả nợ**

```
Ghi nhận thanh toán nợ
        │
        ▼
┌─────────────────────────┐
│ Input:                  │
│ - DebtorId              │
│ - Amount (số tiền trả)  │
│ - PaymentMethod         │
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Create Transaction      │◄─── RULE-DEBT-03
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│ Update Debtor           │◄─── RULE-DEBT-04
│ CurrentBalance += Amount│
│ (có thể thành dương)    │
└───────────┬─────────────┘
            │
            ▼
        ✅ Done
```

#### UI Considerations

| Field | Hiển thị | Ý nghĩa |
|-------|----------|---------|
| `CurrentBalance < 0` | 🔴 Nợ 500,000đ | Khách đang nợ |
| `CurrentBalance = 0` | ⚪ Hết nợ | Không nợ, không credit |
| `CurrentBalance > 0` | 🟢 Dư 200,000đ | Khách đã trả trước/dư |

### Multi-tenancy Rules

- **Data Isolation**:

```csharp
// Mọi query phải filter theo business_location_id
.Where(p => p.BusinessLocationId == locationId)
.Where(p => !p.IsDeleted)  // Soft delete
```

- **Ownership Validation**: Service layer phải check

```csharp
var isOwner = await _unitOfWork.BusinessLocations
    .IsOwnerOfLocationAsync(userId, locationId);
if (!isOwner) throw new ForbiddenException();
```

## 5. Thông tư 152/2025/TT-BTC

### Tổng quan

- **Tên đầy đủ**: Thông tư 152/2025/TT-BTC hướng dẫn chế độ kế toán hộ kinh doanh
- **Hiệu lực**: 01/01/2026
- **Nội dung chính**:
  - HKD tự ghi chép sổ sách kế toán hoặc thuê dịch vụ
  - Lưu trữ tài liệu kế toán **ít nhất 5 năm** (điện tử hoặc giấy)
  - Phân loại **4 nhóm HKD** theo doanh thu và hình thức nộp thuế
  - Mỗi nhóm sử dụng bộ sổ kế toán và cách tính thuế khác nhau

### Phân loại Nhóm HKD

```markdown
┌───────────────────────────────────────────────────────────────────────┐
│                    PHÂN LOẠI THEO THÔNG TƯ 152                        │
├───────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  NHÓM 1: Doanh thu < 500 triệu/năm                                    │
│  └─ Không chịu thuế GTGT, TNCN                                        │
│  └─ Sổ: S1a-HKD                                                       │
│                                                                       │
│  NHÓM 2: Doanh thu 500 triệu → dưới 3 tỷ/năm                          │
│  └─ Thuế GTGT: % doanh thu theo ngành                                 │
│  └─ Thuế TNCN: Cách 1 (% DT) HOẶC Cách 2 (DT - CP) × 15%              │
│  └─ Sổ: S2a-HKD (cách 1) HOẶC S2b + S2c + S2d + S2e (cách 2)          │
│                                                                       │
│  NHÓM 3: Doanh thu 3 tỷ → dưới 50 tỷ/năm                              │
│  └─ Thuế GTGT: % doanh thu theo ngành                                 │
│  └─ Thuế TNCN: (DT - CP) × 17%                                        │
│  └─ Sổ: S2b + S2c + S2d + S2e                                         │
│                                                                       │
│  NHÓM 4: Doanh thu > 50 tỷ/năm                                        │
│  └─ Thuế GTGT: % doanh thu theo ngành                                 │
│  └─ Thuế TNCN: (DT - CP) × 20%                                        │
│  └─ Sổ: S2b + S2c + S2d + S2e                                         │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### Thuế và sổ sách

| Tiêu chí | Nhóm 1 (< 500tr) | Nhóm 2 (500tr - 3 tỷ) | Nhóm 3 (3 tỷ - 50 tỷ) | Nhóm 4 (> 50 tỷ) |
|-----------|-------------------|------------------------|------------------------|--------------------|
| **Thuế GTGT** | Không chịu thuế | DT × tỷ lệ % theo ngành | DT × tỷ lệ % theo ngành | DT × tỷ lệ % theo ngành |
| **Thuế TNCN** | Không chịu thuế | **Cách 1**: (DT - 500tr) × % ngành **HOẶC Cách 2**: (DT - CP) × 15% | (DT - CP) × 17% | (DT - CP) × 20% |
| **Khai thuế GTGT** | Thông báo DT theo quý | Theo quý | Theo quý | Theo tháng |
| **Khai thuế TNCN** | --- | Theo quý + Quyết toán năm (31/01 năm sau) | --- | --- |
| **Hóa đơn điện tử** | Không bắt buộc | Bắt buộc nếu DT > 1 tỷ | Bắt buộc | Bắt buộc |
| **Sổ kế toán** | S1a-HKD | S2a-HKD (cách 1) hoặc S2b+S2c+S2d+S2e (cách 2) | S2b+S2c+S2d+S2e | S2b+S2c+S2d+S2e |

### Tỷ lệ thuế GTGT theo ngành nghề

| Ngành nghề | Tỷ lệ GTGT |
|------------|-------------|
| --- | --- |

### Tỷ lệ thuế TNCN theo ngành nghề (Cách 1 - Nhóm 2)

> Áp dụng khi **không xác định được chi phí**: `(Doanh thu - 500 triệu) × tỷ lệ %`

| Ngành nghề | Tỷ lệ TNCN |
|------------|-------------|
| Phân phối, cung cấp hàng hóa | 0.5% |
| Sản xuất, vận tải, dịch vụ gắn với hàng hóa, xây dựng có bao thầu NVL | 1.5% |
| Dịch vụ, xây dựng không bao thầu NVL | 2% |
| Cung cấp sản phẩm/dịch vụ nội dung số (game, phim, nhạc, quảng cáo số) | 5% |
| Cho thuê bất động sản (trừ kinh doanh lưu trú) | 5% |
| Các ngành còn lại | 1% |

### Thuế suất TNCN cố định theo nhóm (Cách 2 - Khi xác định được chi phí)

> Áp dụng khi **xác định được chi phí**: `(Doanh thu - Chi phí) × thuế suất`

| Nhóm | Doanh thu | Thuế suất TNCN |
|------|-----------|----------------|
| Nhóm 2 | 500 triệu - dưới 3 tỷ | 15% |
| Nhóm 3 | 3 tỷ - dưới 50 tỷ | 17% |
| Nhóm 4 | Trên 50 tỷ | 20% |

---

### Giải thích thuế

**Thuế GTGT (Giá trị gia tăng)**:

- Thuế gián thu tính trên doanh thu theo tỷ lệ % cố định theo ngành nghề
- Áp dụng phương pháp tính trực tiếp (**không khấu trừ đầu vào**)
- Chỉ áp dụng khi doanh thu ≥ 500 triệu/năm

**Thuế TNCN (Thu nhập cá nhân)**:

- **Cách 1** (không xác định được chi phí): Tính trên phần doanh thu vượt 500 triệu theo tỷ lệ % ngành nghề
- **Cách 2** (xác định được chi phí): Tính trên lợi nhuận thực tế (DT - CP) theo thuế suất cố định của nhóm

**Lưu ý**: Nhóm 2 được **chọn 1 trong 2 cách** tính thuế TNCN. Nhóm 3 và 4 **bắt buộc Cách 2**.

---

### Quy định đặc biệt: Nhiều ngành nghề / Nhiều địa điểm

> Theo Thông báo 85/TB-CT ngày 29/01/2026 của Cục Thuế

Khi HKD kinh doanh **nhiều ngành nghề hoặc nhiều địa điểm**:

1. **Mức trừ 500 triệu**: Chỉ được trừ **1 lần tổng cộng** (không phải mỗi ngành/địa điểm)
2. **Quyền lựa chọn**: Được chọn **1 ngành nghề hoặc 1 địa điểm** có lợi nhất để áp dụng mức trừ 500 triệu
3. **Trừ chưa đủ**: Nếu ngành/địa điểm đã chọn chưa trừ đủ 500 triệu → được tiếp tục chọn thêm ngành/địa điểm khác
4. **Cho thuê BĐS**: 
   - Thuế GTGT = DT × 5%
   - Thuế TNCN = (DT - 500 triệu) × 5%
   - Nhiều hợp đồng thuê → được chọn hợp đồng để trừ 500 triệu
   - Bên thuê khai/nộp thay → phải ghi rõ trong hợp đồng

**Ví dụ**:

```markdown
HKD có 2 ngành:
├─ Ngành A (bán hàng hóa): DT = 800 triệu
└─ Ngành B (dịch vụ):      DT = 300 triệu

Chọn Ngành A để trừ 500 triệu:
├─ Thuế TNCN Ngành A = (800tr - 500tr) × 0.5% = 1.5 triệu
└─ Thuế TNCN Ngành B = 300tr × 2% = 6 triệu (không được trừ nữa vì đã trừ đủ)
Tổng TNCN = 7.5 triệu
```

## 6. Features Overview

Tổng quan tính năng theo từng role và module.

### 6.1 User Features (Owner & Employee)

#### 🏪 Business Location Management

| Feature | Owner | Employee | Description |
|---------|:-----:|:--------:|-------------|
| Tạo địa điểm kinh doanh | ✅ | ❌ | Tạo cửa hàng/kho mới |
| Xem thông tin location | ✅ | ✅ | Tên, địa chỉ, mã số thuế |
| Chỉnh sửa location | ✅ | ❌ | Cập nhật thông tin |
| Xóa/Deactivate location | ✅ | ❌ | Soft delete |
| Chuyển đổi giữa locations | ✅ | ✅ | Multi-location support |

#### 👥 Employee Management (Hire)

| Feature | Owner | Employee | Description |
|---------|:-----:|:--------:|-------------|
| Mời nhân viên | ✅ | ❌ | Gửi lời mời qua ứng dụng |
| Xem danh sách nhân viên | ✅ | ❌ | List all employees |
| Assign nhân viên vào location | ✅ | ❌ | Phân công làm việc |
| Hủy quyền nhân viên | ✅ | ❌ | Revoke access |

#### 📦 Product & Inventory Management

| Feature | Owner | Employee | Description |
|---------|:-----:|:--------:|-------------|
| Xem danh sách sản phẩm | ✅ | ✅ | List products trong location |
| Tìm kiếm sản phẩm | ✅ | ✅ | Search by name, SKU |
| Tạo sản phẩm mới | ✅ | ❌ | Thêm sản phẩm vào catalog |
| Chỉnh sửa sản phẩm | ✅ | ❌ | Cập nhật tên, giá, ảnh |
| Xóa/Disable sản phẩm | ✅ | ❌ | Soft delete |
| Quản lý đơn vị bán (SaleItem) | ✅ | ❌ | Bao, thùng, kg... |
| Quản lý giá theo đơn vị | ✅ | ❌ | Price policies |
| Nhập kho (Import) | ✅ | ❌ | Ghi nhận nhập hàng |
| Xem tồn kho | ✅ | ✅ | Stock hiện tại |
| Xem lịch sử nhập kho | ✅ | ❌ | Import history |

#### 🛒 Order Management

| Feature | Owner | Employee | Description |
|---------|:-----:|:--------:|-------------|
| **Tạo đơn hàng (Manual)** | ✅ | ✅ | Chọn sản phẩm, số lượng |
| **Tạo đơn qua AI Voice** | ✅ | ✅ | Nói trực tiếp/up file record → AI parse |
| Xem draft từ AI | ✅ | ✅ | Review trước khi confirm |
| Chỉnh sửa draft | ✅ | ✅ | Thêm/bớt/sửa items |
| Xác nhận draft → Order | ✅ | ✅ | Create pending order |
| Xem danh sách đơn hàng | ✅ | ✅ | List orders |
| Xem chi tiết đơn | ✅ | ✅ | Order details |
| Sửa đơn hàng của mình | ✅ | 🔒 | Pending orders only |
| Sửa đơn hàng của người khác | ✅ | ❌ | Owner only |
| Hoàn tất đơn hàng (Complete) | ✅ | ✅ | Mark as completed |
| Hủy đơn của mình | ✅ | 🔒 | Pending orders only |
| Hủy đơn của người khác | ✅ | ❌ | Owner only |

#### 💳 Payment & Debt Management

| Feature | Owner | Employee | Description |
|---------|:-----:|:--------:|-------------|
| Thanh toán tiền mặt | ✅ | ✅ | Cash payment |
| Thanh toán chuyển khoản | ✅ | ✅ | Bank transfer |
| Ghi nợ (Debt) | ✅ | ✅ | 100% ghi nợ |
| Thanh toán hỗn hợp (Mixed) | ✅ | ✅ | Partial pay + auto debt/Cash + bank |
| Tạo hồ sơ công nợ (Debtor) | ✅ | ❌ | Đăng ký khách quen |
| Xem danh sách công nợ | ✅ | ✅ | List debtors |
| Xem chi tiết công nợ | ✅ | ✅ | Debtor detail + history |
| Ghi nhận thanh toán nợ | ✅ | ✅ | Record debt payment |
| Chỉnh sửa Debtor | ✅ | ❌ | Update info |
| Xóa Debtor | ✅ | ❌ | Soft delete |

#### 📊 Reports & Analytics

| Feature | Owner | Employee | Description |
|---------|:-----:|:--------:|-------------|
| Dashboard tổng quan | ✅ | ❌ | Overview metrics |
| Báo cáo doanh thu ngày/tuần/tháng | ✅ | ❌ | Revenue reports |
| Top sản phẩm bán chạy | ✅ | ❌ | Best sellers |
| Cảnh báo tồn kho thấp | ✅ | ❌ | Low stock alerts |
| Xuất sổ kế toán (TT152) | ✅ | ❌ | Accounting books |
| Dự báo doanh thu | ✅ | ❌ | Revenue forecast (AI) |
| Cảnh báo bất thường | ✅ | ❌ | Anomaly detection (AI) |

---

### 6.2 Admin Features

#### 👤 Account Management

| Feature | Description |
|---------|-------------|
| Xem tất cả user accounts | List all users |
| Tìm kiếm/Filter users | Search by name, email, status |
| Xem chi tiết profile | User info + locations |
| Activate/Deactivate account | Enable/disable user |
| View user activity logs | Audit trail |

#### 💰 Subscription Management

| Feature | Description |
|---------|-------------|
| Quản lý pricing plans | Define subscription tiers |
| Xem subscription status | User subscription info |
| Manual extend/cancel | Admin override |

#### 📈 Platform Analytics

| Feature | Description |
|---------|-------------|
| Dashboard tổng quan platform | Global metrics |
| Số lượng active users | DAU, MAU |
| Số lượng locations | Total business locations |
| Doanh thu platform | Revenue analytics |
| Growth trends | User acquisition |

#### ⚙️ System Configuration

| Feature | Description |
|---------|-------------|
| Cấu hình hệ thống | Global settings |
| Quản lý business types | Categories |
| Quản lý thuế suất | Tax rates by type |
| System announcements | Global notifications |

---

### 6.3 Consultant Features

#### 📋 Accounting Template Management

| Feature | Description |
|---------|-------------|
| Xem templates hiện tại | Current TT152 templates |
| Cập nhật template | Update forms/formats |
| Preview template output | Test with sample data |
| Version history | Template versions |

#### 📢 Notification Management

| Feature | Description |
|---------|-------------|
| Tạo thông báo về quy định mới | Regulatory updates |
| Tạo thông báo về template changes | Template update alerts |
| Target notification | By business type/region |
| Schedule notification | Timed delivery |

---

### 6.4 System Features (AI Service)

#### 🎤 Speech-to-Text + Order Parsing

| Feature | Description |
|---------|-------------|
| Voice → Text | Google STT / Whisper |
| Text → Structured Order | RAG + LLM parsing |
| Product matching | Match với catalog của location |
| Customer/Debtor matching | Suggest existing debtors |
| Confidence scoring | Độ tin cậy của parsing |

#### 📚 Automated Bookkeeping

| Feature | Description |
|---------|-------------|
| Ghi chép giao dịch tự động | Auto-record transactions |
| Generate sổ kế toán đơn giản | S1a-HKD, S2a-HKD... |
| Tính thuế GTGT/TNCN | Based on business type |
| Export PDF/Excel | Download reports |

#### 📈 Revenue Forecast (Phase 2)

| Feature | Description |
|---------|-------------|
| Dự báo doanh thu tuần/tháng | ML-based prediction |
| Trending products | Demand forecast |
| Seasonal patterns | Historical analysis |

#### ⚠️ Anomaly Detection (Phase 2)

| Feature | Description |
|---------|-------------|
| Unusual revenue patterns | Alert on anomalies |
| Suspicious transactions | Fraud detection |
| Inventory discrepancies | Stock anomalies |

---

### 6.5 Feature Priority Matrix

Phân loại theo độ ưu tiên triển khai:

| Priority | Module | Features |
|:--------:|--------|----------|
| **P0** | Auth | Login, Register, Forgot Password |
| **P0** | Location | CRUD Business Location |
| **P0** | Product | CRUD Products, SaleItems, Pricing |
| **P0** | Order | Manual order creation, Complete, Cancel |
| **P1** | Import | Stock import recording |
| **P1** | Debt | Debtor management, Debt payment |
| **P1** | Hire | Employee invitation & management |
| **P1** | AI Order | Voice/Text → Draft order |
| **P2** | Reports | Daily revenue, Best sellers |
| **P2** | TT152 | Accounting book generation |
| **P2** | Notifications | Push notifications |
| **P3** | Forecast | Revenue prediction |
| **P3** | Anomaly | Unusual data warnings |
| **P3** | Admin | Full admin panel |

---

### 6.6 Mobile vs Web Feature Parity


| Feature | Mobile (Flutter) | Web (ReactJS) | Notes |
|---------|:----------------:|:-------------:|-------|
| Manual Order | ✅ | ✅ | Core feature |
| AI Voice Order | ✅ | 🟡 | Mobile primary |
| Product Management | 🟡 | ✅ | Web preferred |
| Import Management | 🟡 | ✅ | Web preferred |
| Report View | ✅ | ✅ | Both |
| Report Export | ✅ | ✅ | Both |
| Admin Panel | ❌ | ✅ | Web only |
| Consultant Panel | ❌ | ✅ | Web only |

**Legend**: ✅ Full support | 🟡 Limited/Basic | ❌ Not available