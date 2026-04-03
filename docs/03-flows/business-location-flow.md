# Business Location Flow Documentation

> **Mục đích**: Document chi tiết các flow liên quan đến quản lý địa điểm kinh doanh (Business Location) trong BizFlow Platform.

---

## Mục lục

1. [Tổng quan Business Location](#1-tổng-quan-business-location)
2. [Entity Design](#2-entity-design)
3. [Create Location Flow](#3-create-location-flow)
4. [View Location Flow](#4-view-location-flow)
5. [Update Location Flow](#5-update-location-flow)
6. [Delete Location Flow](#6-delete-location-flow)
7. [Status Management (IsActive)](#7-status-management-isactive)
8. [Employee Assignment](#8-employee-assignment)
9. [Multi-tenancy & Authorization Rules](#9-multi-tenancy--authorization-rules)
10. [API Endpoints Summary](#10-api-endpoints-summary)
11. [Error Codes](#11-error-codes)
12. [Business Rules Summary](#12-business-rules-summary)

---

## 1. Tổng quan Business Location

### Context - Nghiệp vụ quản lý địa điểm kinh doanh HKD

Đối với hộ kinh doanh Việt Nam:

- Mỗi HKD có thể có **nhiều địa điểm kinh doanh** (cửa hàng, kho, chi nhánh)
- Mỗi địa điểm có data riêng biệt: sản phẩm, đơn hàng, tồn kho, công nợ → **multi-tenant by location**
- Owner (chủ hộ KD) tạo và sở hữu location, có toàn quyền quản lý
- Employee (nhân viên) được Owner mời và assign vào location để thao tác

### Core Concepts

```markdown
Business Location (Địa điểm kinh doanh)
├── Thông tin: Tên, Địa chỉ, Quận/Huyện, Tỉnh/TP, SĐT, Mã số thuế
├── Status: IsActive (đang hoạt động hay tạm ngưng)
├── Soft Delete: DeletedAt (xóa mềm)
│
├── Owner (Chủ sở hữu)
│   └── UserLocationAssignment (IsOwner = true)
│
├── Employees (Nhân viên)
│   └── UserLocationAssignment (IsOwner = false)
│
├── Products (Sản phẩm thuộc location)
├── Orders (Đơn hàng thuộc location)
├── Imports (Phiếu nhập hàng thuộc location)
└── RegularCustomers (Khách hàng thân thiết thuộc location)
```

### Quan hệ Location - BusinessType

> **Quyết định thiết kế**: `BusinessTypeId` được gắn ở **level Product**, không phải Location.

Lý do:

- Một location có thể kinh doanh **nhiều loại hình** cùng lúc (vừa bán hàng hóa, vừa dịch vụ)
- Khi query revenue/report → phân loại theo `Product.BusinessTypeId` để tính thuế chính xác theo TT152
- Nếu gắn ở Location level → không phân loại được khi 1 location kinh doanh đa ngành

```markdown
Location: "Cửa hàng VLXD Minh Phát"
├── Product A (Xi măng)     → BusinessType: Bán lẻ hàng hóa
├── Product B (Cắt sắt)     → BusinessType: Dịch vụ
└── Product C (Vận chuyển)   → BusinessType: Vận tải
```

### Phân biệt IsActive vs DeletedAt

| Mechanism | Mục đích | Khôi phục? | Ảnh hưởng |
|-----------|---------|:----------:|-----------|
| `IsActive = false` | **Tạm ngưng** hoạt động | ✅ Bật lại được | Employee không thao tác được, Owner vẫn thao tác bình thường |
| `DeletedAt != null` | **Xóa mềm** (không dùng nữa) | ❌ Không hiện ra | Không hiện trong danh sách, data vẫn giữ cho audit |

---

## 2. Entity Design

### Database Schema

```sql
-- =============================================
-- BUSINESS LOCATIONS TABLE
-- =============================================
CREATE TABLE IF NOT EXISTS BusinessLocations (
    BusinessLocationId INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    Name VARCHAR(255) NOT NULL COMMENT 'Tên cửa hàng/kho',
    Address TEXT NOT NULL,
    District VARCHAR(100) DEFAULT NULL,
    City VARCHAR(100) DEFAULT NULL,
    Phone VARCHAR(20) DEFAULT NULL,
    IsActive BOOLEAN NOT NULL DEFAULT TRUE,
    DeletedAt DATETIME DEFAULT NULL COMMENT 'Soft delete timestamp',
    TaxCode VARCHAR(50) DEFAULT NULL COMMENT 'Mã số thuế',

    INDEX idx_business_location_name (Name),
    INDEX idx_business_location_city (City),
    INDEX idx_business_location_is_active (IsActive)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =============================================
-- USER LOCATION ASSIGNMENTS TABLE (Phân quyền user - location)
-- =============================================
CREATE TABLE IF NOT EXISTS UserLocationAssignments (
    UserLocationAssignmentId INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    UserId CHAR(36) NOT NULL COMMENT 'User được assign',
    BusinessLocationId INT NOT NULL COMMENT 'Location được assign',
    IsOwner BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Có phải chủ sở hữu?',
    IsActive BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT fk_user_location_assignment_location 
        FOREIGN KEY (BusinessLocationId) REFERENCES BusinessLocations(BusinessLocationId)
        ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE INDEX idx_user_location_unique (UserId, BusinessLocationId),
    INDEX idx_user_location_assignment_user (UserId),
    INDEX idx_user_location_assignment_location (BusinessLocationId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### Entity Classes

```csharp
public partial class BusinessLocation
{
    public int BusinessLocationId { get; set; }
    public string Name { get; set; } = null!;
    public string Address { get; set; } = null!;
    public string? District { get; set; }
    public string? City { get; set; }
    public string? Phone { get; set; }
    public bool? IsActive { get; set; }
    public DateTime? DeletedAt { get; set; }
    public string? TaxCode { get; set; }

    // Navigation properties
    public virtual ICollection<Import> Imports { get; set; }
    public virtual ICollection<Product> Products { get; set; }
    public virtual ICollection<UserLocationAssignment> UserLocationAssignments { get; set; }
}

public partial class UserLocationAssignment
{
    public int UserLocationAssignmentId { get; set; }
    public Guid UserId { get; set; }
    public int BusinessLocationId { get; set; }
    public bool IsOwner { get; set; }
    public bool? IsActive { get; set; }

    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
    public virtual User User { get; set; } = null!;
}
```

### Field Specifications

| Field | Type | Required | Default | Mô tả |
|-------|------|:--------:|---------|-------|
| `BusinessLocationId` | INT | Auto | Auto-increment | PK |
| `Name` | VARCHAR(255) | ✅ | — | Tên cửa hàng/kho |
| `Address` | TEXT | ✅ | — | Địa chỉ |
| `District` | VARCHAR(100) | ❌ | NULL | Quận/Huyện |
| `City` | VARCHAR(100) | ❌ | NULL | Tỉnh/Thành phố |
| `Phone` | VARCHAR(20) | ❌ | NULL | Số điện thoại |
| `IsActive` | BOOLEAN | ✅ | `true` | Trạng thái hoạt động |
| `DeletedAt` | DATETIME | ❌ | NULL | Soft delete timestamp |
| `TaxCode` | VARCHAR(50) | ❌ | NULL | Mã số thuế kinh doanh |

---

## 3. Create Location Flow

### Flow Diagram

```markdown
User (Role = User) tạo Location
        │
        ▼
┌───────────────────────────┐
│ Input:                    │
│ - Name (required)         │
│ - Address (required)      │
│ - District (optional)     │
│ - City (optional)         │
│ - Phone (optional)        │
│ - TaxCode (optional)      │
│ - EmployeeIds (optional)  │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Validate: Tên location    │◄─── RULE-LOC-01
│ chưa tồn tại cho owner    │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Create BusinessLocation   │
│ IsActive = true           │
│ DeletedAt = null          │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Create UserLocationAssign │◄─── RULE-LOC-02
│ UserId = currentUser      │
│ IsOwner = true            │
│ IsActive = true           │
└─────────────┬─────────────┘
              │
              ▼
      EmployeeIds provided?
        │           │
       Yes          No
        │           │
        ▼           │
┌──────────────┐    │
│ Validate     │    │
│ employees    │◄─── RULE-LOC-03
│ (Hire check) │    │
└──────┬───────┘    │
       │            │
       ▼            │
┌──────────────┐    │
│ Assign       │    │
│ employees    │    │
│ to location  │    │
└──────┬───────┘    │
       │            │
       ▼            ▼
    ✅ Return BusinessLocationDto
```

### Request DTO

```csharp
public class CreateLocationRequest
{
    [Required]
    [StringLength(255, MinimumLength = 1)]
    public string Name { get; set; } = null!;

    [Required]
    public string Address { get; set; } = null!;

    [StringLength(100)]
    public string? District { get; set; }

    [StringLength(100)]
    public string? City { get; set; }

    [StringLength(20)]
    public string? Phone { get; set; }

    [StringLength(50)]
    public string? TaxCode { get; set; }

    /// <summary>
    /// Optional: List hired employee IDs to assign.
    /// Employees must exist in Hire table.
    /// </summary>
    public List<Guid>? EmployeeIds { get; set; }
}
```

### Business Logic

```csharp
public async Task<BusinessLocationDto> CreateLocationAsync(Guid userId, CreateLocationRequest request)
{
    return await _unitOfWork.ExecuteResilientAsync(async _ =>
    {
        // RULE-LOC-01: Unique name per owner
        var isExisted = await _unitOfWork.BusinessLocations.IsExistedByNameAsync(userId, request.Name);
        if (isExisted)
            throw new ConflictException(MessageKeys.LocationAlreadyExists);

        // Create location entity
        var location = _mapper.Map<BusinessLocation>(request);
        var createdLocation = await _unitOfWork.BusinessLocations.AddAsync(location);
        await _unitOfWork.SaveChangesAsync();

        // RULE-LOC-02: Auto-assign creator as owner
        var ownerAssignment = new UserLocationAssignment
        {
            UserId = userId,
            BusinessLocationId = createdLocation.BusinessLocationId,
            IsOwner = true,
            IsActive = true
        };
        await _unitOfWork.BusinessLocations.AddUserLocationAssignmentAsync(ownerAssignment);

        // RULE-LOC-03: Optional employee assignment
        if (request.EmployeeIds != null && request.EmployeeIds.Any())
        {
            await AssignEmployeesToLocationAsync(userId, createdLocation.BusinessLocationId, request.EmployeeIds);
        }

        await _unitOfWork.SaveChangesAsync();
        return _mapper.Map<BusinessLocationDto>(createdLocation);
    });
}
```

---

## 4. View Location Flow

### 4.1 Xem danh sách Owned Locations

> Owner xem tất cả location mình sở hữu.

```
GET /api/location/me/owned
        │
        ▼
┌───────────────────────────┐
│ Query: UserLocationAssign │
│ WHERE UserId = currentUser│
│   AND IsOwner = true      │
│ JOIN BusinessLocations    │
│ WHERE DeletedAt IS NULL   │◄─── RULE-LOC-04
└─────────────┬─────────────┘
              │
              ▼
    Return List<BusinessLocationDto>
    (kèm OwnerName cho mỗi location)
```

### 4.2 Xem danh sách Work Locations

> Employee xem tất cả location mình được assign.

```markdown
GET /api/location/work-at-locations
        │
        ▼
┌───────────────────────────┐
│ Query: UserLocationAssign │
│ WHERE UserId = currentUser│
│   AND IsOwner = false     │
│ JOIN BusinessLocations    │
│ WHERE DeletedAt IS NULL   │◄─── RULE-LOC-04
└─────────────┬─────────────┘
              │
              ▼
    Return List<BusinessLocationDto>
    (kèm OwnerName cho mỗi location)
```

### 4.3 Xem chi tiết Location (TODO)

> Xem thông tin chi tiết 1 location cụ thể.

```markdown
GET /api/location/{id}
        │
        ▼
┌───────────────────────────┐
│ Validate access:          │◄─── RULE-LOC-05
│ Owner OR assigned Employee│
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Get location detail       │
│ WHERE DeletedAt IS NULL   │
└─────────────┬─────────────┘
              │
              ▼
    Return BusinessLocationDetailDto
    (kèm: OwnerName, employee count,
     product count, etc.)
```

### Response DTO

```csharp
public class BusinessLocationDto
{
    public int Id { get; set; }
    public string Name { get; set; } = null!;
    public string Address { get; set; } = null!;
    public string? District { get; set; }
    public string? City { get; set; }
    public string? Phone { get; set; }
    public bool IsActive { get; set; }
    public string? OwnerName { get; set; }
}
```

---

## 5. Update Location Flow

### 5.1 Update Location Info

> Chỉ Owner mới được cập nhật thông tin location.

```markdown
Owner gửi request update
        │
        ▼
┌───────────────────────────┐
│ Validate:                 │
│ 1. Location tồn tại?      │◄─── 404 nếu không
│ 2. User là Owner?         │◄─── 403 nếu không
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Nếu đổi Name:             │◄─── RULE-LOC-01
│ Check unique per owner    │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Update fields:            │
│ Name, Address, District,  │
│ City, Phone, TaxCode      │
└─────────────┬─────────────┘
              │
              ▼
        ✅ Updated
```

### Request DTO

```csharp
public class UpdateLocationRequest
{
    [Required]
    [StringLength(255, MinimumLength = 1)]
    public string Name { get; set; } = null!;

    [Required]
    public string Address { get; set; } = null!;

    [StringLength(100)]
    public string? District { get; set; }

    [StringLength(100)]
    public string? City { get; set; }

    [StringLength(10)]
    public string? Phone { get; set; }

    [StringLength(50)]
    public string? TaxCode { get; set; }
}
```

### 5.2 Update Location Status

> Toggle `IsActive` flag. Xem chi tiết ảnh hưởng ở [Section 7](#7-status-management-isactive).

```markdown
PUT /api/location/me/owned/{id}/status
Body: { "isActive": false }
        │
        ▼
┌───────────────────────────┐
│ Validate ownership        │◄─── 403 nếu không phải Owner
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Update IsActive flag      │
└─────────────┬─────────────┘
              │
              ▼
        ✅ Updated
```

---

## 6. Delete Location Flow

### Flow Diagram

```markdown
Owner xóa location
        │
        ▼
┌───────────────────────────┐
│ Validate:                 │
│ 1. Location tồn tại?      │◄─── 404 nếu không
│ 2. User là Owner?         │◄─── 403 nếu không
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Check ràng buộc:          │◄─── RULE-LOC-06
│ Location có Orders nào    │
│ đang tồn tại không?       │
└─────────┬─────────────────┘
          │
    ┌─────┴──────┐
    │            │
  Có Orders   Không có
    │            │
    ▼            │
┌──────────┐     │
│ Trả về   │     │
│ WARNING  │     │
│ + yêu cầu│     │
│ confirm  │     │
└────┬─────┘     │
     │           │
     ▼           │
 User confirm?   │
   │     │       │
  Yes    No      │
   │     │       │
   │   Cancel    │
   │             │
   ▼             ▼
┌───────────────────────────┐
│ Soft Delete:              │
│ DeletedAt = DateTime.Now  │
└─────────────┬─────────────┘
              │
              ▼
        ✅ Deleted (soft)
```

### Business Logic

```csharp
public async Task<DeleteLocationResult> DeleteLocationAsync(Guid userId, int locationId)
{
    var location = await ValidateOwnershipAndGetLocationAsync(userId, locationId);
    if (location == null)
        return new DeleteLocationResult { Success = false };

    // RULE-LOC-06: Check existing orders
    var hasOrders = await _unitOfWork.Orders.HasOrdersByLocationAsync(locationId);
    if (hasOrders)
    {
        return new DeleteLocationResult
        {
            Success = false,
            RequiresConfirmation = true,
            Warning = new Warning
            {
                Code = "LOCATION_HAS_ORDERS",
                Message = $"Location '{location.Name}' có đơn hàng. Bạn có chắc muốn xóa?"
            }
        };
    }

    // Soft delete
    location.DeletedAt = DateTime.UtcNow;
    _unitOfWork.BusinessLocations.Update(location);
    await _unitOfWork.SaveChangesAsync();

    return new DeleteLocationResult { Success = true };
}

// Confirm delete (user đã xác nhận)
public async Task<bool> ConfirmDeleteLocationAsync(Guid userId, int locationId)
{
    var location = await ValidateOwnershipAndGetLocationAsync(userId, locationId);
    if (location == null) return false;

    location.DeletedAt = DateTime.UtcNow;
    _unitOfWork.BusinessLocations.Update(location);
    await _unitOfWork.SaveChangesAsync();

    return true;
}
```

### Delete Strategy

| Scenario | Action | Data |
|----------|--------|------|
| Location không có orders | Soft delete ngay | Data giữ nguyên, không hiện ra |
| Location có orders | Warning + yêu cầu confirm | User phải xác nhận, sau đó soft delete |
| Location đã soft delete | Không hiện trong list | Query phải filter `DeletedAt IS NULL` |

> **Lưu ý**: Soft delete **chỉ ẩn** location khỏi danh sách. Toàn bộ data (products, orders, imports, debtors) vẫn tồn tại trong DB cho mục đích audit và kế toán.

---

## 7. Status Management (IsActive)

### Status Matrix

| IsActive | DeletedAt | Trạng thái | Owner | Employee |
|:--------:|:---------:|-----------|:-----:|:--------:|
| `true` | `null` | **Hoạt động** | ✅ Toàn quyền | ✅ Thao tác được |
| `false` | `null` | **Tạm ngưng** | ✅ Toàn quyền | ❌ Không thao tác được |
| `true/false` | `2026-03-01` | **Đã xóa** | ❌ Không hiện ra | ❌ Không hiện ra |

### Quy tắc khi IsActive = false

**Owner vẫn thao tác bình thường:**

- ✅ Xem thông tin location
- ✅ Cập nhật thông tin, bật lại IsActive
- ✅ Quản lý products, orders, imports, debtors
- ✅ Quản lý employees

**Employee bị chặn:**

- ❌ Không tạo được order mới
- ❌ Không xem được products, orders
- ❌ Mọi thao tác trả về lỗi `LOCATION_INACTIVE`

### Validation Logic

```csharp
// Middleware/Service: Check location active cho Employee
public async Task ValidateLocationAccessAsync(Guid userId, int locationId)
{
    var location = await _unitOfWork.BusinessLocations.GetByIdAsync(locationId);

    // Location đã bị xóa
    if (location == null || location.DeletedAt != null)
        throw new NotFoundException(MessageKeys.NotFound);

    var assignment = await _unitOfWork.UserLocationAssignments
        .GetByUserAndLocationAsync(userId, locationId);

    if (assignment == null)
        throw new ForbiddenException("No access to this location");

    // Nếu là Employee và location tạm ngưng → block
    if (!assignment.IsOwner && location.IsActive == false)
        throw new ForbiddenException("LOCATION_INACTIVE");
}
```

### Use Case: Tạm ngưng kinh doanh

```markdown
Ví dụ: Owner có 2 cửa hàng, muốn tạm nghỉ 1 cửa hàng dịp Tết

1. Owner set IsActive = false cho Location "Chi nhánh 2"
2. → 3 nhân viên ở Chi nhánh 2 không thao tác được
3. → Owner vẫn xem được data, báo cáo
4. Sau Tết: Owner set IsActive = true
5. → Nhân viên thao tác lại bình thường
```

---

## 8. Employee Assignment

> **Chi tiết đầy đủ**: Xem [Hire Flow Documentation](./hire-flow.md) (TODO)

### Tóm tắt flow Assignment trong context Location

#### Assign Employee vào Location

```markdown
POST /api/location/{locationId}/employees
Body: [employeeId1, employeeId2, ...]
        │
        ▼
┌───────────────────────────┐
│ Validate ownership        │◄─── Owner only
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Validate employees:       │◄─── RULE-LOC-03
│ 1. Phải có Hire record    │
│ 2. Chưa assign vào loc    │
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Create UserLocationAssign │
│ IsOwner = false           │
│ IsActive = true           │
└─────────────┬─────────────┘
              │
              ▼
        ✅ Assigned
```

#### View Employees of Location

```markdown
GET /api/location/me/owned/{locationId}/employees
        │
        ▼
┌───────────────────────────┐
│ Validate ownership        │◄─── Owner only
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Query employees:          │
│ WHERE LocationId = id     │
│   AND IsOwner = false     │
│   AND IsActive = true     │
└─────────────┬─────────────┘
              │
              ▼
    Return EmployeeSummaryListDto
    (UserId, UserName, Phone)
```

#### Remove Employee khỏi Location (TODO)

```markdown
DELETE /api/location/{locationId}/employees/{employeeId}
        │
        ▼
┌───────────────────────────┐
│ Validate ownership        │◄─── Owner only
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ Set assignment             │
│ IsActive = false           │
│ (hoặc hard delete record) │
└─────────────┬─────────────┘
              │
              ▼
        ✅ Removed
```

---

## 9. Multi-tenancy & Authorization Rules

### Data Isolation

> Mọi data trong hệ thống đều thuộc về 1 location cụ thể. Query phải **luôn luôn** filter theo `BusinessLocationId`.

```csharp
// ĐÚng: Luôn filter theo location
var products = await _context.Products
    .Where(p => p.BusinessLocationId == locationId)
    .Where(p => p.DeletedAt == null)
    .ToListAsync();

// SAI: Query không có location filter
var products = await _context.Products.ToListAsync(); // ❌ NEVER DO THIS
```

### Authorization Flow (mọi request)

```markdown
Mọi request có context Location
        │
        ▼
┌───────────────────────────┐
│ 1. Location tồn tại?      │
│    AND DeletedAt IS NULL  │──── 404 NotFound
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ 2. User có access?        │
│   (UserLocationAssignment │
│     tồn tại & IsActive)   │──── 403 Forbidden
└─────────────┬─────────────┘
              │
              ▼
┌───────────────────────────┐
│ 3. User là Owner?         │
│    (check IsOwner flag)   │
└────────┬────────┬─────────┘
         │        │
       Owner    Employee
         │        │
         ▼        ▼
┌──────────┐ ┌──────────────┐
│ Toàn     │ │ 4. Location  │
│ quyền    │ │ IsActive?    │
│          │ │ false → 403  │
└──────────┘ └──────┬───────┘
                    │
                    ▼
             ┌──────────────┐
             │ 5. Check     │
             │ permission   │
             │ per action   │
             └──────────────┘
```

### Permission Summary cho Location

| Action | Owner | Employee | Điều kiện |
|--------|:-----:|:--------:|-----------|
| Tạo location | ✅ | ❌ | — |
| Xem owned locations | ✅ | — | — |
| Xem work locations | — | ✅ | — |
| Xem chi tiết location | ✅ | ✅ | Phải có assignment |
| Cập nhật thông tin | ✅ | ❌ | — |
| Cập nhật status | ✅ | ❌ | — |
| Xóa location | ✅ | ❌ | — |
| Assign employees | ✅ | ❌ | Employee phải có Hire record |
| Xem employees | ✅ | ❌ | — |
| Remove employee | ✅ | ❌ | — |

### Repository: Soft Delete Filter

> **RULE-LOC-04**: Tất cả query trả về cho user phải filter `DeletedAt IS NULL`.

```csharp
// Repository: Phải filter soft delete
public async Task<IEnumerable<BusinessLocation>> GetOwnedByUserIdAsync(Guid userId)
{
    return await _context.UserLocationAssignments
        .Where(ula => ula.UserId == userId && ula.IsOwner)
        .Join(_context.BusinessLocations.Where(loc => loc.DeletedAt == null), // ← QUAN TRỌNG
            ula => ula.BusinessLocationId,
            loc => loc.BusinessLocationId,
            (ula, loc) => loc)
        .ToListAsync();
}
```

---

## 10. API Endpoints Summary

| Method | Endpoint | Mô tả | Permission |
|--------|----------|-------|------------|
| `POST` | `/api/location/create` | Tạo location mới | Owner (any User) |
| `GET` | `/api/location/me/owned` | Danh sách owned locations | Owner |
| `GET` | `/api/location/work-at-locations` | Danh sách work locations | Employee |
| `GET` | `/api/location/{id}` | Chi tiết location (TODO) | Owner, Employee |
| `PUT` | `/api/location/me/owned/{id}` | Cập nhật thông tin | Owner only |
| `PUT` | `/api/location/me/owned/{id}/status` | Toggle IsActive | Owner only |
| `DELETE` | `/api/location/me/owned/{id}` | Soft delete | Owner only |
| `POST` | `/api/location/{locationId}/employees` | Assign employees | Owner only |
| `GET` | `/api/location/me/owned/{locationId}/employees` | Xem employees | Owner only |
| `DELETE` | `/api/location/{locationId}/employees/{employeeId}` | Remove employee (TODO) | Owner only |

### Request/Response Summary

| Endpoint | Request DTO | Response DTO |
|----------|-------------|-------------|
| Create | `CreateLocationRequest` | `BusinessLocationDto` |
| List Owned | — | `List<BusinessLocationDto>` |
| List Work | — | `List<BusinessLocationDto>` |
| Detail | — | `BusinessLocationDetailDto` (TODO) |
| Update Info | `UpdateLocationRequest` | — |
| Update Status | `UpdateLocationStatusRequest` | — |
| Delete | — | `DeleteLocationResult` |
| Assign Employees | `List<Guid>` | — |
| View Employees | — | `EmployeeSummaryListDto` |

---

## 11. Error Codes

| Code | HTTP | Mô tả |
|------|:----:|-------|
| `FORBIDDEN` | 403 | User không phải Owner của location |
| `NOT_FOUND` | 404 | Location không tồn tại hoặc đã bị xóa |
| `LOCATION_ALREADY_EXISTS` | 409 | Tên location đã tồn tại cho owner này |
| `LOCATION_INACTIVE` | 403 | Employee thao tác trên location đang tạm ngưng |
| `LOCATION_HAS_ORDERS` | — | Warning: Location có orders, yêu cầu user confirm trước khi xóa |
| `EMPLOYEES_NOT_HIRED` | 400 | Employee chưa được Hire bởi Owner |
| `EMPLOYEES_ALREADY_ASSIGNED` | 400 | Employee đã được assign vào location này rồi |

---

## 12. Business Rules Summary

| Rule | Mô tả | Section |
|------|-------|--------|
| RULE-LOC-01 | Tên location phải unique per owner (không trùng trong các location mình sở hữu) | [Create](#3-create-location-flow), [Update](#5-update-location-flow) |
| RULE-LOC-02 | User tạo location tự động trở thành Owner (UserLocationAssignment.IsOwner = true) | [Create](#3-create-location-flow) |
| RULE-LOC-03 | Employee phải có Hire record với Owner mới được assign vào location, và chưa được assign trước đó | [Create](#3-create-location-flow), [Assignment](#8-employee-assignment) |
| RULE-LOC-04 | Tất cả query phải filter `DeletedAt IS NULL` — không trả về location đã soft delete | [View](#4-view-location-flow) |
| RULE-LOC-05 | Xem chi tiết location: User phải là Owner hoặc Employee đã assign | [View](#4-view-location-flow) |
| RULE-LOC-06 | Xóa location: check có orders không → nếu có thì cảnh báo, yêu cầu confirm, không block | [Delete](#6-delete-location-flow) |
| RULE-LOC-07 | `IsActive = false`: Employee không thao tác được, Owner vẫn hoạt động bình thường | [Status](#7-status-management-isactive) |
| RULE-LOC-08 | BusinessTypeId gắn ở level Product, không gắn ở Location (1 location có thể kinh doanh đa ngành) | [Tổng quan](#1-tổng-quan-business-location) |
| RULE-LOC-09 | Data isolation: Mọi query phải filter theo `BusinessLocationId` — multi-tenant by location | [Multi-tenancy](#9-multi-tenancy--authorization-rules) |
