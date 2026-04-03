# Import Flow Documentation (Nhập hàng)

> **Mục đích**: Document chi tiết các flow liên quan đến nhập hàng (Import) trong BizFlow Platform.

---

## Mục lục

1. [Tổng quan Import](#1-tổng-quan-import)
2. [Entity Design](#2-entity-design)
3. [Import Schema (Phiếu mua hàng không hóa đơn)](#3-import-schema-phiếu-mua-hàng-không-hóa-đơn)
4. [Create Import Flow](#4-create-import-flow)
5. [Confirm Import Flow](#5-confirm-import-flow)
6. [Delete & Cancel Import Flow](#6-delete--cancel-import-flow)
7. [View & Edit Import Flow](#7-view--edit-import-flow)
8. [Stock & Cost Price Rules](#8-stock--cost-price-rules)
9. [Accounting Integration (TT152)](#9-accounting-integration-tt152)
10. [API Endpoints Summary](#10-api-endpoints-summary)
11. [Error Codes](#11-error-codes)

---

## 1. Tổng quan Import

### Context - Nghiệp vụ nhập hàng HKD

Đối với hộ kinh doanh Việt Nam:

- Nhập hàng từ nhiều nguồn: nhà cung cấp, chợ đầu mối, đại lý
- **Có hóa đơn**: Nhà cung cấp xuất hóa đơn → owner lưu ảnh chụp hóa đơn
- **Không có hóa đơn**: Mua ở chợ, mua lẻ → theo TT152 phải lập **"Phiếu mua hàng hóa không có hóa đơn"**
- Owner cần track: *"Nhập gì, bao nhiêu, giá vốn bao nhiêu, nhập từ ai"*

### UX Design Principle: Progressive Disclosure

> **Nguyên tắc**: Target user là HKD không rành công nghệ. Flow nhập hàng phải **tối giản ở mặt FE**, đầy đủ ở mặt BE.

**Minimal Path (Con đường ngắn nhất)** — User chỉ cần:

```markdown
1. Chọn sản phẩm
2. Nhập số lượng
3. Bấm "Nhập kho" → XONG ✅
```

Tất cả thông tin khác đều **optional**, có thể **update sau**:

| Field | Bắt buộc? | Mặc định khi không nhập | Hiển thị trên report |
|-------|:---------:|------------------------|---------------------|
| Sản phẩm (ProductId) | ✅ Bắt buộc | — | — |
| Số lượng (Quantity) | ✅ Bắt buộc | — | — |
| Đơn vị (BaseUnit) | ✅ Bắt buộc | Product.Unit | — |
| Giá vốn (CostPrice) | ❌ Optional | `null` | ⚠️ "Chi phí chưa xác định"/phải có checkbox xác nhận chưa nhập giá vốn |
| Nhà cung cấp (Supplier) | ❌ Optional | `null` | "Chưa có thông tin NCC" |
| Ghi chú (Note) | ❌ Optional | `null` | — |
| Ngày nhận (ReceivedAt) | ❌ Optional | `CreatedAt` | — |
| Ảnh hóa đơn (Image) | ❌ Optional | `null` | — |
| Phiếu mua hàng (SchemaData) | ❌ Optional | `null` | — |
| Loại chứng từ (HasInvoice) | ❌ Optional | `true` | — |

> **FE Design**: Màn hình tạo phiếu chỉ yêu cầu nhập fields cốt lõi (sản phẩm + số lượng + giá).
> Fields khác có thể update sau.
> BE xử lý logic DRAFT → CONFIRMED phía sau, FE có thể tinh gọn.

> **Khi thiếu CostPrice**: Hệ thống vẫn cho nhập, nhưng report/dashboard hiển thị visual indicator
> ⚠️ "Có X phiếu nhập chưa cập nhật giá vốn" để user biết cần bổ sung.

### Import Type (Mục đích nhập)

| ImportType | Hiển thị (VI) | Mô tả |
|-----------|--------------|-------|
| `INVOICE` | Nhập hàng | Nhập hàng từ nhà cung cấp (mục đích chính) |
| `INVENTORY_ADJUSTMENT` | Điều chỉnh tồn kho | Cộng/trừ stock thủ công: hàng hư, kiểm kê chênh lệch, tìm thấy hàng thừa |
| `RETURN` | Trả hàng nhập lại | Khách trả hàng → nhập lại kho |

### HasInvoice (Loại chứng từ)

| HasInvoice | Mô tả | Action |
|:----------:|-------|--------|
| `true` | Có hóa đơn từ nhà cung cấp | Upload ảnh hóa đơn để lưu trữ (optional) |
| `false` | Không có hóa đơn | Fill phiếu mua hàng không hóa đơn theo TT152 (optional) để in ra và ký kết |

### Import Status Flow

```markdown
                      ┌─────────┐
                      │  DRAFT  │◄─── Tạo phiếu nhập (chưa confirm)
                      └────┬────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
      ┌───────────┐  ┌───────────┐  ┌───────────┐
      │ CONFIRMED │  │ HOT DELETE│  │  (Edit)   │
      └───────────┘  └───────────┘  └───────────┘
```

### Status Definitions

| Status | Code | Mô tả | Cho phép sửa? | Side effects? |
|--------|------|-------|:-------------:|:-------------:|
| **Draft** | `DRAFT` | Phiếu nhập tạo xong, chờ confirm | ✅ Edit trực tiếp | ❌ Chưa cộng kho |
| **Confirmed** | `CONFIRMED` | Đã xác nhận nhập kho | ❌ Phải cancel | ✅ Đã cộng kho + update giá vốn |
| **Cancelled** | `CANCELLED` | Đã hủy (chỉ từ CONFIRMED) | ❌ | ✅ Rollback kho + giá vốn |

> **Nguyên tắc quan trọng**:

> - Stock cộng + CostPrice update chỉ xảy ra khi chuyển sang **CONFIRMED**
> - Khi Cancel đơn CONFIRMED → rollback stock + recalculate CostPrice
> - DRAFT có thể **hot delete** (hard delete) — xóa hoàn toàn, không lưu lại record
> - CANCELLED chỉ áp dụng cho đơn đã CONFIRMED (cần giữ lại audit trail)
> *(Tương tự pattern Order: side effects chỉ ở Complete/Confirm)*

---

## 2. Entity Design

### Tables

```sql
-- =============================================
-- IMPORTS TABLE (Phiếu nhập hàng)
-- =============================================
CREATE TABLE Imports (
    ImportId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    ImportCode VARCHAR(50) NOT NULL COMMENT 'Auto-generated: PNK-YYYYMMDD-NNN',
    ImportType VARCHAR(50) NOT NULL DEFAULT 'INVOICE' COMMENT 'INVOICE | INVENTORY_ADJUSTMENT | RETURN',
    Status VARCHAR(20) NOT NULL DEFAULT 'DRAFT' COMMENT 'DRAFT | CONFIRMED | CANCELLED',
    
    -- Location
    BusinessLocationId INT NOT NULL,
    
    -- Chứng từ
    HasInvoice BOOLEAN NOT NULL DEFAULT TRUE COMMENT 'true=có hóa đơn, false=không hóa đơn',
    Supplier VARCHAR(200) DEFAULT NULL COMMENT 'Tên nhà cung cấp (free text)',
    
    -- Ảnh hóa đơn (khi HasInvoice = true)
    ImageUrl VARCHAR(500) DEFAULT NULL COMMENT 'URL ảnh hóa đơn (Cloudinary)',
    ImagePublicId VARCHAR(100) DEFAULT NULL COMMENT 'Cloudinary public ID',
    
    -- Schema phiếu mua hàng không hóa đơn (khi HasInvoice = false)
    SchemaVersionId INT DEFAULT NULL COMMENT 'Version schema đã dùng (snapshot)',
    SchemaDataJson LONGTEXT DEFAULT NULL COMMENT 'Dữ liệu user đã fill vào template',
    
    -- Tổng tiền
    TotalAmount DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'Tổng tiền nhập = SUM(ProductImports.TotalPrice)',
    
    -- Metadata
    Note TEXT DEFAULT NULL COMMENT 'Ghi chú / diễn giải',
    ReceivedAt DATETIME DEFAULT NULL COMMENT 'Ngày thực tế nhận hàng',
    
    -- Audit
    CreatedByUserId CHAR(36) NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    ConfirmedAt DATETIME DEFAULT NULL,
    ConfirmedByUserId CHAR(36) DEFAULT NULL,
    CancelledAt DATETIME DEFAULT NULL,
    CancelledByUserId CHAR(36) DEFAULT NULL,
    CancelReason TEXT DEFAULT NULL,
    
    -- Indexes & FKs
    CONSTRAINT fk_import_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    CONSTRAINT fk_import_schema_version FOREIGN KEY (SchemaVersionId)
        REFERENCES ImportSchemaVersions(ImportSchemaVersionId),
    UNIQUE INDEX idx_import_code (ImportCode),
    INDEX idx_import_status (Status),
    INDEX idx_import_type (ImportType),
    INDEX idx_import_location (BusinessLocationId),
    INDEX idx_import_created (CreatedAt),
    INDEX idx_import_has_invoice (HasInvoice)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- PRODUCT IMPORTS TABLE (Chi tiết phiếu nhập - Junction)
-- =============================================
CREATE TABLE ProductImports (
    ProductImportId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    ImportId BIGINT NOT NULL,
    ProductId BIGINT NOT NULL,
    
    -- Số lượng & giá
    Quantity INT NOT NULL COMMENT 'Số lượng (dương=nhập, âm=điều chỉnh giảm cho INVENTORY_ADJUSTMENT)',
    CostPrice DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'Giá vốn / đơn vị (0 = chưa xác định)',
    TotalPrice DECIMAL(15,2) NOT NULL DEFAULT 0 COMMENT 'Quantity × CostPrice',
    BaseUnit VARCHAR(50) NOT NULL COMMENT 'Đơn vị tính nhỏ nhất (bao, kg, cái...)',
    
    -- Audit
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_product_import_import FOREIGN KEY (ImportId) 
        REFERENCES Imports(ImportId) ON DELETE CASCADE,
    CONSTRAINT fk_product_import_product FOREIGN KEY (ProductId)
        REFERENCES Products(ProductId),
    INDEX idx_product_import_import (ImportId),
    INDEX idx_product_import_product (ProductId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### Entity Classes

```csharp
public class Import
{
    public long ImportId { get; set; }
    public string ImportCode { get; set; } = null!;
    public string ImportType { get; set; } = "INVOICE";
    public string Status { get; set; } = "DRAFT";
    
    // Location
    public int BusinessLocationId { get; set; }
    
    // Chứng từ
    public bool HasInvoice { get; set; } = true;
    public string? Supplier { get; set; }
    
    // Ảnh hóa đơn
    public string? ImageUrl { get; set; }
    public string? ImagePublicId { get; set; }
    
    // Schema (phiếu mua hàng không hóa đơn)
    public int? SchemaVersionId { get; set; }
    public string? SchemaDataJson { get; set; }
    
    // Money
    public decimal TotalAmount { get; set; }
    
    // Metadata
    public string? Note { get; set; }
    public DateTime? ReceivedAt { get; set; }
    
    // Audit
    public Guid CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? UpdatedAt { get; set; }
    public DateTime? ConfirmedAt { get; set; }
    public Guid? ConfirmedByUserId { get; set; }
    public DateTime? CancelledAt { get; set; }
    public Guid? CancelledByUserId { get; set; }
    public string? CancelReason { get; set; }
    
    // Navigation
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
    public virtual ImportSchemaVersion? SchemaVersion { get; set; }
    public virtual User CreatedByUser { get; set; } = null!;
    public virtual ICollection<ProductImport> ProductImports { get; set; } = new List<ProductImport>();
}

public class ProductImport
{
    public long ProductImportId { get; set; }
    public long ImportId { get; set; }
    public long ProductId { get; set; }
    
    // Quantity & Cost
    public int Quantity { get; set; }       // Dương = nhập, Âm = điều chỉnh giảm (INVENTORY_ADJUSTMENT)
    public decimal CostPrice { get; set; }  // 0 = chưa xác định, user có thể update sau
    public decimal TotalPrice { get; set; }
    public string BaseUnit { get; set; } = null!;
    
    // Audit
    public DateTime CreatedAt { get; set; }
    
    // Navigation
    public virtual Import Import { get; set; } = null!;
    public virtual Product Product { get; set; } = null!;
}

public enum ImportStatus
{
    Draft,
    Confirmed,
    Cancelled
}

public static class ImportTypes
{
    public const string Invoice = "INVOICE";
    public const string InventoryAdjustment = "INVENTORY_ADJUSTMENT";
    public const string Return = "RETURN";
}
```

### So sánh với Entity hiện tại (Cần migration)

| Field | Hiện tại | Sau update | Change type |
|-------|---------|-----------|:-----------:|
| `HasInvoice` | ❌ | `BOOLEAN DEFAULT TRUE` | ADD |
| `SchemaVersionId` | ❌ | `INT FK → ImportSchemaVersions` | ADD |
| `SchemaDataJson` | ❌ (có `SchemaJson`) | `LONGTEXT` | RENAME + change purpose |
| `CreatedByUserId` | ❌ | `CHAR(36) NOT NULL` | ADD |
| `ConfirmedAt` | ❌ | `DATETIME NULL` | ADD |
| `ConfirmedByUserId` | ❌ | `CHAR(36) NULL` | ADD |
| `CancelledAt` | ❌ | `DATETIME NULL` | ADD |
| `CancelledByUserId` | ❌ | `CHAR(36) NULL` | ADD |
| `CancelReason` | ❌ | `TEXT NULL` | ADD |
| `ProductImportId` | ❌ (composite PK) | `BIGINT AUTO_INCREMENT PK` | ADD + change PK |

---

## 3. Import Schema (Phiếu mua hàng không hóa đơn)

> **Optional Feature**: Phiếu mua hàng không hóa đơn là tính năng **hỗ trợ**, không bắt buộc trong flow nhập hàng.
> User có thể nhập hàng xong rồi quay lại in phiếu sau, hoặc không in nếu không cần.

### Context - Quy định TT152

Theo Thông tư 152/2025/TT-BTC:

- Khi mua hàng hóa **không có hóa đơn** → phải lập **"Phiếu mua hàng hóa không có hóa đơn"**
- Template phiếu này được quy định từ trước (nhưng chưa có update mới để phù hợp sau khi đổi sang dùng CCCD thay vì CMND)
- BizFlow cung cấp template điện tử, user chỉ cần fill thông tin
- User có thể **in ra giấy** để ký xác nhận với người bán (theo quy định)

### Schema Processing Flow

```
1. Admin/Consultant → upload SchemaJson (định nghĩa fields, rules) + TemplateFileUrl (file .xlsx/.docx template)
2. FE → GET active schema version → render form động từ SchemaJson
3. Hệ thống auto-fill: BusinessLocation info + Import info (Supplier, ReceivedAt, Items...)
4. User nhập thêm thông tin thủ công (địa chỉ người bán, CCCD...) → optional
5. FE → save SchemaDataJson (dữ liệu user đã fill)
6. Khi cần export → BE mapping SchemaDataJson → TemplateFile → xuất file .docx/.pdf
7. User → download file hoặc print trực tiếp từ browser
```

### Schema Architecture

```markdown
ImportSchema (Template type)
├── ImportSchemaId
├── TemplateCode: "PHIEU_MUA_HANG_KHONG_HOA_DON"
├── Name: "Phiếu mua hàng hóa không có hóa đơn"
├── IsActive: true
├── EverActivated: true
│
└── ImportSchemaVersions (Versioned definitions)
    ├── Version 1 (IsActive: false, EffectiveFrom: 2026-01-01)
    │   ├── SchemaJson: { ... field definitions ... }
    │   ├── MappingJson: { ... DB ↔ export file mapping ... }
    │   └── TemplateFileUrl: "/templates/phieu-mua-hang-v1.xlsx"
    │
    └── Version 2 (IsActive: true, EffectiveFrom: 2026-07-01)
        ├── SchemaJson: { ... updated fields ... }
        ├── MappingJson: { ... updated mapping ... }
        └── TemplateFileUrl: "/templates/phieu-mua-hang-v2.xlsx"
```

### Schema Entity (Updated)

```sql
-- =============================================
-- IMPORT SCHEMAS TABLE (Template types)
-- Managed by: Admin / Consultant
-- =============================================
CREATE TABLE ImportSchemas (
    ImportSchemaId INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    TemplateCode VARCHAR(50) NOT NULL COMMENT 'Unique code: PHIEU_MUA_HANG_KHONG_HOA_DON',
    Name VARCHAR(100) NOT NULL COMMENT 'Tên template',
    IsActive BOOLEAN DEFAULT FALSE COMMENT 'Template có khả dụng không',
    EverActivated BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Đã từng active chưa (gates delete)',
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    DeletedAt DATETIME DEFAULT NULL COMMENT 'Soft delete',
    
    UNIQUE INDEX idx_schema_template_code (TemplateCode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- IMPORT SCHEMA VERSIONS TABLE (Versioned definitions)
-- Mỗi schema có nhiều versions, chỉ 1 active tại 1 thời điểm
-- =============================================
CREATE TABLE ImportSchemaVersions (
    ImportSchemaVersionId INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    ImportSchemaId INT NOT NULL,
    
    -- Schema definition
    SchemaJson LONGTEXT NOT NULL COMMENT 'JSON schema: field definitions, validation rules',
    MappingJson LONGTEXT DEFAULT NULL COMMENT 'Mapping DB fields ↔ export file fields',
    TemplateFileUrl VARCHAR(500) DEFAULT NULL COMMENT 'URL file template (Excel/PDF) để xuất',
    
    -- Versioning
    VersionLabel VARCHAR(20) DEFAULT NULL COMMENT 'v1.0, v2.0...',
    IsActive BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Chỉ 1 version active / schema',
    EffectiveFrom DATETIME DEFAULT NULL COMMENT 'Ngày bắt đầu hiệu lực',
    
    -- Audit
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CreatedByUserId CHAR(36) DEFAULT NULL,
    
    CONSTRAINT fk_schema_version_schema FOREIGN KEY (ImportSchemaId)
        REFERENCES ImportSchemas(ImportSchemaId) ON DELETE CASCADE,
    INDEX idx_schema_version_schema (ImportSchemaId),
    INDEX idx_schema_version_active (IsActive)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### Schema Entity Classes (Updated)

```csharp
public class ImportSchema
{
    public int ImportSchemaId { get; set; }
    public string TemplateCode { get; set; } = null!;
    public string Name { get; set; } = null!;
    public bool IsActive { get; set; }
    public bool EverActivated { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? DeletedAt { get; set; }
    
    public virtual ICollection<ImportSchemaVersion> Versions { get; set; } = new List<ImportSchemaVersion>();
}

public class ImportSchemaVersion
{
    public int ImportSchemaVersionId { get; set; }
    public int ImportSchemaId { get; set; }
    
    // Schema definition
    public string SchemaJson { get; set; } = null!;
    public string? MappingJson { get; set; }
    public string? TemplateFileUrl { get; set; }
    
    // Versioning
    public string? VersionLabel { get; set; }
    public bool IsActive { get; set; }
    public DateTime? EffectiveFrom { get; set; }
    
    // Audit
    public DateTime CreatedAt { get; set; }
    public Guid? CreatedByUserId { get; set; }
    
    // Navigation
    public virtual ImportSchema ImportSchema { get; set; } = null!;
}
```

### SchemaJson Example (Phiếu mua hàng không hóa đơn)

```json
{
  "templateName": "Phiếu mua hàng hóa không có hóa đơn",
  "regulation": "Thông tư 152/2025/TT-BTC",
  "sections": [
    {
      "id": "header",
      "label": "Thông tin chung",
      "fields": [
        {
          "id": "business_name",
          "label": "Tên hộ kinh doanh",
          "type": "text",
          "required": true,
          "source": "auto",
          "sourceField": "BusinessLocation.Name"
        },
        {
          "id": "business_address",
          "label": "Địa chỉ",
          "type": "text",
          "required": true,
          "source": "auto",
          "sourceField": "BusinessLocation.Address"
        },
        {
          "id": "tax_code",
          "label": "Mã số thuế",
          "type": "text",
          "required": false,
          "source": "auto",
          "sourceField": "BusinessLocation.TaxCode"
        },
        {
          "id": "purchase_date",
          "label": "Ngày mua hàng",
          "type": "date",
          "required": true,
          "source": "auto",
          "sourceField": "Import.ReceivedAt"
        }
      ]
    },
    {
      "id": "supplier_info",
      "label": "Thông tin người bán",
      "fields": [
        {
          "id": "supplier_name",
          "label": "Họ tên người bán hàng",
          "type": "text",
          "required": true,
          "source": "auto",
          "sourceField": "Import.Supplier"
        },
        {
          "id": "supplier_address",
          "label": "Địa chỉ người bán",
          "type": "text",
          "required": false,
          "source": "manual"
        },
        {
          "id": "supplier_id_number",
          "label": "Số CMND/CCCD người bán",
          "type": "text",
          "required": false,
          "source": "manual"
        }
      ]
    },
    {
      "id": "items",
      "label": "Chi tiết hàng hóa mua",
      "type": "table",
      "columns": [
        { "id": "stt", "label": "STT", "type": "auto_increment" },
        { "id": "product_name", "label": "Tên hàng hóa", "source": "auto", "sourceField": "Product.ProductName" },
        { "id": "unit", "label": "Đơn vị tính", "source": "auto", "sourceField": "ProductImport.BaseUnit" },
        { "id": "quantity", "label": "Số lượng", "source": "auto", "sourceField": "ProductImport.Quantity" },
        { "id": "unit_price", "label": "Đơn giá", "source": "auto", "sourceField": "ProductImport.CostPrice" },
        { "id": "total_price", "label": "Thành tiền", "source": "auto", "sourceField": "ProductImport.TotalPrice" }
      ]
    },
    {
      "id": "footer",
      "label": "Ký xác nhận",
      "fields": [
        {
          "id": "total_amount_words",
          "label": "Tổng tiền (bằng chữ)",
          "type": "text",
          "required": false,
          "source": "auto_generated"
        },
        {
          "id": "buyer_signature",
          "label": "Người mua hàng (ký, ghi rõ họ tên)",
          "type": "signature",
          "required": false,
          "source": "manual"
        },
        {
          "id": "seller_signature",
          "label": "Người bán hàng (ký, ghi rõ họ tên)",
          "type": "signature",
          "required": false,
          "source": "manual"
        }
      ]
    }
  ]
}
```

### MappingJson Example

```json
{
  "exportFormat": "xlsx",
  "templateFile": "phieu-mua-hang-v1.xlsx",
  "mappings": [
    { "schemaField": "header.business_name", "cell": "B3" },
    { "schemaField": "header.business_address", "cell": "B4" },
    { "schemaField": "header.tax_code", "cell": "B5" },
    { "schemaField": "header.purchase_date", "cell": "E3", "format": "dd/MM/yyyy" },
    { "schemaField": "supplier_info.supplier_name", "cell": "B7" },
    { "schemaField": "supplier_info.supplier_address", "cell": "B8" },
    { "schemaField": "supplier_info.supplier_id_number", "cell": "B9" },
    { "schemaField": "items", "startRow": 12, "columns": {
        "stt": "A", "product_name": "B", "unit": "C",
        "quantity": "D", "unit_price": "E", "total_price": "F"
    }},
    { "schemaField": "footer.total_amount_words", "cell": "B{lastRow+2}" }
  ]
}
```

### Quản lý Schema (Admin/Consultant)

| Action | Who | Description |
|--------|-----|-------------|
| Xem danh sách schemas | Admin, Consultant | List all template types |
| Tạo schema version mới | Admin, Consultant | Khi TT152 thay đổi template |
| Activate version | Admin, Consultant | Set version active (deactivate old) |
| Xem preview | Admin, Consultant | Preview với sample data |

---

## 4. Create Import Flow

### Use Case

Owner tạo phiếu nhập hàng khi nhận hàng từ nhà cung cấp hoặc điều chỉnh kho.

### Required vs Optional Fields

| Field | Required? | Default | Note |
|-------|:---------:|---------|------|
| `businessLocationId` | ✅ | — | Location hiện tại |
| `items[].productId` | ✅ | — | Chọn từ danh sách sản phẩm |
| `items[].quantity` | ✅ | — | Số lượng nhập |
| `items[].baseUnit` | ✅ | Product.Unit | Lấy từ Product |
| `items[].costPrice` | ❌ | `0` | 0 = chưa xác định, cập nhật sau |
| `importType` | ❌ | `INVOICE` | FE có thể ẩn |
| `hasInvoice` | ❌ | `true` | Toggle đơn giản |
| `supplier` | ❌ | `null` | Free text |
| `receivedAt` | ❌ | `CreatedAt` | Ngày thực tế nhận hàng |
| `note` | ❌ | `null` | Hệ thống gợi ý (suggestedNote) |
| `image` | ❌ | `null` | Ảnh hóa đơn |
| `schemaData` | ❌ | `null` | Phiếu TT152 |

### Minimal Path Example (Fastest UX)

```yaml
# User chỉ chọn sản phẩm + nhập số lượng, không điền gì thêm:
POST /api/imports?autoConfirm=true
{
  "businessLocationId": 1,
  "items": [
    { "productId": 1, "quantity": 50, "baseUnit": "bao" },
    { "productId": 2, "quantity": 100, "baseUnit": "kg" }
  ]
}

# BE tự động:
# - importType = "INVOICE" (default)
# - hasInvoice = true (default)
# - costPrice = 0 cho mỗi item (chưa xác định)
# - receivedAt = CreatedAt
# - suggestedNote = auto-generate
# - autoConfirm = true → DRAFT → CONFIRMED ngay
```

> **FE Tip**: FE có thể gom `POST /imports` + `POST /imports/{id}/confirm` thành 1 action "Nhập kho",
> bằng query param `?autoConfirm=true` để BE tự confirm luôn.

### Sequence Diagram

```
┌─────────┐     ┌─────────┐     ┌─────────────┐     ┌──────────┐
│  Owner  │     │  App    │     │  Backend    │     │    DB    │
└────┬────┘     └────┬────┘     └──────┬──────┘     └────┬─────┘
     │               │                 │                 │
     │ Click "Nhập   │                 │                 │
     │  hàng"        │                 │                 │
     │──────────────►│                 │                 │
     │               │                 │                 │
     │ Chọn:         │                 │                 │
     │ ○ Có hóa đơn  │                 │                 │
     │ ○ Không HĐ    │                 │                 │
     │──────────────►│                 │                 │
     │               │                 │                 │
     │ Nhập thông tin│                 │                 │
     │ - NCC, ngày   │                 │                 │
     │ - Sản phẩm    │                 │                 │
     │ - Số lượng,giá│                 │                 │
     │ - Upload ảnh  │                 │                 │
     │   (nếu có HĐ) │                 │                 │
     │──────────────►│                 │                 │
     │               │                 │                 │
     │ Submit Draft  │ POST /imports   │                 │
     │──────────────►│────────────────►│                 │
     │               │                 │                 │
     │               │                 │ Validate        │
     │               │                 │ - Location access│
     │               │                 │ - Products exist │
     │               │                 │ - Amounts valid  │
     │               │                 │                 │
     │               │                 │ Generate code   │
     │               │                 │ PNK-YYYYMMDD-NNN│
     │               │                 │                 │
     │               │                 │ Suggest Note    │
     │               │                 │ (auto-generate) │
     │               │                 │                 │
     │               │                 │ Create Import   │
     │               │                 │ Status = DRAFT  │
     │               │                 │ KHÔNG cộng kho  │
     │               │                 │────────────────►│
     │               │                 │◄────────────────│
     │               │                 │                 │
     │               │◄────────────────│                 │
     │ Draft created │                 │                 │
     │ (chưa cộng kho)                 │                 │
     │◄──────────────│                 │                 │
```

### API Contract

```yaml
POST /api/imports
Authorization: Bearer {token}

# Option 1: Có hóa đơn + upload ảnh
Request (multipart/form-data):
{
  "businessLocationId": 1,
  "importType": "INVOICE",
  "hasInvoice": true,
  "supplier": "Công ty TNHH Xi Măng Hà Tiên",
  "receivedAt": "2026-02-27T10:00:00Z",
  "note": "Nhập xi măng đợt 2 tháng 2",    # Optional, BE có thể gợi ý
  "image": <file>,                            # Optional - ảnh hóa đơn
  "items": [
    {
      "productId": 1,
      "quantity": 100,
      "costPrice": 95000,
      "baseUnit": "bao"
    },
    {
      "productId": 1,
      "quantity": 50,
      "costPrice": 90000,
      "baseUnit": "bao"
    },
    {
      "productId": 2,
      "quantity": 200,
      "costPrice": 12000,
      "baseUnit": "kg"
    }
  ]
}

# Option 2: Không hóa đơn
Request:
{
  "businessLocationId": 1,
  "importType": "INVOICE",
  "hasInvoice": false,
  "supplier": "Chị Hương - chợ Bà Chiểu",
  "receivedAt": "2026-02-27T08:00:00Z",
  "note": "Mua lẻ ở chợ",
  "schemaData": {                             # Optional - fill phiếu mua hàng
    "supplier_address": "Sạp 15, chợ Bà Chiểu, Q.Bình Thạnh",
    "supplier_id_number": "079123456789"
  },
  "items": [
    {
      "productId": 3,
      "quantity": 20,
      "costPrice": 45000,
      "baseUnit": "kg"
    }
  ]
}

# Response (201 Created):
{
  "success": true,
  "data": {
    "importId": 101,
    "importCode": "PNK-20260227-001",
    "importType": "INVOICE",
    "status": "DRAFT",
    "hasInvoice": true,
    "supplier": "Công ty TNHH Xi Măng Hà Tiên",
    "imageUrl": "https://res.cloudinary.com/.../pnk-20260227-001.jpg",
    "totalAmount": 11900000,
    "note": "Nhập xi măng đợt 2 tháng 2",
    "suggestedNote": "Nhập hàng từ Công ty TNHH Xi Măng Hà Tiên: Xi măng Hà Tiên x150, Cát xây dựng x200",
    "receivedAt": "2026-02-27T10:00:00Z",
    "items": [
      {
        "productImportId": 1,
        "productId": 1,
        "productName": "Xi măng Hà Tiên",
        "quantity": 100,
        "costPrice": 95000,
        "totalPrice": 9500000,
        "baseUnit": "bao",
        "currentStock": 150
      },
      {
        "productImportId": 2,
        "productId": 1,
        "productName": "Xi măng Hà Tiên",
        "quantity": 50,
        "costPrice": 90000,
        "totalPrice": 4500000,
        "baseUnit": "bao",
        "currentStock": 150
      }
    ],
    "createdAt": "2026-02-27T09:30:00Z",
    "createdByName": "Nguyễn Văn A"
  }
}
```

> **Lưu ý**: Cùng 1 product (Xi măng) có thể xuất hiện 2 lần với giá khác nhau (2 lô nhập khác giá).
> `ProductImportId` (auto-increment) cho phép điều này.

### Business Rules

**RULE-IMPORT-01: Chỉ Owner tạo được phiếu nhập**

```csharp
var assignment = await _unitOfWork.UserLocationAssignments
    .GetByUserAndLocationAsync(userId, request.BusinessLocationId);
    
if (assignment == null || !assignment.IsOwner)
    throw new ForbiddenException("Only owner can create imports");
```

**RULE-IMPORT-02: Validate products thuộc location**

```csharp
foreach (var item in request.Items)
{
    var product = await _unitOfWork.Products.GetByIdAsync(item.ProductId);
    if (product == null || product.DeletedAt != null)
        throw new NotFoundException($"Product {item.ProductId} not found");
    
    if (product.BusinessLocationId != request.BusinessLocationId)
        throw new ValidationException($"Product {product.ProductName} does not belong to this location");
}
```

**RULE-IMPORT-03: Validate amounts**

```csharp
foreach (var item in request.Items)
{
    // INVOICE/RETURN: Quantity > 0 | INVENTORY_ADJUSTMENT: Quantity ≠ 0
    if (request.ImportType == ImportTypes.InventoryAdjustment)
    {
        if (item.Quantity == 0)
            throw new ValidationException("Adjustment quantity cannot be zero");
    }
    else if (item.Quantity <= 0)
    {
        throw new ValidationException("Quantity must be positive");
    }
    
    if (item.CostPrice < 0)
        throw new ValidationException("Cost price cannot be negative");
    // CostPrice = 0 → chấp nhận (chưa xác định, user update sau)
    
    // TotalPrice = Quantity × CostPrice (BE tính, không tin FE)
    item.TotalPrice = item.Quantity * item.CostPrice;
}

// TotalAmount = SUM(items.TotalPrice)
import.TotalAmount = request.Items.Sum(i => i.Quantity * i.CostPrice);
```

**RULE-IMPORT-04: Auto-generate ImportCode**

```csharp
// Format: PNK-YYYYMMDD-NNN (NNN = sequential per day per location)
var today = DateTime.UtcNow.ToString("yyyyMMdd");
var count = await _unitOfWork.Imports
    .CountAsync(i => i.BusinessLocationId == request.BusinessLocationId
                  && i.ImportCode.StartsWith($"PNK-{today}"));
var importCode = $"PNK-{today}-{(count + 1):D3}";
```

**RULE-IMPORT-05: Suggest Note (Gợi ý diễn giải)**

```csharp
// Hệ thống gợi ý diễn giải dựa trên thông tin nhập
// User có thể dùng hoặc sửa lại
var productSummary = string.Join(", ", 
    request.Items
        .GroupBy(i => i.ProductId)
        .Select(g => $"{g.First().ProductName} x{g.Sum(i => i.Quantity)}"));

var suggestedNote = $"Nhập hàng từ {request.Supplier ?? "N/A"}: {productSummary}";
```

**RULE-IMPORT-06: Schema data validation (khi không có hóa đơn)**

```csharp
if (!request.HasInvoice && request.SchemaData != null)
{
    // Lấy active schema version
    var schema = await _unitOfWork.ImportSchemas
        .GetActiveVersionByCodeAsync("PHIEU_MUA_HANG_KHONG_HOA_DON");
    
    if (schema != null)
    {
        import.SchemaVersionId = schema.ImportSchemaVersionId;
        import.SchemaDataJson = JsonSerializer.Serialize(request.SchemaData);
        
        // Validate against schema (optional - chỉ warning, không block)
        // Vì phiếu là optional, user có thể không fill đủ
    }
}
```

---

## 5. Confirm Import Flow

### Use Case

Owner xác nhận phiếu nhập → cộng stock + update giá vốn.

### Flow Diagram

```
┌─────────────────┐
│  Import DRAFT   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐
│ Owner clicks "Xác nhận" │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Validate:               │
│ - Status == DRAFT       │
│ - User is Owner         │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ For each ProductImport: │
│                         │
│ 1. Cộng Stock           │
│    Product.Stock += Qty │
│    (nếu TrackInventory) │
│                         │
│ 2. Update CostPrice     │
│    Weighted Average     │
│    (xem Section 8)      │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│ Update Import:          │
│ - Status = CONFIRMED    │
│ - ConfirmedAt = now     │
│ - ConfirmedByUserId     │
└────────────┬────────────┘
             │
             ▼
         ✅ Done
```

### API Contract

```yaml
POST /api/imports/{id}/confirm
Authorization: Bearer {token}

# Response (200 OK):
{
  "success": true,
  "data": {
    "importId": 101,
    "importCode": "PNK-20260227-001",
    "status": "CONFIRMED",
    "confirmedAt": "2026-02-27T10:30:00Z",
    "confirmedByName": "Nguyễn Văn A",
    "stockUpdates": [
      {
        "productId": 1,
        "productName": "Xi măng Hà Tiên",
        "quantityAdded": 150,
        "stockBefore": 150,
        "stockAfter": 300,
        "costPriceBefore": 92000,
        "costPriceAfter": 93000,
        "costPriceMethod": "weighted_average"
      },
      {
        "productId": 2,
        "productName": "Cát xây dựng",
        "quantityAdded": 200,
        "stockBefore": 500,
        "stockAfter": 700,
        "costPriceBefore": 11500,
        "costPriceAfter": 11714,
        "costPriceMethod": "weighted_average"
      }
    ]
  }
}
```

### Business Rules

**RULE-CONFIRM-01: Chỉ Owner confirm**

```csharp
if (!isOwner)
    throw new ForbiddenException("Only owner can confirm imports");
```

**RULE-CONFIRM-02: Chỉ DRAFT → CONFIRMED**

```csharp
if (import.Status != ImportStatus.Draft)
    throw new ValidationException("Only draft imports can be confirmed");
```

**RULE-CONFIRM-03: Stock + CostPrice update (xem chi tiết Section 8)**

```csharp
foreach (var item in import.ProductImports)
{
    var product = await _unitOfWork.Products.GetByIdAsync(item.ProductId);
    
    if (product.TrackInventory == true)
    {
        // Weighted average cost price
        var oldTotal = product.Stock * product.CostPrice;
        var newTotal = item.Quantity * item.CostPrice;
        var newStock = product.Stock + item.Quantity;
        
        product.CostPrice = newStock > 0 
            ? (oldTotal + newTotal) / newStock 
            : item.CostPrice;
        product.Stock = newStock;
    }
}
```

---

## 6. Delete & Cancel Import Flow

### Delete DRAFT (Hot Delete)

DRAFT chưa có side effects → **hard delete** (xóa hoàn toàn khỏi DB, không giữ record).

```yaml
DELETE /api/imports/{id}
Authorization: Bearer {token}

# Chỉ cho phép khi Status = DRAFT
# Hard delete: xóa Import + ProductImports

Response (200 OK):
{
  "success": true,
  "data": {
    "importId": 101,
    "importCode": "PNK-20260227-001",
    "deleted": true
  }
}
```

> **Lý do hot delete**: DRAFT chưa tạo side effects (chưa cộng kho, chưa update giá vốn).
> Không cần giữ record cho audit trail. User có thể tạo lại phiếu mới.

### Cancel CONFIRMED (Rollback stock + giá vốn)

Phải rollback stock và recalculate giá vốn.

```
┌────────────────────┐
│  Import CONFIRMED  │
└─────────┬──────────┘
          │
          ▼
┌──────────────────────────────┐
│ Owner clicks "Hủy phiếu"     │
│ + Nhập lý do                 │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│ Validate:                    │
│ - Status == CONFIRMED        │
│ - User is Owner              │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│ For each ProductImport:      │
│                              │
│ 1. Rollback Stock            │
│    Product.Stock -= Qty      │
│    (nếu TrackInventory)      │
│                              │
│ 2. Recalculate CostPrice     │
│    Reverse weighted average  │
│    (xem Section 8)           │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│ Check: Stock < 0 sau rollback│
│ → WARNING (vẫn cho cancel)   │
│ Lý do: đã bán 1 phần hàng    │
│ Stock sẽ bị âm               │
└─────────────┬────────────────┘
              │
              ▼
┌──────────────────────────────┐
│ Update Import:               │
│ - Status = CANCELLED         │
│ - CancelledAt = now          │
│ - CancelledByUserId          │
│ - CancelReason               │
└─────────────┬────────────────┘
              │
              ▼
          ✅ Done
```

```yaml
POST /api/imports/{id}/cancel
Authorization: Bearer {token}

Request:
{
  "cancelReason": "NCC giao sai hàng, trả lại"
}

Response (200 OK):
{
  "success": true,
  "data": {
    "importId": 101,
    "status": "CANCELLED",
    "cancelledAt": "2026-02-27T15:00:00Z",
    "rollbackApplied": true,
    "stockRollbacks": [
      {
        "productId": 1,
        "productName": "Xi măng Hà Tiên",
        "quantityRemoved": 150,
        "stockBefore": 300,
        "stockAfter": 150,
        "warning": null
      },
      {
        "productId": 2,
        "productName": "Cát xây dựng",
        "quantityRemoved": 200,
        "stockBefore": 180,
        "stockAfter": -20,
        "warning": "Stock âm sau rollback (-20). Có thể đã bán một phần hàng nhập."
      }
    ]
  }
}
```

---

## 7. View & Edit Import Flow

### List Imports

```yaml
GET /api/imports?locationId=1&status=CONFIRMED&from=2026-02-01&to=2026-02-28
Authorization: Bearer {token}

Query Parameters:
- locationId (required): Business location ID
- status (optional): DRAFT | CONFIRMED | CANCELLED
- importType (optional): INVOICE | INVENTORY_ADJUSTMENT | RETURN
- hasInvoice (optional): true | false
- from (optional): Start date
- to (optional): End date
- supplier (optional): Search by supplier name
- page (optional): Page number (default: 1)
- pageSize (optional): Items per page (default: 20)
- sortBy (optional): createdAt, totalAmount, importCode (default: createdAt)
- sortDir (optional): asc, desc (default: desc)

Response:
{
  "items": [
    {
      "importId": 101,
      "importCode": "PNK-20260227-001",
      "importType": "INVOICE",
      "status": "CONFIRMED",
      "hasInvoice": true,
      "supplier": "Công ty Xi Măng Hà Tiên",
      "totalAmount": 11900000,
      "itemCount": 3,
      "receivedAt": "2026-02-27T10:00:00Z",
      "confirmedAt": "2026-02-27T10:30:00Z",
      "createdByName": "Nguyễn Văn A"
    }
  ],
  "totalCount": 45,
  "page": 1,
  "pageSize": 20,
  "summary": {
    "totalImports": 45,
    "totalAmount": 125000000,
    "draftCount": 3,
    "confirmedCount": 38,
    "cancelledCount": 4
  }
}
```

### Import Detail

```yaml
GET /api/imports/101
Authorization: Bearer {token}

Response:
{
  "importId": 101,
  "importCode": "PNK-20260227-001",
  "importType": "INVOICE",
  "status": "CONFIRMED",
  "hasInvoice": true,
  "supplier": "Công ty Xi Măng Hà Tiên",
  "imageUrl": "https://res.cloudinary.com/.../pnk-001.jpg",
  "totalAmount": 11900000,
  "note": "Nhập xi măng đợt 2 tháng 2",
  "receivedAt": "2026-02-27T10:00:00Z",
  
  "items": [
    {
      "productImportId": 1,
      "productId": 1,
      "productName": "Xi măng Hà Tiên",
      "sku": "XM-HT-50",
      "quantity": 100,
      "costPrice": 95000,
      "totalPrice": 9500000,
      "baseUnit": "bao",
      "currentStock": 300
    },
    {
      "productImportId": 2,
      "productId": 1,
      "productName": "Xi măng Hà Tiên",
      "sku": "XM-HT-50",
      "quantity": 50,
      "costPrice": 90000,
      "totalPrice": 4500000,
      "baseUnit": "bao",
      "currentStock": 300
    }
  ],
  
  "schemaData": null,
  
  "audit": {
    "createdByName": "Nguyễn Văn A",
    "createdAt": "2026-02-27T09:30:00Z",
    "confirmedByName": "Nguyễn Văn A",
    "confirmedAt": "2026-02-27T10:30:00Z"
  }
}
```

### Edit DRAFT Import

Chỉ DRAFT mới được edit trực tiếp (chưa có side effects).

```yaml
PUT /api/imports/{id}
Authorization: Bearer {token}

Request:
{
  "supplier": "Công ty Xi Măng Hà Tiên (updated)",
  "note": "Sửa lại số lượng",
  "receivedAt": "2026-02-28T10:00:00Z",
  "items": [
    { "productId": 1, "quantity": 120, "costPrice": 95000, "baseUnit": "bao" },
    { "productId": 2, "quantity": 250, "costPrice": 12000, "baseUnit": "kg" }
  ]
}
```

**Rules**:
- Chỉ edit khi Status = DRAFT
- Chỉ Owner
- Replace toàn bộ items (delete old + insert new)
- Cho phép thay đổi `hasInvoice` (chuyển từ có ↔ không hóa đơn)

### Export Phiếu (Không hóa đơn)

```yaml
GET /api/imports/{id}/export
Authorization: Bearer {token}

# Response: File download (Excel/PDF)
# Chỉ export được khi:
# - HasInvoice = false
# - SchemaVersionId != null
# - SchemaDataJson != null hoặc auto-fill từ import data

Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
Content-Disposition: attachment; filename="phieu-mua-hang-PNK-20260227-001.xlsx"
```

---

## 8. Stock & Cost Price Rules

### Stock Update (Cộng kho)

**Nguyên tắc**: Stock chỉ cộng khi import CONFIRMED, chỉ khi `TrackInventory = true`.

```csharp
public async Task ConfirmImportAsync(long importId, Guid userId)
{
    var import = await _unitOfWork.Imports
        .GetByIdWithItemsAsync(importId);
    
    if (import.Status != "DRAFT")
        throw new ValidationException("Only draft imports can be confirmed");
    
    // Group items by ProductId (có thể trùng product với giá khác)
    var groupedItems = import.ProductImports
        .GroupBy(pi => pi.ProductId)
        .ToList();
    
    foreach (var group in groupedItems)
    {
        var product = await _unitOfWork.Products.GetByIdAsync(group.Key);
        
        if (product.TrackInventory != true)
            continue;   // Không track kho → skip
        
        var totalQtyAdded = group.Sum(pi => pi.Quantity);
        var totalCostAdded = group.Sum(pi => pi.TotalPrice);
        
        
    }
    
    // Update import status
    import.Status = "CONFIRMED";
    import.ConfirmedAt = DateTime.UtcNow;
    import.ConfirmedByUserId = userId;
    
    await _unitOfWork.SaveChangesAsync();
}
```

### Stock Rollback (Cancel CONFIRMED)

```csharp
public async Task CancelConfirmedImportAsync(long importId, string reason, Guid userId)
{
    var import = await _unitOfWork.Imports
        .GetByIdWithItemsAsync(importId);
    
    if (import.Status != "CONFIRMED")
        throw new ValidationException("Only confirmed imports can be cancelled");
    
    var warnings = new List<string>();
    
    var groupedItems = import.ProductImports
        .GroupBy(pi => pi.ProductId)
        .ToList();
    
    foreach (var group in groupedItems)
    {
        var product = await _unitOfWork.Products.GetByIdAsync(group.Key);
        
        if (product.TrackInventory != true)
            continue;
        
        var totalQtyRemoved = group.Sum(pi => pi.Quantity);
        var totalCostRemoved = group.Sum(pi => pi.TotalPrice);
        
        // --- Reverse Weighted Average ---
        var currentTotalValue = product.Stock * product.CostPrice;
        var newStock = product.Stock - totalQtyRemoved;
        
        if (newStock > 0)
        {
            product.CostPrice = Math.Round(
                (currentTotalValue - totalCostRemoved) / newStock, 2);
        }
        // Nếu newStock <= 0, giữ CostPrice hiện tại (không chia cho 0)
        
        product.Stock = newStock;
        
        // Warning nếu stock âm
        if (newStock < 0)
        {
            warnings.Add(
                $"Stock âm sau rollback: {product.ProductName} = {newStock}. " +
                "Có thể đã bán một phần hàng nhập.");
        }
    }
    
    import.Status = "CANCELLED";
    import.CancelledAt = DateTime.UtcNow;
    import.CancelledByUserId = userId;
    import.CancelReason = reason;
    
    await _unitOfWork.SaveChangesAsync();
}
```

### Tổng kết Side Effects theo Status

| Action | Stock | CostPrice | Rollback khi Cancel? |
|--------|:-----:|:---------:|:--------------------:|
| Tạo import (DRAFT) | ❌ | ❌ | Hot delete |
| Edit DRAFT | ❌ | ❌ | Hot delete |
| Confirm import | ✅ Cộng | ✅ Weighted avg | - |
| Delete DRAFT | ❌ | ❌ | Hard delete, xóa record |
| Cancel CONFIRMED | ✅ Trừ | ✅ Reverse avg | ✅ |

### CostPrice = 0 (Chưa xác định giá vốn)

Khi user tạo phiếu nhập mà không nhập giá vốn (CostPrice = 0):

```csharp
// Khi Confirm: CostPrice = 0 → KHÔNG ảnh hưởng weighted average
foreach (var group in groupedItems)
{
    var product = await _unitOfWork.Products.GetByIdAsync(group.Key);
    if (product.TrackInventory != true) continue;
    
    var totalQtyAdded = group.Sum(pi => pi.Quantity);
    var totalCostAdded = group.Sum(pi => pi.TotalPrice); // = 0 khi CostPrice = 0
    
    // Chỉ update CostPrice khi import có giá vốn > 0
    if (totalCostAdded > 0)
    {
        var oldTotalValue = product.Stock * product.CostPrice;
        var newStock = product.Stock + totalQtyAdded;
        product.CostPrice = newStock > 0
            ? Math.Round((oldTotalValue + totalCostAdded) / newStock, 2)
            : group.Average(pi => pi.CostPrice);
    }
    
    // Stock vẫn cộng bình thường
    product.Stock += totalQtyAdded;
}
```

**Report / Dashboard hiển thị**:
- Phiếu nhập có CostPrice = 0 → flag ⚠️ "Chi phí chưa xác định"
- Dashboard tổng hợp → "Có X phiếu nhập chưa cập nhật giá vốn (tổng Y sản phẩm)"
- User click vào → list các phiếu cần bổ sung → Edit (nếu DRAFT) hoặc xem chi tiết

### Stock Adjustment (INVENTORY_ADJUSTMENT)

Khi user muốn điều chỉnh tồn kho **thủ công** (không qua nhập/bán hàng):

**Use cases**:
- Hàng hư, hỏng, hết hạn → **trừ stock**
- Kiểm kê phát hiện thừa → **cộng stock**
- Sai số lượng ban đầu → **điều chỉnh**

**Flow**: Sử dụng Import với `ImportType = INVENTORY_ADJUSTMENT`

```yaml
POST /api/imports?autoConfirm=true
{
  "businessLocationId": 1,
  "importType": "INVENTORY_ADJUSTMENT",
  "note": "Kiểm kê cuối tháng 2 - Xi măng hư 5 bao",
  "items": [
    {
      "productId": 1,
      "quantity": -5,          # ← Âm = giảm stock
      "costPrice": 0,          # Không ảnh hưởng giá vốn
      "baseUnit": "bao"
    },
    {
      "productId": 2,
      "quantity": 10,           # ← Dương = tăng stock
      "costPrice": 0,
      "baseUnit": "kg"
    }
  ]
}
```

**Business Rules cho INVENTORY_ADJUSTMENT**:

```csharp
// RULE-ADJ-01: Quantity cho phép âm (giảm stock)
if (request.ImportType == ImportTypes.InventoryAdjustment)
{
    // Quantity != 0 (phải có thay đổi)
    if (item.Quantity == 0)
        throw new ValidationException("Adjustment quantity cannot be zero");
    
    // CostPrice mặc định = 0 (không ảnh hưởng giá vốn)
    // TotalPrice = 0
}
else
{
    // INVOICE / RETURN: Quantity phải dương
    if (item.Quantity <= 0)
        throw new ValidationException("Quantity must be positive");
}

// RULE-ADJ-02: Stock adjustment KHÔNG thay đổi CostPrice
// Chỉ thay đổi Product.Stock
// Lý do: Điều chỉnh kho là thay đổi số lượng, không phải giá trị mua vào
```

**Khi Confirm INVENTORY_ADJUSTMENT**:

```csharp
if (import.ImportType == ImportTypes.InventoryAdjustment)
{
    // Chỉ update Stock, KHÔNG update CostPrice
    product.Stock += item.Quantity;  // Quantity có thể âm
    
    // Warning nếu stock âm sau điều chỉnh
    if (product.Stock < 0)
        warnings.Add($"Stock âm: {product.ProductName} = {product.Stock}");
}
```

### Cross-reference: Order Cancel → Optional Stock Return

> **Liên kết với order-flow.md**: Khi Owner cancel order đã Complete, user có thể **chọn**
> có hoàn trả stock lại kho hay không.
>
> ```yaml
> POST /api/orders/{id}/cancel
> {
>   "cancelReason": "Khách đổi ý",
>   "returnStock": true    # ← true = hoàn stock, false = không hoàn
> }
> ```
>
> - `returnStock = true` → Product.Stock += SaleItem.Quantity (hoàn lại kho)
> - `returnStock = false` → Giữ nguyên stock (hàng đã giao, không thu hồi)
> - Chi tiết implementation → xem [order-flow.md](./order-flow.md) Section Cancel

---

## 9. Accounting Integration (TT152)

### Diễn giải kế toán (Suggested Note)

Khi nhập hàng, hệ thống gợi ý diễn giải cho sổ kế toán:

```
┌─────────────────────────────────────────────────────────┐
│  Diễn giải (gợi ý):                                     │
│  ┌───────────────────────────────────────────────────┐  │
│  │ Nhập hàng từ Công ty Xi Măng Hà Tiên:             │  │
│  │ Xi măng Hà Tiên x150 bao, Cát xây dựng x200 kg   │  │
│  └───────────────────────────────────────────────────┘  │
│  [Dùng gợi ý]  [Sửa lại]                               │
└─────────────────────────────────────────────────────────┘
```

### Liên kết với sổ sách

| Trường hợp | Sổ kế toán | Bút toán |
|------------|-----------|---------|
| Nhập hàng có hóa đơn | S2b (Sổ chi tiết mua hàng) | Nợ: Hàng hóa / Có: Tiền mặt hoặc Phải trả |
| Nhập hàng không hóa đơn | S2b + Phiếu mua hàng | Nợ: Hàng hóa / Có: Tiền mặt (kèm phiếu) |
| Điều chỉnh tồn kho | S2c (Sổ chi tiết hàng hóa) | Điều chỉnh giá trị kho |

### UI: Chọn có/không hóa đơn

```markdown
┌─────────────────────────────────────────────────────────┐
│              NHẬP HÀNG                                  │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Loại chứng từ:                                         │
│  ┌─────────────────────────────────────────────────┐    │
│  │ ● Có hóa đơn                                    │    │
│  │   Nhập từ NCC có xuất hóa đơn                   │    │
│  │   → Upload ảnh hóa đơn (không bắt buộc)         │    │
│  └─────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────┐    │
│  │ ○ Không có hóa đơn                              │    │
│  │   Mua ở chợ, mua lẻ không có hóa đơn            │    │
│  │   → Lập phiếu mua hàng (không bắt buộc)         │    │
│  └─────────────────────────────────────────────────┘    │
│                                                         │
│  Nhà cung cấp: [_________________________]              │
│  Ngày nhận hàng: [27/02/2026    ]                       │
│                                                         │
│  ─── Sản phẩm nhập ────────────────────────             │
│                                                         │
│  [+ Thêm sản phẩm]                                      │
│  ┌───────────────────────────────────────────────┐      │
│  │ Xi măng Hà Tiên                               │      │
│  │ SL: [100] bao  ×  Giá: [95,000]đ = 9,500,000đ │      │
│  └───────────────────────────────────────────────┘      │
│  ┌───────────────────────────────────────────────┐      │
│  │ Xi măng Hà Tiên (lô 2)                        │      │
│  │ SL: [50] bao  ×  Giá: [90,000]đ = 4,500,000đ  │      │
│  └───────────────────────────────────────────────┘      │
│                                                         │
│  ─── Tổng: 14,000,000đ ────────────────────────         │
│                                                         │
│  Diễn giải: [Nhập hàng từ Công ty Xi Măng...   ]        │
│             (gợi ý bởi hệ thống)                        │
│                                                         │
│  [ Upload ảnh hóa đơn   ]                               │
│                                                         │
│   [ Hủy ]                             [ Nhập kho   ]    │
│   (hot delete nháp nếu đã lưu)       (auto confirm)     │
└─────────────────────────────────────────────────────────┘
```

Có auto-confirm không thì tùy FE quyết định, BE vẫn xử lí bình thường theo quy tắc đã định: draft + confirm (xem Section 4).

### UI: Phiếu mua hàng không hóa đơn (khi chọn "Không có hóa đơn")

```markdown
┌─────────────────────────────────────────────────────────┐
│  PHIẾU MUA HÀNG HÓA KHÔNG CÓ HÓA ĐƠN                    │
│  (Theo Thông tư 152/2025/TT-BTC)                        │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Hộ kinh doanh: [Tự động fill] ← từ Location            │
│  Địa chỉ: [Tự động fill]                                │
│  MST: [Tự động fill]                                    │
│                                                         │
│  Ngày mua hàng: [27/02/2026] ← từ ReceivedAt            │
│                                                         │
│  ─── Thông tin người bán ──────────────────────         │
│  Họ tên: [Tự động fill] ← từ Supplier                   │
│  Địa chỉ: [________________]  ← User nhập               │
│  CCCD: [________________]     ← User nhập               │
│                                                         │
│  ─── Chi tiết hàng hóa ──────────────────────           │
│  ┌────┬──────────────┬─────┬───────┬────────┬─────────┐ │
│  │STT │ Tên hàng hóa │ ĐVT │  SL   │ Đơn giá│Thành tiền │
│  ├────┼──────────────┼─────┼───────┼────────┼─────────┤ │
│  │ 1  │ Xi măng HT   │ bao │  100  │ 95,000 │9,500,000│ │
│  │ 2  │ Xi măng HT   │ bao │   50  │ 90,000 │4,500,000│ │
│  └────┴──────────────┴─────┴───────┴────────┴─────────┘ │
│  Tổng: Mười bốn triệu đồng        ← Auto-generate       │
│                                                         │
│  Người mua: ____________  Người bán: ____________       │
│  (ký, ghi rõ họ tên)     (ký, ghi rõ họ tên)            │
│                                                         │
│  [ Bỏ qua ]                  [ In phiếu  ]              │
└─────────────────────────────────────────────────────────┘
```

---

## 10. API Endpoints Summary

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/imports` | Tạo phiếu nhập (DRAFT). Query: `?autoConfirm=true` | Owner |
| `GET` | `/api/imports` | List imports (filter, pagination) | Owner, Employee (read-only) |
| `GET` | `/api/imports/{id}` | Import detail | Owner, Employee |
| `PUT` | `/api/imports/{id}` | Edit DRAFT import | Owner |
| `DELETE` | `/api/imports/{id}` | Hot delete DRAFT import (hard delete) | Owner |
| `POST` | `/api/imports/{id}/confirm` | Confirm → cộng kho + giá vốn | Owner |
| `POST` | `/api/imports/{id}/cancel` | Cancel CONFIRMED (rollback kho + giá vốn) | Owner |
| `GET` | `/api/imports/{id}/export` | Export phiếu mua hàng không hóa đơn | Owner |
| `GET` | `/api/import-schemas` | List template schemas | Owner, Admin, Consultant |
| `GET` | `/api/import-schemas/{id}` | Schema detail + active version | Owner, Admin, Consultant |
| `POST` | `/api/import-schemas/{id}/versions` | Create new version | Admin, Consultant |
| `PUT` | `/api/import-schemas/versions/{versionId}/activate` | Activate version | Admin, Consultant |

---

## 11. Error Codes

| Code | HTTP | Message |
|------|------|---------|
| `IMPORT_NOT_FOUND` | 404 | Phiếu nhập không tồn tại |
| `IMPORT_NOT_DRAFT` | 400 | Phiếu nhập không ở trạng thái DRAFT (không thể edit/delete) |
| `IMPORT_NOT_CONFIRMED` | 400 | Phiếu nhập phải ở trạng thái CONFIRMED để cancel rollback |
| `IMPORT_ALREADY_CANCELLED` | 400 | Phiếu nhập đã bị hủy |
| `PRODUCT_NOT_IN_LOCATION` | 400 | Sản phẩm không thuộc location này |
| `PRODUCT_NOT_FOUND` | 404 | Sản phẩm không tồn tại |
| `QUANTITY_INVALID` | 400 | Số lượng phải > 0 (INVOICE/RETURN) hoặc ≠ 0 (INVENTORY_ADJUSTMENT) |
| `COST_PRICE_NEGATIVE` | 400 | Giá vốn không được âm |
| `COST_PRICE_ZERO_WARNING` | 200 | Giá vốn = 0, chi phí chưa xác định (warning, không block) |
| `SCHEMA_NOT_FOUND` | 404 | Template schema không tồn tại |
| `SCHEMA_VERSION_NOT_ACTIVE` | 400 | Không có version active cho schema |
| `STOCK_NEGATIVE_WARNING` | 200 | Stock âm sau cancel rollback hoặc điều chỉnh |
| `NO_PERMISSION` | 403 | Không có quyền thực hiện action này |
| `CANCEL_REASON_REQUIRED` | 400 | Phải nhập lý do hủy (cancel CONFIRMED) |
| `ADJUSTMENT_QUANTITY_ZERO` | 400 | Số lượng điều chỉnh không được bằng 0 |
