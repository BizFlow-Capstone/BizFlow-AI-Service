# Product Flow Documentation

> **Mục đích**: Document chi tiết các flow liên quan đến quản lý sản phẩm (Product) trong BizFlow Platform.

---

## Mục lục

1. [Tổng quan Product](#1-tổng-quan-product)
2. [Entity Design](#2-entity-design)
3. [Create Product Flow](#3-create-product-flow)
4. [View & Search Product Flow](#4-view--search-product-flow)
5. [Update Product Flow](#5-update-product-flow)
6. [Delete Product Flow](#6-delete-product-flow)
7. [Status Management](#7-status-management)
8. [SaleItem & Pricing Rules](#8-saleitem--pricing-rules)
9. [Stock Rules & Integration](#9-stock-rules--integration)
10. [API Endpoints Summary](#10-api-endpoints-summary)
11. [Error Codes](#11-error-codes)
12. [Business Rules Summary](#12-business-rules-summary)

---

## 1. Tổng quan Product

### Context - Nghiệp vụ quản lý sản phẩm HKD

Đối với hộ kinh doanh Việt Nam:

- Sản phẩm đa dạng: hàng hóa vật lý (tạp hóa, VLXD), dịch vụ (cắt tóc, sửa xe), F&B (quán ăn, cà phê)
- Một sản phẩm có thể bán theo **nhiều đơn vị** khác nhau (bao, thùng, kg, cái...)
- Giá bán có thể thay đổi theo thời điểm (giá mùa, giá khuyến mãi)
- Tồn kho chỉ áp dụng cho **hàng hóa vật lý**, dịch vụ/F&B không cần quản lý kho

### Core Concepts

```markdown
Product (Sản phẩm)
├── Thông tin chung: Tên, SKU, Ảnh, Nhà sản xuất
├── Giá: SellingPrice (giá bán base unit), CostPrice (giá vốn cached)
├── Tồn kho: Stock (theo base unit)
├── Flag: TrackInventory (có quản lý kho không?)
│
├── SaleItem 1 (Base Unit - tự động tạo)
│   ├── Unit: "Bao" (= Product.Unit)
│   ├── Quantity: 1
│   └── PricePolicy: 95,000đ (default, = Product.SellingPrice)
│
├── SaleItem 2 (Price Tier - user tạo thêm)
│   ├── Unit: "Thùng"
│   ├── Quantity: 12 (= 12 bao)
│   └── PricePolicy: 1,080,000đ (= 90,000đ/bao)
│
└── SaleItem 3 (Price Tier - user tạo thêm)
    ├── Unit: "Tấn"
    ├── Quantity: 20 (= 20 bao)
    └── PricePolicy: 1,800,000đ (= 90,000đ/bao)
```

**Quan hệ giữa các entity:**

```markdown
Product 1 ──── N SaleItem 1 ──── N ProductPricePolicy
   │                │                    │
   │                │                    ├── Price (giá bán)
   │                │                    ├── IsDefault (giá mặc định?)
   │                │                    ├── StartAt (bắt đầu áp dụng)
   │                │                    └── EndAt (kết thúc)
   │                │
   │                ├── Unit (đơn vị bán: thùng, bao...)
   │                └── Quantity (quy đổi: 1 thùng = 12 bao)
   │
   ├── Unit (đơn vị tính nhỏ nhất / base unit)
   ├── Stock (tồn kho theo base unit)
   ├── SellingPrice (giá bán theo base unit)
   ├── CostPrice (giá vốn cached - auto-update from Import)
   └── TrackInventory (có quản lý tồn kho?)
```

### Phân biệt Product vs SaleItem

| Khía cạnh | Product | SaleItem |
|-----------|---------|----------|
| **Mục đích** | Quản lý hàng hóa trong kho (inventory) | Quản lý đơn vị bán hàng (sales) |
| **Scope** | Thông tin chung của sản phẩm | Đơn vị + giá bán cụ thể |
| **Unit** | Base unit (đơn vị nhỏ nhất) | Đơn vị bán (có thể = base hoặc lớn hơn) |
| **Stock** | Có (nếu TrackInventory) | Không |
| **Giá** | SellingPrice (giá bán), CostPrice (giá vốn cached) | PricePolicy (giá bán theo đơn vị) |
| **Ví dụ** | Xi măng Hà Tiên - Bán 95k, Vốn 80k, Stock 150 bao | Bao (1) - 95k, Thùng (12 bao) - 1.08M |

> **Lưu ý dịch vụ/F&B**: Đối với ngành dịch vụ và F&B, sản phẩm không cần quản lý tồn kho → `TrackInventory = false`. SaleItem vẫn dùng để quản lý giá bán.

---

## 2. Entity Design

### Tables

```sql
-- =============================================
-- PRODUCTS TABLE (Sản phẩm)
-- =============================================
CREATE TABLE Products (
    ProductId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    BusinessLocationId INT NOT NULL COMMENT 'Thuộc location nào',
    BusinessTypeId CHAR(36) NOT NULL COMMENT 'Loại hình kinh doanh',
    
    -- Thông tin sản phẩm
    ProductName VARCHAR(255) NOT NULL,
    Sku VARCHAR(100) DEFAULT NULL COMMENT 'Mã SKU (optional)',
    Unit VARCHAR(50) NOT NULL COMMENT 'Đơn vị tính nhỏ nhất (base unit)',
    
    -- Giá & Tồn kho
    SellingPrice DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'Giá bán theo base unit',
    CostPrice DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'Giá vốn cached (auto-update from Import)',
    Stock INT NOT NULL DEFAULT 0 COMMENT 'Tồn kho theo base unit',
    
    -- Ảnh sản phẩm (Cloudinary)
    ImageUrl VARCHAR(500) DEFAULT NULL,
    ImagePublicId VARCHAR(255) DEFAULT NULL COMMENT 'Cloudinary public ID',
    
    -- Metadata
    Manufacturer VARCHAR(255) DEFAULT NULL COMMENT 'Nhà sản xuất',
    TrackInventory BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'Có quản lý tồn kho?',
    Status ENUM('active', 'inactive') NOT NULL DEFAULT 'active',
    
    -- Soft delete
    DeletedAt DATETIME DEFAULT NULL COMMENT 'Soft delete timestamp',
    
    -- FKs & Indexes
    CONSTRAINT fk_product_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    CONSTRAINT fk_product_business_type FOREIGN KEY (BusinessTypeId) 
        REFERENCES BusinessTypes(BusinessTypeId),
    INDEX idx_product_location (BusinessLocationId),
    INDEX idx_product_sku (Sku),
    INDEX idx_product_status (Status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- SALE_ITEMS TABLE (Đơn vị bán hàng)
-- =============================================
CREATE TABLE SaleItems (
    SaleItemId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    ProductId BIGINT NOT NULL,
    
    Unit VARCHAR(50) NOT NULL COMMENT 'Đơn vị bán (bao, thùng, kg...)',
    Quantity INT NOT NULL DEFAULT 1 COMMENT 'Quy đổi: 1 Unit = N base units',
    
    -- Soft delete
    DeletedAt DATETIME DEFAULT NULL,
    
    CONSTRAINT fk_saleitem_product FOREIGN KEY (ProductId) 
        REFERENCES Products(ProductId),
    INDEX idx_saleitem_product (ProductId),
    INDEX idx_saleitem_deletedat (DeletedAt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- =============================================
-- PRODUCT_PRICE_POLICIES TABLE (Chính sách giá)
-- =============================================
CREATE TABLE ProductPricePolicies (
    ProductPricePolicyId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    SaleItemId BIGINT NOT NULL,
    
    Price DECIMAL(15,2) NOT NULL COMMENT 'Giá bán',
    IsDefault BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Giá mặc định?',
    StartAt DATETIME DEFAULT NULL COMMENT 'Bắt đầu áp dụng',
    EndAt DATETIME DEFAULT NULL COMMENT 'Kết thúc áp dụng (NULL = vô thời hạn)',
    
    CONSTRAINT fk_pricepolicy_saleitem FOREIGN KEY (SaleItemId) 
        REFERENCES SaleItems(SaleItemId),
    INDEX idx_pricepolicy_saleitem (SaleItemId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### Entity Classes

```csharp
public partial class Product
{
    public long ProductId { get; set; }
    public int BusinessLocationId { get; set; }
    public Guid BusinessTypeId { get; set; }
    
    public string ProductName { get; set; } = null!;
    public string? Sku { get; set; }
    public string Unit { get; set; } = null!;         // Base unit
    
    public decimal SellingPrice { get; set; }          // Giá bán base unit
    public decimal CostPrice { get; set; }             // Giá vốn cached (auto-update from Import)
    public int Stock { get; set; }
    
    public string? ImageUrl { get; set; }
    public string? ImagePublicId { get; set; }
    public string? Manufacturer { get; set; }
    public bool? TrackInventory { get; set; }
    public string Status { get; set; } = null!;        // "active" | "inactive"
    public DateTime? DeletedAt { get; set; }
    
    // Navigation
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
    public virtual BusinessType BusinessType { get; set; } = null!;
    public virtual ICollection<SaleItem> SaleItems { get; set; } = new List<SaleItem>();
    public virtual ICollection<ProductImport> ProductsImports { get; set; } = new List<ProductImport>();
    public virtual ICollection<StockMovement> StockMovements { get; set; } = new List<StockMovement>();
}

public partial class SaleItem
{
    public long SaleItemId { get; set; }
    public long ProductId { get; set; }
    
    public string Unit { get; set; } = null!;          // Đơn vị bán
    public int Quantity { get; set; }                   // Quy đổi ra base unit
    public DateTime? DeletedAt { get; set; }
    
    // Navigation
    public virtual Product Product { get; set; } = null!;
    public virtual ICollection<ProductPricePolicy> ProductPricePolicies { get; set; } = new List<ProductPricePolicy>();
}

public partial class ProductPricePolicy
{
    public long ProductPricePolicyId { get; set; }
    public long SaleItemId { get; set; }
    
    public decimal Price { get; set; }
    public bool IsDefault { get; set; }
    public DateTime? StartAt { get; set; }
    public DateTime? EndAt { get; set; }
    
    // Navigation
    public virtual SaleItem SaleItem { get; set; } = null!;
}
```

### Relationship Diagram

```
┌─────────────────────────────┐
│         Product             │
│─────────────────────────────│
│ ProductId (PK)              │
│ BusinessLocationId (FK)     │
│ BusinessTypeId (FK)         │
│ ProductName                 │
│ Sku                         │
│ Unit ◄───── Base unit       │
│ SellingPrice                │
│ CostPrice (cached)          │
│ Stock                       │
│ ImageUrl / ImagePublicId    │
│ TrackInventory              │
│ Status                      │
│ DeletedAt                   │
└──────────┬──────────────────┘
           │ 1:N
           ▼
┌─────────────────────────────┐
│        SaleItem             │
│─────────────────────────────│
│ SaleItemId (PK)             │
│ ProductId (FK)              │
│ Unit                        │
│ Quantity ◄── Quy đổi        │
│ DeletedAt                   │
└──────────┬──────────────────┘
           │ 1:N
           ▼
┌─────────────────────────────┐
│    ProductPricePolicy       │
│─────────────────────────────│
│ ProductPricePolicyId (PK)   │
│ SaleItemId (FK)             │
│ Price                       │
│ IsDefault                   │
│ StartAt / EndAt             │
└─────────────────────────────┘
```

---

## 3. Create Product Flow

### Permission

| Action | Owner | Employee | Admin | Consultant |
|--------|:-----:|:--------:|:-----:|:----------:|
| Tạo sản phẩm | ✅ | ❌ | ❌ | ❌ |

### Input

| Field | Bắt buộc? | Validation | Mặc định |
|-------|:---------:|------------|----------|
| LocationId | ✅ | Phải là location mà user owns | — |
| BusinessTypeId | ✅ | Phải tồn tại | — |
| ProductName | ✅ | Max 255 chars | — |
| Unit | ✅ | Max 50 chars (base unit) | — |
| Sku | ❌ | Max 100 chars | `null` |
| SellingPrice | ❌ | >= 0 | `0` |
| Stock | ❌ | integer | `0` |
| TrackInventory | ❌ | boolean | `true` |
| Manufacturer | ❌ | Max 255 chars | `null` |
| Image | ❌ | File (multipart) | `null` |
| PriceTiers | ❌ | JSON array | `[]` |

#### PriceTier Schema

```json
[
  {
    "Unit": "Thùng",       // Đơn vị bán (khác base unit)
    "Quantity": 12,         // 1 Thùng = 12 [base unit]
    "Price": 1080000        // Giá bán cho 1 Thùng
  }
]
```

### Flow Diagram

```markdown
Owner tạo sản phẩm mới
        │
        ▼
┌─────────────────────────────┐
│ 1. Validate Ownership       │
│    IsOwner(userId, locId)?  │
│    → 403 nếu không phải     │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 2. Validate Input           │
│    - Required fields        │
│    - PriceTier unit ≠ base  │
│      unit (no duplicate)    │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 3. Create Product entity    │
│    Status = 'active'        │
│    DeletedAt = null         │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 4. Auto-create Default      │
│    SaleItem (base unit)     │
│    ├── Unit = Product.Unit  │
│    ├── Quantity = 1         │
│    └── PricePolicy:         │
│        Price = SellingPrice │
│        IsDefault = true     │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 5. Create PriceTier         │
│    SaleItems (nếu có)       │
│    Mỗi tier → SaleItem +    │
│    PricePolicy (IsDefault)  │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 6. Upload Image (nếu có)    │
│    → Cloudinary             │
│    → Lưu URL + PublicId     │
│    → Rollback nếu DB fail   │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 7. SaveChanges              │
│    → Nếu fail: xóa image    │
│      đã upload              │
└───────────┬─────────────────┘
            │
            ▼
        ✅ Return ProductListItemDto
```

### Business Rules

**RULE-PROD-01: Default SaleItem tự động tạo**

Khi tạo product, hệ thống **luôn** tạo 1 SaleItem mặc định:

- `Unit` = Product.Unit (base unit)
- `Quantity` = 1
- `PricePolicy.Price` = **Product.SellingPrice** (giá bán, không phải giá vốn)
- `PricePolicy.IsDefault` = true

> ✅ **Quyết định**: Default SaleItem lấy giá = `SellingPrice` (giá bán). User nhập giá bán khi tạo sản phẩm. `CostPrice` là giá vốn riêng, không liên quan đến giá bán trên SaleItem.

**RULE-PROD-02: CostPrice là cached value**

`Product.CostPrice` đóng vai trò **read-optimized cache** để hiển thị nhanh giá vốn trên UI:

| Thời điểm | CostPrice = ? | Nguồn |
|------------|---------------|------|
| Tạo product (chưa nhập hàng) | User tự nhập (optional, default 0) | Input |
| Import lần 1 confirmed | `ProductImport.CostPrice` | Auto-update |
| Import lần N confirmed | **Giá vốn nhập gần nhất** | Auto-update |
| Tính báo cáo lợi nhuận | Query từ `ProductImport` (FIFO/weighted avg) | **Nguồn chính xác** |

```csharp
// Trong ConfirmImportAsync (import-flow)
// Auto-update cached CostPrice = giá nhập gần nhất
product.CostPrice = productImport.CostPrice;
```

> **Lưu ý**: `Product.CostPrice` dùng cho UI dashboard (ước lượng). Báo cáo tài chính chính xác phải query từ `ProductImport`.

**RULE-PROD-03: SKU cảnh báo trùng, không block**

SKU là mã do nhà sản xuất/chuỗi cung ứng đặt. Với HKD Việt Nam, SKU có thể nhập thủ công và trùng lặp do nhiều lý do. Hệ thống **cảnh báo** nhưng **không chặn**:

```
User nhập SKU
    │
    ▼
Check trùng trong cùng Location?
    │
  ┌─┴──┐
  │    │
 Trùng  Không trùng
  │    │
  ▼    ▼
⚠️ WARNING      ✅ OK
"SKU này đã tồn tại
cho sản phẩm [X]."
  │
  ▼
Vẫn cho phép tạo/cập nhật
```

```csharp
// Trả warnings[] trong response, không throw exception
if (!string.IsNullOrWhiteSpace(request.Sku))
{
    var existingProduct = await _unitOfWork.Products
        .FindBySkuInLocationAsync(request.LocationId, request.Sku, excludeProductId: null);
    
    if (existingProduct != null)
    {
        response.Warnings.Add(new Warning
        {
            Code = "PRODUCT_DUPLICATE_SKU",
            Message = $"SKU '{request.Sku}' đã tồn tại cho sản phẩm '{existingProduct.ProductName}'"
        });
    }
}
```

**RULE-PROD-04: PriceTier Unit không được trùng Base Unit**

```csharp
// Validate: không cho PriceTier có Unit giống Product.Unit
var duplicateUnitTier = request.PriceTiers.FirstOrDefault(t => 
    string.Equals(t.Unit?.Trim(), request.Unit?.Trim(), StringComparison.OrdinalIgnoreCase));
    
if (duplicateUnitTier != null)
    throw new BadRequestException("Duplicate unit in price tiers");
```

> Vì base unit đã có SaleItem mặc định → PriceTier chỉ dành cho đơn vị khác.

**RULE-PROD-05: Image Upload Rollback**

```
Upload image → Save DB
                 │
                 ├── Success → DONE ✅
                 └── Fail → Delete uploaded image from Cloudinary → throw error
```

---

## 4. View & Search Product Flow

### Permission

| Action | Owner | Employee | Admin | Consultant |
|--------|:-----:|:--------:|:-----:|:----------:|
| Xem danh sách sản phẩm | ✅ | ✅ | ❌ | ❌ |
| Xem chi tiết sản phẩm | ✅ | ✅ | ❌ | ❌ |
| Xem sale items | ✅ | ✅ | ❌ | ❌ |

### 4.1 Search & Filter Products

**Endpoint**: `GET /api/my-business/products`

**Query Parameters:**

| Param | Type | Mô tả |
|-------|------|--------|
| LocationId | int | ✅ **Required** - Location ID |
| Name | string | Search theo tên (contains, case-insensitive) |
| Sku | string | Search theo SKU |
| MinSellingPrice | decimal | Filter giá bán tối thiểu |
| MaxSellingPrice | decimal | Filter giá bán tối đa |
| MinStock | int | Filter tồn kho tối thiểu |
| MaxStock | int | Filter tồn kho tối đa |
| Status | string | Filter theo status (`active` / `inactive`) |
| TrackInventory | bool | Filter theo flag quản lý kho |
| PageNumber | int | Trang (default: 1) |
| PageSize | int | Kích thước trang (default: 10, max: 50) |

**Response**: `PaginatedResponse<ProductListItemDto>`

```json
{
  "items": [
    {
      "productId": 1,
      "name": "Xi măng Hà Tiên",
      "sku": "XM-HT-50",
      "price": 95000,          // Default SaleItem price
      "trackInventory": true,
      "stock": 150,
      "status": "active"
    }
  ],
  "totalCount": 25,
  "pageNumber": 1,
  "pageSize": 10,
  "totalPages": 3
}
```

### 4.2 Product Detail

**Endpoint**: `GET /api/my-business/product/{productId}`

**Response**: `ProductDetailDto`

```json
{
  "productId": 1,
  "name": "Xi măng Hà Tiên",
  "sku": "XM-HT-50",
  "imageUrl": "https://res.cloudinary.com/.../product.jpg",
  "unit": "Bao",
  "sellingPrice": 95000,
  "costPrice": 80000,
  "stock": 150,
  "manufacturer": "Hà Tiên",
  "status": "active",
  "trackInventory": true,
  "businessLocationId": 1,
  "businessLocationName": "Cửa hàng VLXD Minh Anh",
  "saleItems": [
    {
      "saleItemId": 1,
      "unit": "Bao",
      "quantity": 1,
      "price": 95000
    },
    {
      "saleItemId": 2,
      "unit": "Thùng",
      "quantity": 12,
      "price": 1080000
    }
  ]
}
```

### 4.3 Product Sale Items

**Endpoint**: `GET /api/my-business/product/{productId}/sale-items`

**Response**: `ProductSaleItemsResponseDto`

```json
{
  "productId": 1,
  "saleItems": [
    { "saleItemId": 1, "unit": "Bao", "quantity": 1, "price": 95000 },
    { "saleItemId": 2, "unit": "Thùng", "quantity": 12, "price": 1080000 }
  ]
}
```

### Flow Diagram (Search)

```markdown
User mở danh sách sản phẩm
        │
        ▼
┌─────────────────────────────┐
│ 1. Validate Access          │
│    HasAccess(userId, locId)?│
│    → Owner hoặc Employee    │
│    → 403 nếu không          │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 2. Apply Filters            │
│    - Name LIKE '%search%'   │
│    - Status = ?             │
│    - DeletedAt IS NULL      │
│    - Stock BETWEEN ? AND ?  │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 3. Paginate & Return        │
│    - Map Product → DTO      │
│    - Price = default        │
│      SaleItem's price       │
└───────────┬─────────────────┘
            │
            ▼
        ✅ PaginatedResponse
```

> **Note**: Soft deleted products (`DeletedAt IS NOT NULL`) **KHÔNG** xuất hiện trong search results.

---

## 5. Update Product Flow

### Permission

| Action | Owner | Employee |
|--------|:-----:|:--------:|
| Cập nhật thông tin sản phẩm | ✅ | ❌ |

### Input

Giống `CreateProductRequest` + thêm `RemoveImage` flag:

| Field | Mô tả  |
|-------|--------|
| RemoveImage | `true` = xóa ảnh hiện tại khỏi Cloudinary |
| Image (file) | Upload ảnh mới (tự xóa ảnh cũ) |

### Flow Diagram

```markdown
Owner cập nhật sản phẩm
        │
        ▼
┌─────────────────────────────┐
│ 1. Validate Product exists  │
│    GetByIdWithSaleItems()   │
│    → 404 nếu không tìm thấy │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 2. Validate Ownership       │
│    IsOwner(userId, locId)?  │
│    → 403 nếu không phải     │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 3. Validate Location        │
│    không đổi Location       │
│    → 400 nếu locationId     │
│      khác product hiện tại  │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 4. Validate PriceTier       │
│    Unit ≠ base unit         │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 5. Update Product fields    │
│    Name, SKU, SellingPrice, │
│    CostPrice, Stock, Unit   │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 6. Handle Image             │
│    ├── RemoveImage=true     │
│    │   → Delete từ Cloud    │
│    └── New Image            │
│        → Upload mới trước   │
│        → Xóa cũ sau khi     │
│          DB save thành công │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 7. Sync SaleItems           │◄─── RULE-PROD-06
│    (xem chi tiết bên dưới)  │
└───────────┬─────────────────┘
            │
            ▼
        ✅ Return ProductListItemDto
```

### RULE-PROD-06: SaleItem Sync Strategy (Reconciliation)

Khi update product, hệ thống **reconcile** SaleItems thay vì delete-all + re-create:

```markdown
Expected SaleItems (từ request):
├── (Unit=Product.Unit, Qty=1, Price=SellingPrice)  ← Default
├── PriceTier 1
└── PriceTier 2

Existing SaleItems (trong DB):
├── SaleItem A
├── SaleItem B
└── SaleItem C

Reconciliation:
1. Match expected vs existing by (Unit + Quantity)
2. Matched → Update PricePolicy price
3. Not matched → Create new SaleItem + PricePolicy
4. Remaining existing (unmatched) → Soft delete (DeletedAt = now)
```

**Tại sao reconcile thay vì delete-all?**

- SaleItem có thể đã được reference trong OrderDetail
- Hard delete sẽ break FK constraints
- Soft delete giữ lại lịch sử

### RULE-PROD-07: Không cho đổi Location

```csharp
if (product.BusinessLocationId != request.LocationId)
    throw new BadRequestException("Cannot change product location");
```

> Sản phẩm gắn chặt với location. Muốn chuyển location → tạo product mới ở location đích.

### RULE-PROD-08: Image Update an toàn

Khi update ảnh sản phẩm, phải đảm bảo không mất ảnh do partial failure:

```markdown
Có ảnh mới:
1. Upload ảnh mới lên Cloudinary
2. Lưu DB (product.ImageUrl = new, product.ImagePublicId = new)
3. Nếu DB save thành công → Xóa ảnh cũ khỏi Cloudinary
4. Nếu DB save fail → Xóa ảnh mới, giữ nguyên ảnh cũ
```

> **Tại sao không xóa cũ trước?** Nếu upload mới fail sau khi đã xóa cũ → mất cả 2 ảnh.

---

## 6. Delete Product Flow

### Permission

| Action | Owner | Employee |
|--------|:-----:|:--------:|
| Xóa sản phẩm | ✅ | ❌ |

### Flow Diagram

```markdown
Owner xóa sản phẩm
        │
        ▼
┌─────────────────────────────┐
│ 1. Validate Product exists  │
│    → 404 nếu không tìm thấy│
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 2. Validate Ownership       │
│    → 403 nếu không phải     │
└───────────┬─────────────────┘
            │
            ▼
┌─────────────────────────────┐
│ 3. Check History            │◄─── RULE-PROD-09
│    HasHistory(productId)?   │
│    (OrderDetail, Import)    │
└───────────┬─────────────────┘
            │
       ┌────┴────┐
       │         │
    Có lịch sử  Không có
       │         │
       ▼         ▼
┌──────────┐ ┌──────────┐
│ SOFT     │ │ HARD     │
│ DELETE   │ │ DELETE   │
│ DeletedAt│ │ Remove   │
│ = now    │ │ from DB  │
└──────────┘ └──────────┘
       │         │
       └────┬────┘
            │
            ▼
        ✅ Success
```

### RULE-PROD-06: Smart Delete (Soft vs Hard)

| Điều kiện | Action | Lý do |
|-----------|--------|-------|
| Product có trong OrderDetail hoặc ProductImport | **Soft delete** (DeletedAt = now) | Giữ lại lịch sử giao dịch |
| Product chưa từng được dùng | **Hard delete** (remove from DB) | Không có reference, xóa sạch |

> **Note**: Soft deleted products không xuất hiện trong search nhưng vẫn hiển thị trong lịch sử order/import.

---

## 7. Status Management

### Permission

| Action | Owner | Employee |
|--------|:-----:|:--------:|
| Đổi status | ✅ | ❌ |

### Status Values

| Status | Mô tả | Hiển thị trong search? | Có thể tạo order? |
|--------|-------|:---------------------:|:-----------------:|
| `active` | Đang bán | ✅ | ✅ |
| `inactive` | Tạm ngưng bán | ✅ (filter) | ❌ |

### Flow

```markdown
Owner đổi status sản phẩm
        │
        ▼
    Validate: status ∈ {'active', 'inactive'}
        │
        ▼
    Update product.Status = newStatus
        │
        ▼
    ✅ Success
```

> ✅ **Quyết định**: Bỏ trạng thái `discontinued` ở flow nghiệp vụ hiện tại. Product status chỉ gồm `active` và `inactive`.

---

## 8. SaleItem & Pricing Rules

### 8.1 SaleItem Concept (Đơn vị bán hàng)

SaleItem đại diện cho **cách bán** một sản phẩm. Ví dụ thực tế:

```markdown
Sản phẩm: Nước ngọt Pepsi
Base Unit: Lon
Stock: 500 lon

SaleItems:
├── Lon (1 lon)           → Giá: 12,000đ
├── Lốc (6 lon)           → Giá: 65,000đ   (tiết kiệm 7k)
└── Thùng (24 lon)        → Giá: 240,000đ  (tiết kiệm 48k)
```

```markdown
Sản phẩm: Dịch vụ cắt tóc nam
Base Unit: Lần
TrackInventory: false
Stock: N/A

SaleItems:
├── Cắt gội sấy (1 lần)  → Giá: 80,000đ
└── Combo cắt + uốn      → Giá: 250,000đ
```

### 8.2 Conversion Logic (Quy đổi khi bán)

Khi tạo Order, stock trừ theo **base unit**:

```markdown
Bán 2 thùng Pepsi (1 thùng = 24 lon):
→ Trừ stock: 2 × 24 = 48 lon

Bán 1 lốc + 3 lon Pepsi:
→ Trừ stock: (1 × 6) + (3 × 1) = 9 lon
```

**Công thức**:

```markdown
StockDeduction = SaleItem.Quantity × OrderDetail.Quantity
```

### 8.3 PricePolicy (Chính sách giá)

Mỗi SaleItem có thể có **nhiều PricePolicy** (giá theo thời gian):

| Field | Mô tả |
|-------|--------|
| `Price` | Giá bán |
| `IsDefault` | `true` = giá mặc định (luôn áp dụng) |
| `StartAt` | Thời điểm bắt đầu áp dụng |
| `EndAt` | Thời điểm kết thúc (`null` = vô thời hạn) |

**Quy tắc lấy giá hiện tại:**

```markdown
1. Tìm PricePolicy có StartAt <= NOW <= EndAt (giá theo thời gian)
2. Nếu không có → Lấy PricePolicy có IsDefault = true
3. Nếu không có → Giá = 0
```

> ✅ **Quyết định**: Phase hiện tại chỉ dùng `IsDefault = true`. Logic `StartAt/EndAt` sẽ implement ở phase sau.

### 8.4 Ví dụ đầy đủ

```
Product: Xi măng Hà Tiên PCB40
    Unit: Bao (base unit)
    SellingPrice: 95,000đ (giá bán base unit)
    CostPrice: 80,000đ (giá vốn cached - từ lần nhập gần nhất)
    Stock: 500 bao
    TrackInventory: true

    SaleItem 1 (default - auto created):
        Unit: Bao
        Quantity: 1
        PricePolicy (default): 95,000đ  (← = Product.SellingPrice)

    SaleItem 2 (price tier):
        Unit: Thùng (10 bao)
        Quantity: 10
        PricePolicy (default): 900,000đ  (= 90,000đ/bao, giảm 5k/bao)

    SaleItem 3 (price tier):
        Unit: Pallet (50 bao)
        Quantity: 50
        PricePolicy (default): 4,250,000đ (= 85,000đ/bao, giảm 10k/bao)

    Lợi nhuận ước lượng: 95k - 80k = 15k/bao (ước lượng từ cached CostPrice)
    Lợi nhuận chính xác: Query từ ProductImport (FIFO)
```

---

## 9. Stock Rules & Integration

### 9.1 Stock Location

Stock được lưu trực tiếp trên `Product.Stock` (đơn vị: base unit).

### 9.2 Stock Changes

| Event | Hành động | Điều kiện |
|-------|-----------|-----------|
| **Order Completed** | Stock -= (SaleItem.Qty × OrderDetail.Qty) | `TrackInventory = true` |
| **Order Cancelled** (từ completed) | Stock += (rollback) | `TrackInventory = true` |
| **Import Confirmed** | Stock += Import.Quantity | `TrackInventory = true` |
| **Import Cancelled** (từ confirmed) | Stock -= (rollback) | `TrackInventory = true` |

### 9.3 Stock Validation Rules

**RULE-STOCK-01: Cảnh báo âm kho, không block**

```csharp
// Khi tạo order
if (product.TrackInventory == true)
{
    var requiredStock = saleItem.Quantity * orderDetail.Quantity;
    if (product.Stock < requiredStock)
    {
        // WARNING - vẫn cho tạo order
        response.Warnings.Add(new Warning
        {
            Code = "LOW_STOCK",
            Message = $"Sản phẩm {product.ProductName} chỉ còn {product.Stock} {product.Unit}"
        });
    }
}
```

> Lý do không block: HKD có thể bán hàng đang trên đường giao (stock chưa cập nhật).

**RULE-STOCK-02: TrackInventory = false**

```markdown
Khi TrackInventory = false:
├── Order → KHÔNG trừ stock
├── Import → KHÔNG cộng stock
├── Stock field = 0 (ignored)
└── Dùng cho: dịch vụ, F&B, hàng không quản lý kho
```

### 9.4 Integration Map

```markdown
                    ┌──────────────┐
                    │   Product    │
                    │   Stock: 500 │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────────┐
              │            │                │
              ▼            ▼                ▼
        ┌──────────┐ ┌──────────┐ ┌────────────────┐
        │  Order   │ │  Import  │ │ StockMovements │
        │  -Stock  │ │  +Stock  │ │  (audit log)   │
        └──────────┘ └──────────┘ └────────────────┘
```

> **Cross-reference**: Xem chi tiết stock integration trong [import-flow.md](./import-flow.md) (Confirm/Cancel) và [order-flow.md](./order-flow.md) (Complete/Cancel).

### 9.5 Rủi ro Inconsistent Stock là gì?

Inconsistent xảy ra khi `Product.Stock` không phản ánh đúng tổng biến động thực tế.

Các tình huống thường gặp:

1. **Partial failure trong transaction boundary**
    - Ví dụ: tạo Order/Import thành công nhưng update stock fail (hoặc ngược lại).
2. **Race condition / lost update**
    - 2 request cùng đọc stock cũ rồi cùng ghi đè stock mới.
3. **Manual fix trực tiếp DB**
    - Chỉnh tay stock mà không có log biến động tương ứng.
4. **Rollback nghiệp vụ không đối xứng**
    - Complete có trừ stock, nhưng Cancel/Undo bị miss một nhánh xử lý.

Hệ quả:

- Báo cáo tồn kho sai.
- Cảnh báo low stock sai.
- Quyết định nhập hàng sai.

### 9.6 StockMovements Log

`StockMovements` là nhật ký biến động kho theo từng nghiệp vụ (+/-), là **immutable log** giúp:

1. **Audit trail đầy đủ** — Biết chính xác ai, khi nào, lý do gì làm stock tăng/giảm.
2. **Reconciliation** — So sánh `Product.Stock` với `SUM(StockMovements.QuantityDelta)` để phát hiện lệch.
3. **Rebuild stock** — Nếu stock hiện tại bị sai, có thể tính lại từ log.
4. **Điều tra incident** — Truy vết nhanh bug do flow Order/Import/Cancel.

#### 9.6.1 Entity Design

```sql
-- =============================================
-- STOCK_MOVEMENTS TABLE (Nhật ký biến động kho)
-- =============================================
CREATE TABLE StockMovements (
    StockMovementId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    ProductId BIGINT NOT NULL,
    BusinessLocationId INT NOT NULL,
    
    -- Movement details
    QuantityDelta INT NOT NULL COMMENT 'Biến động: +N (nhập) hoặc -N (xuất)',
    StockBefore INT NOT NULL COMMENT 'Tồn trước biến động',
    StockAfter INT NOT NULL COMMENT 'Tồn sau biến động',
    
    -- Source reference (polymorphic)
    ReferenceType VARCHAR(30) NOT NULL COMMENT 'ORDER|IMPORT|CANCEL_ORDER|CANCEL_IMPORT|ADJUSTMENT',
    ReferenceId BIGINT DEFAULT NULL COMMENT 'OrderId hoặc ImportId',
    
    -- Metadata
    Note VARCHAR(500) DEFAULT NULL COMMENT 'Ghi chú (manual adjustment reason)',
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CreatedBy CHAR(36) NOT NULL COMMENT 'UserId thực hiện',
    
    CONSTRAINT fk_stockmov_product FOREIGN KEY (ProductId) 
        REFERENCES Products(ProductId),
    CONSTRAINT fk_stockmov_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    INDEX idx_stockmov_product (ProductId),
    INDEX idx_stockmov_location (BusinessLocationId),
    INDEX idx_stockmov_reference (ReferenceType, ReferenceId),
    INDEX idx_stockmov_created (CreatedAt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

```csharp
public class StockMovement
{
    public long StockMovementId { get; set; }
    public long ProductId { get; set; }
    public int BusinessLocationId { get; set; }
    
    public int QuantityDelta { get; set; }      // +N or -N
    public int StockBefore { get; set; }
    public int StockAfter { get; set; }
    
    public string ReferenceType { get; set; } = null!;  // ORDER, IMPORT, etc.
    public long? ReferenceId { get; set; }
    
    public string? Note { get; set; }
    public DateTime CreatedAt { get; set; }
    public Guid CreatedBy { get; set; }
    
    // Navigation
    public virtual Product Product { get; set; } = null!;
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
}

public static class StockMovementType
{
    public const string Order = "ORDER";
    public const string Import = "IMPORT";
    public const string CancelOrder = "CANCEL_ORDER";
    public const string CancelImport = "CANCEL_IMPORT";
    public const string Adjustment = "ADJUSTMENT";    // Manual fix (phase 2)
}
```

#### 9.6.2 Ví dụ nhật ký biến động

```markdown
Product: Xi măng Hà Tiên | Stock hiện tại: 150 bao

StockMovements (lịch sử):
┌────┬────────────┬────────┬────────┬────────┬──────────────────────┐
│ #  │ Date       │ Delta  │ Before │ After  │ Reference            │
├────┼────────────┼────────┼────────┼────────┼──────────────────────┤
│ 1  │ 2026-01-15 │ +200   │ 0      │ 200    │ IMPORT #PNK-001      │
│ 2  │ 2026-01-20 │ -24    │ 200    │ 176    │ ORDER #ORD-005       │
│ 3  │ 2026-01-22 │ -48    │ 176    │ 128    │ ORDER #ORD-008       │
│ 4  │ 2026-01-25 │ +48    │ 128    │ 176    │ CANCEL_ORDER #ORD-008│
│ 5  │ 2026-02-01 │ +100   │ 176    │ 276    │ IMPORT #PNK-012      │
│ 6  │ 2026-02-10 │ -126   │ 276    │ 150    │ ORDER #ORD-015       │
└────┴────────────┴────────┴────────┴────────┴──────────────────────┘

Kiểm tra: SUM(Delta) = +200-24-48+48+100-126 = +150 ✅ = Product.Stock
```

#### 9.6.3 Khi nào ghi StockMovement?

Mọi thay đổi stock **phải** ghi StockMovement trong **cùng transaction** với update `Product.Stock`:

| Event | ReferenceType | Delta | Điều kiện |
|-------|--------------|-------|-----------|
| Order completed | `ORDER` | `-N` | `TrackInventory = true` |
| Order cancelled (từ completed) | `CANCEL_ORDER` | `+N` (rollback) | `TrackInventory = true` |
| Import confirmed | `IMPORT` | `+N` | `TrackInventory = true` |
| Import cancelled (từ confirmed) | `CANCEL_IMPORT` | `-N` (rollback) | `TrackInventory = true` |
| Manual adjustment (phase 2) | `ADJUSTMENT` | `+/-N` | Owner only |

**Pattern code (trong cùng transaction):**

```csharp
// Ví dụ: Confirm Import
public async Task ConfirmImportAsync(...)
{
    // ... validate ...
    
    foreach (var productImport in import.ProductImports)
    {
        var product = productImport.Product;
        if (product.TrackInventory == true)
        {
            var stockBefore = product.Stock;
            product.Stock += productImport.Quantity;
            
            // Ghi StockMovement trong CÙNG transaction
            var movement = new StockMovement
            {
                ProductId = product.ProductId,
                BusinessLocationId = product.BusinessLocationId,
                QuantityDelta = +productImport.Quantity,
                StockBefore = stockBefore,
                StockAfter = product.Stock,
                ReferenceType = StockMovementType.Import,
                ReferenceId = import.ImportId,
                CreatedAt = DateTime.UtcNow,
                CreatedBy = userId
            };
            
            await _unitOfWork.StockMovements.AddAsync(movement);
        }
        
        // Auto-update cached CostPrice (RULE-PROD-02)
        product.CostPrice = productImport.CostPrice;
    }
    
    await _unitOfWork.SaveChangesAsync(); // Atomic: stock + movement + costprice
}
```

#### 9.6.4 Reconciliation (Phase 2)

```csharp
// Job chạy định kỳ (hàng đêm) kiểm tra sai lệch
public async Task ReconcileStockAsync()
{
    var mismatches = await _dbContext.Products
        .Where(p => p.TrackInventory == true && p.DeletedAt == null)
        .Select(p => new {
            p.ProductId,
            p.ProductName,
            CurrentStock = p.Stock,
            CalculatedStock = p.StockMovements.Sum(m => m.QuantityDelta)
        })
        .Where(x => x.CurrentStock != x.CalculatedStock)
        .ToListAsync();
    
    // Alert / log mismatches
}
```

#### 9.6.5 Phase Plan

| Phase | Scope |
|-------|-------|
| **Phase 1 (now)** | Entity + Migration + Ghi log khi Import confirm/cancel + Order complete/cancel |
| **Phase 2** | Manual Adjustment API + Reconciliation job + Báo cáo XNT + UI lịch sử biến động |

### 9.7 Kiến trúc tổng thể

```markdown
                    ┌────────────────────────┐
                    │       Product           │
                    │  Stock: 500 (read path)  │
                    │  CostPrice: 80k (cached) │
                    └────────────┬───────────┘
                               │
          ┌───────────────┼────────────────┐
          │               │                │
          ▼               ▼                ▼
    ┌──────────┐ ┌──────────┐ ┌────────────────┐
    │  Order   │ │  Import  │ │ StockMovements │
    │  -Stock  │ │  +Stock  │ │ (immutable log)│
    └──────────┘ └──────────┘ └────────────────┘
          │               │                │
          └───────Cùng transaction───────┘
```

> **Nguyên tắc**: Mọi thay đổi `Product.Stock` **bắt buộc** kèm 1 dòng `StockMovement` trong cùng transaction. Không bao giờ thay đổi stock mà không ghi log.

---

## 10. API Endpoints Summary

| Method | Endpoint | Mô tả | Permission |
|--------|----------|-------|------------|
| `GET` | `/api/my-business/products?LocationId=1&...` | Search/filter products | Owner, Employee |
| `GET` | `/api/my-business/product/{productId}` | Product detail + SaleItems | Owner, Employee |
| `GET` | `/api/my-business/product/{productId}/sale-items` | Sale items only | Owner, Employee |
| `POST` | `/api/my-business/product` | Create product (multipart) | Owner only |
| `PUT` | `/api/my-business/product/{id}` | Update product (multipart) | Owner only |
| `PUT` | `/api/my-business/product/{productId}/status` | Toggle status | Owner only |
| `DELETE` | `/api/my-business/product/{productId}` | Soft/Hard delete | Owner only |

### Request/Response Summary

| Endpoint | Request DTO | Response DTO |
|----------|-------------|-------------|
| Search | `ProductQueryParams` | `PaginatedResponse<ProductListItemDto>` |
| Detail | — | `ProductDetailDto` |
| Sale Items | — | `ProductSaleItemsResponseDto` |
| Create | `CreateProductRequest` + file | `ProductListItemDto` |
| Update | `UpdateProductRequest` + file | `ProductListItemDto` |
| Status | `UpdateProductStatusRequest` | — |
| Delete | — | — |

---

## 11. Error Codes

| Code | HTTP | Mô tả |
|------|:----:|-------|
| `FORBIDDEN` | 403 | User không có quyền (không phải Owner hoặc không access được location) |
| `NOT_FOUND` | 404 | Product không tồn tại |
| `PRODUCT_DUPLICATE_UNIT_IN_PRICE_TIERS` | 400 | PriceTier có unit trùng base unit |
| `PRODUCT_DUPLICATE_SKU` | — | Warning: SKU trùng trong cùng location (không block, trả về trong `warnings[]`) |
| `PRODUCT_CANNOT_CHANGE_LOCATION` | 400 | Không cho đổi location khi update |
| `PRODUCT_INVALID_STATUS` | 400 | Status không hợp lệ |
| `PRODUCT_IMAGE_UPLOAD_FAILED` | 400 | Upload ảnh lên Cloudinary thất bại |
| `LOW_STOCK` | — | Warning: Tồn kho không đủ khi tạo order (không block, trả về trong `warnings[]`) |

---

## 12. Business Rules Summary

| Rule | Mô tả | Section |
|------|-------|--------|
| RULE-PROD-01 | Default SaleItem tự động tạo: Unit=base, Qty=1, Price=**SellingPrice** | [Create](#3-create-product-flow) |
| RULE-PROD-02 | CostPrice là cached value, auto-update từ Import gần nhất | [Create](#3-create-product-flow) |
| RULE-PROD-03 | SKU trùng trong location: cảnh báo (warning), không block | [Create](#3-create-product-flow) |
| RULE-PROD-04 | PriceTier Unit không được trùng Base Unit | [Create](#3-create-product-flow) |
| RULE-PROD-05 | Image Upload Rollback (xóa ảnh nếu DB save fail) | [Create](#3-create-product-flow) |
| RULE-PROD-06 | SaleItem Sync Strategy (Reconciliation khi update) | [Update](#5-update-product-flow) |
| RULE-PROD-07 | Không cho đổi Location | [Update](#5-update-product-flow) |
| RULE-PROD-08 | Image Update an toàn (upload mới trước, xóa cũ sau) | [Update](#5-update-product-flow) |
| RULE-PROD-09 | Smart Delete: Soft (có lịch sử) vs Hard (không lịch sử) | [Delete](#6-delete-product-flow) |
| RULE-PROD-10 | Cascade Soft Delete: Product → tất cả SaleItems | [Delete](#6-delete-product-flow) |
| RULE-STOCK-01 | Cảnh báo âm kho, không block order | [Stock](#9-stock-rules--integration) |
| RULE-STOCK-02 | TrackInventory=false: bỏ qua stock changes | [Stock](#9-stock-rules--integration) |
