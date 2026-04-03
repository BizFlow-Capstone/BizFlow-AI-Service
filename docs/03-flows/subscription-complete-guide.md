# Hướng dẫn toàn diện: Subscription, Payment & Feature Access

> Tài liệu giải thích **trọn vẹn** luồng từ xem gói → mua → thanh toán → cấp quyền → FE lấy quyền → sử dụng tính năng (ví dụ: tạo order bằng AI) → check usage/permission ở cả FE lẫn BE.

---

## Mục lục

1. [Tổng quan kiến trúc](#1-tổng-quan-kiến-trúc)
2. [Các thực thể chính và mối quan hệ](#2-các-thực-thể-chính-và-mối-quan-hệ)
3. [FLOW HOÀN CHỈNH: Từ xem gói đến sử dụng tính năng](#3-flow-hoàn-chỉnh)
4. [Chi tiết từng bước](#4-chi-tiết-từng-bước)
5. [FE: Cách lấy và biết được quyền](#5-fe-cách-lấy-và-biết-được-quyền)
6. [Logic check quyền BE (không tin FE)](#6-logic-check-quyền-be)
7. [Ví dụ thực tế: Tạo order bằng AI Voice](#7-ví-dụ-thực-tế-tạo-order-bằng-ai-voice)
8. [Owner vs Employee: Ai check gì?](#8-owner-vs-employee)
9. [Background Jobs tự động](#9-background-jobs)
10. [API Endpoints tổng hợp](#10-api-endpoints)

---

## 1. Tổng quan kiến trúc

```
┌─────────┐     ┌──────────────┐     ┌────────────┐     ┌──────────────┐
│   FE    │────▶│  BizFlow API │────▶│   MySQL    │     │  Firestore   │
│ (App)   │◀────│  (.NET 8)    │◀────│  (SQL)     │     │  (NoSQL)     │
└─────────┘     └──────┬───────┘     └────────────┘     └──────┬───────┘
                       │                                        │
                       │  Webhook                               │
                       ▼                                        │
                ┌──────────────┐                                │
                │   Stripe     │   FE đọc trực tiếp ───────────┘
                │  (Payment)   │   (usage_tracking, subscription_access)
                └──────────────┘
```

**Tại sao dùng cả SQL và Firestore?**

| Mục đích | SQL (MySQL) | Firestore |
|----------|-------------|-----------|
| Source of truth | ✅ Dữ liệu chính | ❌ Cache/Mirror |
| FE đọc realtime | ❌ Chậm, cần API call | ✅ Realtime listener |
| Usage tracking nhanh | ❌ Mỗi lần gọi API | ✅ FE tự đọc, hiển thị |
| BE check quyền | ✅ Luôn fallback về SQL | ✅ Ưu tiên đọc (nhanh) |
| Audit / Billing | ✅ Toàn bộ lịch sử | ❌ Không lưu history |

> **Nguyên tắc vàng:** Firestore là bản sao nhanh để FE đọc. SQL là nguồn sự thật. BE luôn check SQL nếu Firestore không có data.

---

## 2. Các thực thể chính và mối quan hệ

```
SubscriptionPlan (Gói đăng ký)
  ├── SubscriptionPlanPrice (Giá của gói, có thể discount)
  ├── PlanFeature (Tính năng thuộc gói + giới hạn sử dụng)
  │     └── Feature (Định nghĩa tính năng, vd: AI_ORDER)
  ├── Subscription (Đăng ký của user)
  │     ├── FeatureUsage (Đã dùng bao nhiêu lần mỗi tính năng)
  │     ├── SubscriptionAuditLog (Lịch sử thay đổi)
  │     └── Transaction (Giao dịch thanh toán)
  └── Transaction (Lịch sử giao dịch)
```

### Ví dụ dữ liệu cụ thể

```
SubscriptionPlan: "Gói Pro"
├── DurationDays: 30
├── SubscriptionPlanPrice:
│   ├── BasePrice: 500,000 VND
│   ├── DiscountedPrice: 399,000 VND (giảm giá đến 31/12)
│   └── Currency: VND
│
├── PlanFeature:
│   ├── Feature: "AI_ORDER"      → UsageLimit: 100  (tạo order bằng AI, 100 lần/tháng)
│   ├── Feature: "AI_ANALYTICS"  → UsageLimit: 50   (phân tích AI, 50 lần/tháng)
│   └── Feature: "EXPORT_PDF"    → UsageLimit: -1   (không giới hạn)
│
└── Subscription: (khi user mua)
    ├── OwnerProfileId: "abc-123"
    ├── Status: "Active"
    ├── StartDate: 2026-03-01
    ├── EndDate: 2026-03-31
    └── FeatureUsage:
        ├── AI_ORDER:     UsedCount = 23  (đã dùng 23/100)
        ├── AI_ANALYTICS: UsedCount = 10  (đã dùng 10/50)
        └── EXPORT_PDF:   UsedCount = 45  (dùng thoải mái, không giới hạn)
```

---

## 3. FLOW HOÀN CHỈNH

Đây là luồng **đầy đủ nhất**, từ lúc user mở app đến lúc dùng tính năng AI:

```
═══════════════════════════════════════════════════════════════════════
PHASE 1: XEM GÓI & MUA GÓI
═══════════════════════════════════════════════════════════════════════

  FE                          BE (API)                      Stripe
  │                            │                              │
  │  GET /api/subscription-plans│                              │
  │ ──────────────────────────▶│                              │
  │  ◀──── Danh sách gói ─────│                              │
  │  (tên, giá, tính năng)     │                              │
  │                            │                              │
  │  POST /api/subscriptions/  │                              │
  │       checkout             │                              │
  │  {subscriptionPlanId: 2}   │                              │
  │ ──────────────────────────▶│                              │
  │                            │── Tạo Transaction (Pending)  │
  │                            │── Tạo Checkout Session ─────▶│
  │                            │◀── Session URL ──────────────│
  │  ◀──── { sessionUrl } ────│                              │
  │                            │                              │

═══════════════════════════════════════════════════════════════════════
PHASE 2: THANH TOÁN
═══════════════════════════════════════════════════════════════════════

  FE                          Stripe                        BE (Webhook)
  │                            │                              │
  │  Mở sessionUrl (redirect)  │                              │
  │ ──────────────────────────▶│                              │
  │  User nhập thẻ, thanh toán │                              │
  │  ◀──── Redirect success ──│                              │
  │                            │                              │
  │                            │── checkout.session.completed ▶│
  │                            │                              │── Verify signature
  │                            │                              │── Check idempotency
  │                            │                              │── Tạo Subscription (Active)
  │                            │                              │── Tạo FeatureUsage (UsedCount=0)
  │                            │                              │── Transaction → Success
  │                            │                              │── Ghi Firestore usage_tracking
  │                            │                              │── Gửi notification (FCM)
  │                            │                              │
  │  ◀──── Push notification ─────────────────────────────────│
  │  "Gói Pro đã được kích hoạt!"                             │

═══════════════════════════════════════════════════════════════════════
PHASE 3: FE LẤY QUYỀN & HIỂN THỊ
═══════════════════════════════════════════════════════════════════════

  FE                          Firestore                     BE (API)
  │                            │                              │
  │  Lắng nghe realtime:       │                              │
  │  usage_tracking/{id}_active│                              │
  │ ──────────────────────────▶│                              │
  │  ◀──── Snapshot ──────────│                              │
  │  {                         │                              │
  │    status: "active",       │                              │
  │    planName: "Gói Pro",    │                              │
  │    features: {             │                              │
  │      AI_ORDER: {           │                              │
  │        used: 23,           │                              │
  │        limit: 100          │                              │
  │      }                     │                              │
  │    }                       │                              │
  │  }                         │                              │
  │                            │                              │
  │  HOẶC gọi API:            │                              │
  │  GET /api/subscriptions/   │                              │
  │      current               │                              │
  │ ──────────────────────────────────────────────────────────▶│
  │  ◀──── CurrentSubscriptionDto ────────────────────────────│

═══════════════════════════════════════════════════════════════════════
PHASE 4: SỬ DỤNG TÍNH NĂNG (VD: TẠO ORDER BẰNG AI)
═══════════════════════════════════════════════════════════════════════

  FE                          BE (API)                      Firestore
  │                            │                              │
  │  (1) Check local:          │                              │
  │  features.AI_ORDER.used    │                              │
  │  < features.AI_ORDER.limit │                              │
  │  → 23 < 100 → OK!         │                              │
  │                            │                              │
  │  POST /api/orders/voice    │                              │
  │  (locationId: 5)           │                              │
  │ ──────────────────────────▶│                              │
  │                            │── [RequireFeature("AI_ORDER")]│
  │                            │                              │
  │                            │── (2) User có access vào     │
  │                            │       location 5?            │
  │                            │── (3) Tìm owner của          │
  │                            │       location 5             │
  │                            │── (4) Owner có subscription  │
  │                            │       Active?                │
  │                            │── (5) Gói có feature         │
  │                            │       AI_ORDER?              │
  │                            │── (6) Check usage:           │
  │                            │       Firestore: used < limit?│
  │                            │       ──────────────────────▶ │
  │                            │       ◀── {used:23, limit:100}│
  │                            │       → 23 < 100 → OK!       │
  │                            │                              │
  │                            │── (7) Increment usage:       │
  │                            │       Firestore: used → 24   │
  │                            │       ──────────────────────▶ │
  │                            │       Hangfire job: SQL += 1  │
  │                            │                              │
  │                            │── (8) Thực hiện tạo order    │
  │  ◀──── Order created ─────│                              │
  │                            │                              │
  │  Firestore listener tự    │                              │
  │  cập nhật: used = 24      │                              │
```

---

## 4. Chi tiết từng bước

### Bước 1: Xem danh sách gói

**API:** `GET /api/subscription-plans`

FE gọi API để lấy danh sách gói hiện có. Response chứa:

```json
[
  {
    "subscriptionPlanId": 2,
    "name": "Gói Pro",
    "description": "Dành cho quán vừa & lớn",
    "durationDays": 30,
    "isActive": true,
    "currentPrice": {
      "basePrice": 500000,
      "discountedPrice": 399000,
      "effectivePrice": 399000,
      "isDiscountActive": true,
      "discountEnd": "2026-12-31T23:59:59",
      "currency": "VND"
    },
    "features": [
      { "featureCode": "AI_ORDER", "featureName": "Tạo đơn bằng AI", "usageLimit": 100 },
      { "featureCode": "AI_ANALYTICS", "featureName": "Phân tích AI", "usageLimit": 50 },
      { "featureCode": "EXPORT_PDF", "featureName": "Xuất PDF", "usageLimit": -1 }
    ]
  }
]
```

> `usageLimit = -1` nghĩa là **không giới hạn** (unlimited).

### Bước 2: Mua gói (Checkout)

**API:** `POST /api/subscriptions/checkout`

```json
{ "subscriptionPlanId": 2 }
```

**BE xử lý:**

1. Check user **chưa có** subscription Active (nếu có → 409 Conflict)
2. Tạo `Transaction` với status `Pending`
3. Gọi Stripe API tạo Checkout Session (mode: `payment`, one-time)
4. Trả về `sessionUrl` cho FE

```json
{
  "transactionId": "abc-456",
  "sessionUrl": "https://checkout.stripe.com/pay/cs_xxx",
  "planPrice": 399000,
  "prorationCredit": 0,
  "finalAmount": 399000,
  "currency": "VND",
  "transactionType": "PURCHASE"
}
```

### Bước 3: Thanh toán trên Stripe

- FE redirect user đến `sessionUrl`
- User nhập thông tin thẻ trên giao diện Stripe (BizFlow **không** lưu thông tin thẻ)
- Stripe xử lý thanh toán
- Thành công → Stripe redirect về `SuccessUrl`
- Thất bại/hủy → Stripe redirect về `CancelUrl`

### Bước 4: Webhook xử lý kết quả

Stripe gửi webhook đến `POST /api/webhooks/stripe`.

**Luồng xử lý webhook:**

```
Stripe POST /api/webhooks/stripe
  │
  ├── Verify chữ ký (signature) → Sai → 400 Bad Request
  │
  ├── Check idempotency (TryCreateReceivedAsync)
  │   → Đã xử lý rồi → Skip (200 OK)
  │
  ├── checkout.session.completed
  │   ├── Tìm Transaction theo metadata.transactionId
  │   ├── Tạo Subscription mới (Status = Active)
  │   ├── Tạo FeatureUsage cho mỗi feature (UsedCount = 0)
  │   ├── Transaction.Status → Success
  │   ├── Ghi SubscriptionAuditLog
  │   ├── Ghi Firestore usage_tracking
  │   └── Gửi push notification (FCM)
  │
  ├── checkout.session.expired
  │   └── Transaction.Status → Failed
  │
  ├── payment_intent.payment_failed
  │   └── Transaction.Status → Failed + notify user
  │
  └── charge.refunded
      └── Transaction.Status → Refunded
```

**Compensation Refund (An toàn tuyệt đối):**

Nếu webhook `checkout.session.completed` nhận tiền thành công nhưng **tạo subscription thất bại** (lỗi DB, bug,...), BE tự động refund tiền về cho user qua Stripe. User không bị mất tiền.

### Bước 5: Subscription được kích hoạt

Sau khi webhook thành công, dữ liệu trong hệ thống:

**SQL:**
```
Subscription:
  SubscriptionId: "new-sub-id"
  OwnerProfileId: "abc-123"
  SubscriptionPlanId: 2
  Status: "Active"
  StartDate: 2026-03-26T10:00:00Z
  EndDate: 2026-04-25T10:00:00Z

FeatureUsage (3 records):
  - AI_ORDER:     UsedCount = 0, PeriodStart → PeriodEnd
  - AI_ANALYTICS: UsedCount = 0
  - EXPORT_PDF:   UsedCount = 0
```

**Firestore** (collection: `usage_tracking`, doc: `{profileId}_active`):
```json
{
  "ownerProfileId": "abc-123",
  "planName": "Gói Pro",
  "subscriptionId": "new-sub-id",
  "status": "active",
  "startDate": "2026-03-26T10:00:00Z",
  "endDate": "2026-04-25T10:00:00Z",
  "features": {
    "AI_ORDER":     { "used": 0, "limit": 100 },
    "AI_ANALYTICS": { "used": 0, "limit": 50  },
    "EXPORT_PDF":   { "used": 0, "limit": -1  }
  },
  "updatedAt": "2026-03-26T10:00:00Z"
}
```

---

## 5. FE: Cách lấy và biết được quyền

FE có **2 cách** để biết user có quyền gì:

### Cách 1: Firestore Realtime (Nhanh, Recommend)

FE listen Firestore document:

```
Collection: usage_tracking
Document:   {ownerProfileId}_active
```

```typescript
// Pseudo-code FE (Flutter/React)
const docRef = firestore
  .collection("usage_tracking")
  .doc(`${ownerProfileId}_active`);

docRef.onSnapshot((snapshot) => {
  const data = snapshot.data();
  
  // Kiểm tra subscription còn active không
  if (data.status !== "active") {
    showUpgradeDialog();
    return;
  }
  
  // Kiểm tra feature cụ thể
  const aiOrder = data.features["AI_ORDER"];
  if (aiOrder.limit === -1) {
    // Unlimited - luôn cho phép
    enableFeature("AI_ORDER");
  } else if (aiOrder.used < aiOrder.limit) {
    // Còn quota
    enableFeature("AI_ORDER");
    showUsageLabel(`${aiOrder.used}/${aiOrder.limit}`);
  } else {
    // Hết quota
    disableFeature("AI_ORDER");
    showLimitReachedDialog();
  }
});
```

**Ưu điểm:** Realtime, không cần gọi API, UI cập nhật tức thì khi usage thay đổi.

### Cách 2: API Call (Chính xác, Fallback)

```
GET /api/subscriptions/current
```

Response:

```json
{
  "subscriptionId": "new-sub-id",
  "status": "Active",
  "startDate": "2026-03-26",
  "endDate": "2026-04-25",
  "plan": {
    "subscriptionPlanId": 2,
    "name": "Gói Pro",
    "features": [...]
  },
  "features": [
    {
      "featureId": 1,
      "featureCode": "AI_ORDER",
      "featureName": "Tạo đơn bằng AI",
      "usageLimit": 100,
      "usedCount": 23
    }
  ]
}
```

### Khi nào dùng cách nào?

| Tình huống | Dùng cách nào |
|-----------|--------------|
| Hiển thị badge/icon trên UI | Firestore Realtime |
| Hiển thị usage bar (23/100) | Firestore Realtime |
| Khi mới mở app | Firestore Realtime |
| Khi cần data chính xác 100% | API `/subscriptions/current` |
| FE cần debug/verify | API `/subscriptions/current` |

### Employee đọc được không?

Employee **cũng cần biết** mình có quyền dùng tính năng hay không. Owner cấp quyền cho employee đọc:

**Firestore structure (subscription_access):**

```
Collection: subscription_access
  Document: {ownerProfileId}
    Collection: members
      Document: {employeeProfileId}
        {
          "ownerProfileId": "abc-123",
          "memberProfileId": "emp-456",
          "canReadUsage": true,
          "isActive": true,
          "updatedAt": "..."
        }
```

FE employee flow:

```typescript
// 1. Employee check mình thuộc owner nào
const memberDoc = await firestore
  .collection("subscription_access")
  .doc(ownerProfileId)       // từ location info
  .collection("members")
  .doc(myProfileId)
  .get();

if (memberDoc.exists && memberDoc.data().isActive && memberDoc.data().canReadUsage) {
  // 2. Đọc usage_tracking của owner
  const usageDoc = await firestore
    .collection("usage_tracking")
    .doc(`${ownerProfileId}_active`)
    .get();
  
  // 3. Hiển thị tương tự owner
}
```

---

## 6. Logic check quyền BE (không tin FE)

> **Triết lý: FE check để hiển thị UI (UX tốt). BE check để thực thi (bảo mật).  
> FE có thể bị bypass, BE thì KHÔNG.**

### RequireFeature Attribute

Khi một API endpoint cần tính năng subscription, chỉ cần gắn attribute:

```csharp
[HttpPost("voice")]
[RequireFeature("AI_ORDER")]    // ← Chỉ cần dòng này
public async Task<IActionResult> CreateOrderFromVoice(
    [FromQuery] int locationId,
    [FromBody] VoiceOrderRequest request)
{
    // Code xử lý order...
    // Nếu đến được đây = user CÓ QUYỀN
}
```

### RequireFeatureFilter - Logic chi tiết

Khi request đến endpoint có `[RequireFeature("AI_ORDER")]`, filter thực hiện **7 bước tuần tự**:

```
Request đến [RequireFeature("AI_ORDER")]
  │
  │  Bước 1: Lấy profileId từ JWT token
  ├── profileId = User.GetRequiredUserId()
  │   (lấy từ claim "profileId" hoặc "userId", KHÔNG phải "sub")
  │
  │  Bước 2: Tìm locationId từ request
  ├── Tìm trong: route param → request body property → query string
  │   locationId = 5
  │
  │  Bước 3: User có access vào location này?
  ├── HasAccessToLocationAsync(profileId, locationId)
  │   → Kiểm tra trong DB: user là owner HOẶC employee của location
  │   → Nếu KHÔNG → return false
  │
  │  Bước 4: Tìm owner của location
  ├── IsOwnerOfLocationAsync(profileId, locationId)
  │   → Nếu user LÀ owner → ownerId = profileId
  │   → Nếu user KHÔNG phải owner (là employee)
  │     → GetOwnerIdByLocationAsync(locationId)
  │     → ownerId = owner's profileId
  │
  │  ⭐ QUAN TRỌNG: Subscription luôn gắn với OWNER, không phải employee
  │
  │  Bước 5: Owner có subscription Active?
  ├── GetActiveByOwnerAsync(ownerId)
  │   → Tìm subscription có Status = "Active" của owner
  │   → Nếu KHÔNG có → return false (403 Forbidden)
  │
  │  Bước 6: Gói subscription có feature này?
  ├── PlanFeatures.FirstOrDefault(f => f.FeatureCode == "AI_ORDER")
  │   → Nếu KHÔNG có → return false (403 Forbidden)
  │   → UsageLimit = 0 → return false (feature bị disable)
  │   → UsageLimit = -1 → UNLIMITED → skip check usage
  │   → UsageLimit > 0 → check usage (bước 7)
  │
  │  Bước 7: Check usage quota
  ├── Ưu tiên Firestore:
  │   │  GetUsageSnapshotAsync(ownerId, "AI_ORDER")
  │   │  → Firestore trả về: { used: 23, limit: 100 }
  │   │  → 23 < 100 → CÒN QUOTA → OK
  │   │
  │   │  Nếu Firestore không có data (null):
  │   └── Fallback về SQL:
  │       → FeatureUsages.Where(featureId == AI_ORDER).UsedCount
  │       → So sánh với UsageLimit
  │
  │  Bước 8: Increment usage (nếu OK)
  ├── Firestore: increment features.AI_ORDER.used += 1 (REALTIME)
  └── Hangfire: enqueue SQL update UsedCount += 1 (BACKGROUND)
  
  → Request đi tiếp vào controller → xử lý tạo order
```

### Code thực tế: CheckFeatureAccessAsync

```csharp
public async Task<bool> CheckFeatureAccessAsync(
    Guid profileId, int locationId, string featureCode, bool incrementUsage = false)
{
    // Bước 3: Check location access
    var hasAccess = await _businessLocationRepository.HasAccessToLocationAsync(profileId, locationId);
    if (!hasAccess) return false;

    // Bước 4: Resolve owner
    var ownerId = await ResolveOwnerProfileIdAsync(profileId, locationId);
    if (ownerId == null) return false;

    // Bước 5: Active subscription?
    var active = await _unitOfWork.Subscriptions.GetActiveByOwnerAsync(ownerId.Value);
    if (active == null) return false;

    // Bước 6: Feature exists in plan?
    var planFeature = active.SubscriptionPlan.PlanFeatures
        .FirstOrDefault(pf => pf.Feature.FeatureCode == featureCode);
    if (planFeature == null || planFeature.UsageLimit == 0) return false;

    // Bước 7: Check quota
    if (planFeature.UsageLimit > 0) // -1 = unlimited, skip
    {
        var snapshot = await _firestoreService.GetUsageSnapshotAsync(ownerId.Value, featureCode);
        if (snapshot != null)
        {
            if (snapshot.Used >= snapshot.Limit) return false;
        }
        else
        {
            // Fallback SQL
            var sqlUsed = active.FeatureUsages
                .Where(x => x.FeatureId == planFeature.FeatureId)
                .Select(x => x.UsedCount).FirstOrDefault();
            if (sqlUsed >= planFeature.UsageLimit) return false;
        }
    }

    // Bước 8: Increment
    if (incrementUsage)
    {
        await _firestoreService.IncrementFeatureUsageAsync(ownerId.Value, featureCode);
        BackgroundJob.Enqueue<ISubscriptionService>(s =>
            s.IncrementUsageSqlBackgroundAsync(active.SubscriptionId, featureCode));
    }

    return true;
}
```

---

## 7. Ví dụ thực tế: Tạo order bằng AI Voice

### Tình huống

- **Owner Minh** mua Gói Pro (AI_ORDER: 100 lần/tháng)
- **Employee Linh** làm việc tại quán của Minh (location 5)
- Linh muốn tạo order bằng giọng nói (AI)

### Luồng xử lý

```
 Linh (Employee)                    BizFlow BE                         Firestore
      │                                  │                                  │
      │  Mở app, vào trang tạo order     │                                  │
      │  FE check: tôi có quyền?         │                                  │
      │                                  │                                  │
      │  (1) FE đọc Firestore            │                                  │
      │      subscription_access/        │                                  │
      │      {minh-id}/members/{linh-id} │                                  │
      │ ─────────────────────────────────────────────────────────────────── ▶│
      │ ◀─── { isActive: true, canReadUsage: true } ───────────────────────│
      │                                  │                                  │
      │  (2) FE đọc usage_tracking/      │                                  │
      │      {minh-id}_active            │                                  │
      │ ─────────────────────────────────────────────────────────────────── ▶│
      │ ◀─── { AI_ORDER: { used: 23, limit: 100 } } ──────────────────────│
      │                                  │                                  │
      │  FE: 23 < 100 → hiển thị nút    │                                  │
      │  "Tạo order bằng AI" (enabled)   │                                  │
      │  Badge: "23/100 lần"             │                                  │
      │                                  │                                  │
      │  Linh bấm nút, nói:             │                                  │
      │  "2 phở bò, 1 trà đá"           │                                  │
      │                                  │                                  │
      │  POST /api/orders/voice          │                                  │
      │  { locationId: 5, audio: ... }   │                                  │
      │ ────────────────────────────────▶│                                  │
      │                                  │                                  │
      │                                  │  [RequireFeature("AI_ORDER")]    │
      │                                  │  profileId = Linh's ID           │
      │                                  │  locationId = 5                  │
      │                                  │                                  │
      │                                  │  HasAccess(Linh, location 5)?    │
      │                                  │  → YES (Linh là employee)        │
      │                                  │                                  │
      │                                  │  IsOwner(Linh, location 5)?      │
      │                                  │  → NO → GetOwner(location 5)     │
      │                                  │  → ownerId = Minh's ID           │
      │                                  │                                  │
      │                                  │  Minh có sub Active?             │
      │                                  │  → YES (Gói Pro)                 │
      │                                  │                                  │
      │                                  │  Gói Pro có AI_ORDER?            │
      │                                  │  → YES (limit: 100)             │
      │                                  │                                  │
      │                                  │  Check usage (Firestore)  ──────▶│
      │                                  │  ◀── { used: 23, limit: 100 } ──│
      │                                  │  23 < 100 → OK!                  │
      │                                  │                                  │
      │                                  │  Increment Firestore ───────────▶│
      │                                  │  (AI_ORDER.used = 24)            │
      │                                  │  Enqueue Hangfire SQL job         │
      │                                  │                                  │
      │                                  │  → Xử lý AI voice → tạo order   │
      │  ◀──── Order created ───────────│                                  │
      │                                  │                                  │
      │  Firestore listener tự update:   │                                  │
      │  Badge: "24/100 lần" ◀──────────────────────────────────────────── │
```

### Nếu hết quota thì sao?

```
  Linh                               BizFlow BE
    │                                     │
    │  FE thấy: used = 100, limit = 100   │
    │  → Disable nút "Tạo order bằng AI"  │
    │  → Hiển thị "Đã hết lượt sử dụng"   │
    │                                     │
    │  (Giả sử FE bị hack, gọi thẳng API) │
    │  POST /api/orders/voice              │
    │ ───────────────────────────────────▶ │
    │                                     │
    │                                     │── CheckFeatureAccess
    │                                     │── used(100) >= limit(100)
    │                                     │── return false
    │                                     │
    │  ◀──── 403 Forbidden ───────────── │
    │  "Bạn không có quyền thực hiện"     │
```

---

## 8. Owner vs Employee

### So sánh quyền

```
┌─────────────────────────────────────────────────────────────────┐
│                        SUBSCRIPTION                             │
│                     (thuộc về OWNER)                             │
│                                                                 │
│  Owner (Minh)              Employee (Linh, Hùng, Mai)           │
│  ┌──────────────┐          ┌─────────────────────────────┐      │
│  │ Mua gói      │          │ KHÔNG THỂ mua gói           │      │
│  │ Upgrade gói  │          │ KHÔNG THỂ upgrade            │      │
│  │ Renew gói    │          │ KHÔNG THỂ renew              │      │
│  │ Xem hóa đơn  │          │ KHÔNG THỂ xem hóa đơn       │      │
│  │ Cấp quyền    │          │ Được cấp quyền đọc          │      │
│  │ Thu hồi quyền │          │                              │      │
│  │              │          │                              │      │
│  │ SỬ DỤNG     │          │ SỬ DỤNG                     │      │
│  │ tính năng AI │          │ tính năng AI                 │      │
│  │ (trừ quota   │          │ (trừ quota CỦA OWNER)       │      │
│  │  của mình)   │          │                              │      │
│  └──────────────┘          └─────────────────────────────┘      │
│                                                                 │
│  Usage quota CHIA SẺ: Owner + tất cả Employee dùng chung 100    │
│  lần AI_ORDER. Ai dùng cũng trừ vào quota của Owner.            │
└─────────────────────────────────────────────────────────────────┘
```

### Tại sao thiết kế như vậy?

**Subscription gắn với Owner, không phải cá nhân:**
- Minh (owner) mở quán, mua Gói Pro
- Tất cả nhân viên trong quán của Minh đều được dùng tính năng
- Quota tính chung cho cả quán (không phải mỗi người 100 lần)
- Khi Minh sa thải Linh → thu hồi quyền employee → Linh không dùng được nữa

### FE xử lý ra sao? (Code thống nhất cho cả Owner lẫn Employee)

**Nguyên tắc:** FE viết **CÙNG MỘT code** cho Owner và Employee. Không cần `if (isOwner)` / `else`. Firestore Security Rules tự phân biệt quyền ở tầng dưới.

**Tại sao được?**
- Owner đọc `usage_tracking/{ownerProfileId}_active` → Rules thấy `myProfileId == ownerProfileId` → cho đọc
- Employee đọc cùng document đó → Rules tự check `subscription_access` ngầm → có grant thì cho đọc, không thì deny
- FE chỉ cần try/catch → **không cần biết** user là Owner hay Employee

#### Cấu trúc Firestore document: 1 document chứa TẤT CẢ features

```
Collection: usage_tracking
Document:   {ownerProfileId}_active

{
  "ownerProfileId": "abc-123",
  "planName": "Gói Pro",
  "status": "active",
  "startDate": "2026-03-26T10:00:00Z",
  "endDate": "2026-04-25T10:00:00Z",
  "features": {                            ← MAP chứa TẤT CẢ tính năng
    "AI_ORDER":     { "used": 23, "limit": 100 },
    "AI_ANALYTICS": { "used": 10, "limit": 50  },
    "EXPORT_PDF":   { "used": 45, "limit": -1  },
    "MULTI_BRANCH": { "used": 2,  "limit": 3   }
  },
  "updatedAt": "2026-03-26T15:30:00Z"
}
```

**1 lần đọc = biết hết toàn bộ.** FE dựa vào `features` map để enable/disable UI:

| Trường hợp | Điều kiện | UI |
|------------|-----------|-----|
| Feature không có trong map | `features["X"]` === undefined | Ẩn / Disable + "Nâng cấp gói" |
| Unlimited | `limit < 0` | Enable, không hiện badge |
| Còn quota | `used < limit` | Enable + badge "23/100" |
| Hết quota | `used >= limit` | Disable + "Đã hết lượt" |
| Subscription expired | `status !== "active"` | Disable tất cả + "Gia hạn gói" |
| Document không tồn tại | snapshot không exists | Disable tất cả + "Mua gói" |

#### Code mẫu hoàn chỉnh (TypeScript/React)

```typescript
// ====================================================================
// subscription-hook.ts — Hook dùng chung cho Owner và Employee
// ====================================================================

import {
  getFirestore, doc, onSnapshot, FirestoreError
} from "firebase/firestore";

// Kiểu dữ liệu
interface FeatureUsage {
  used: number;
  limit: number;
}

interface SubscriptionUsageData {
  status: string;
  planName: string;
  subscriptionId: string;
  startDate: any;
  endDate: any;
  features: Record<string, FeatureUsage>;
}

interface SubscriptionState {
  loading: boolean;
  hasAccess: boolean;          // user có quyền đọc data không
  isActive: boolean;           // subscription đang active không
  planName: string | null;
  features: Record<string, FeatureUsage>;
  error: string | null;
}

// ====================================================================
// BƯỚC 1: Lấy ownerProfileId từ location đang làm việc
// ====================================================================
// Khi user (Owner hoặc Employee) chọn location để làm việc,
// FE đã có sẵn ownerProfileId từ thông tin location.
//
//   Owner chọn quán của mình   → ownerProfileId = chính mình
//   Employee chọn quán làm việc → ownerProfileId = chủ quán
//
// Cả hai trường hợp đều trả về cùng 1 giá trị: ownerProfileId của location.

function getOwnerProfileIdFromCurrentLocation(): string {
  // Lấy từ context location hiện tại (đã có khi user chọn location)
  // Ví dụ: từ Redux store, Context, hoặc local storage
  return currentLocation.ownerProfileId;
}

// ====================================================================
// BƯỚC 2: Listen Firestore — Code giống nhau cho Owner & Employee
// ====================================================================

function useSubscriptionUsage(): SubscriptionState {
  const [state, setState] = useState<SubscriptionState>({
    loading: true,
    hasAccess: false,
    isActive: false,
    planName: null,
    features: {},
    error: null,
  });

  useEffect(() => {
    const ownerProfileId = getOwnerProfileIdFromCurrentLocation();
    if (!ownerProfileId) {
      setState(prev => ({ ...prev, loading: false, error: "No location selected" }));
      return;
    }

    // Document ID luôn là: {ownerProfileId}_active
    const db = getFirestore();
    const usageDocRef = doc(db, "usage_tracking", `${ownerProfileId}_active`);

    // Realtime listener — Firestore Rules tự check quyền:
    //   Owner  → Rules: myProfileId == ownerProfileId → OK
    //   Employee → Rules: check subscription_access ngầm → OK hoặc Deny
    const unsubscribe = onSnapshot(
      usageDocRef,

      // SUCCESS: User có quyền đọc (Owner hoặc Employee được cấp quyền)
      (snapshot) => {
        if (!snapshot.exists()) {
          // Document không tồn tại → Owner chưa mua gói
          setState({
            loading: false,
            hasAccess: true,
            isActive: false,
            planName: null,
            features: {},
            error: null,
          });
          return;
        }

        const data = snapshot.data() as SubscriptionUsageData;
        setState({
          loading: false,
          hasAccess: true,
          isActive: data.status === "active",
          planName: data.planName,
          features: data.features || {},
          error: null,
        });
      },

      // ERROR: Firestore Rules chặn → User không có quyền
      (error: FirestoreError) => {
        if (error.code === "permission-denied") {
          // Employee chưa được Owner cấp quyền đọc
          setState({
            loading: false,
            hasAccess: false,
            isActive: false,
            planName: null,
            features: {},
            error: "no_access_grant",
          });
        } else {
          // Lỗi khác (network, Firestore down,...)
          setState(prev => ({
            ...prev,
            loading: false,
            error: error.code,
          }));
        }
      }
    );

    return () => unsubscribe();
  }, [currentLocation]);

  return state;
}

// ====================================================================
// BƯỚC 3: Check 1 tính năng cụ thể
// ====================================================================

function canUseFeature(
  features: Record<string, FeatureUsage>,
  featureCode: string
): { allowed: boolean; used: number; limit: number; reason: string } {

  const feature = features[featureCode];

  if (!feature) {
    return { allowed: false, used: 0, limit: 0, reason: "not_in_plan" };
  }

  // limit < 0 → unlimited (không giới hạn)
  if (feature.limit < 0) {
    return { allowed: true, used: feature.used, limit: -1, reason: "unlimited" };
  }

  // Còn quota?
  if (feature.used < feature.limit) {
    return { allowed: true, used: feature.used, limit: feature.limit, reason: "ok" };
  }

  // Hết quota
  return { allowed: false, used: feature.used, limit: feature.limit, reason: "quota_exceeded" };
}

// ====================================================================
// BƯỚC 4: Check TẤT CẢ features cùng lúc → enable/disable toàn bộ UI
// ====================================================================

// Danh sách TẤT CẢ feature codes mà app hỗ trợ
const ALL_FEATURES = [
  { code: "AI_ORDER",     label: "Tạo order bằng AI",    icon: "mic"       },
  { code: "AI_ANALYTICS", label: "Phân tích AI",         icon: "analytics" },
  { code: "EXPORT_PDF",   label: "Xuất báo cáo PDF",     icon: "pdf"       },
  { code: "MULTI_BRANCH", label: "Quản lý nhiều chi nhánh", icon: "store"  },
];

// Component hiển thị TOÀN BỘ tính năng premium
function PremiumFeaturesPanel() {
  const subscription = useSubscriptionUsage();

  if (subscription.loading) return <Spinner />;

  if (!subscription.hasAccess) {
    return <Banner message="Liên hệ chủ quán để được cấp quyền sử dụng" />;
  }

  if (!subscription.isActive) {
    return <UpgradePrompt message="Mua gói để sử dụng các tính năng cao cấp" />;
  }

  // Check TẤT CẢ features 1 lần từ cùng 1 data source
  return (
    <div>
      <Text>Gói hiện tại: {subscription.planName}</Text>
      {ALL_FEATURES.map((feat) => {
        const status = canUseFeature(subscription.features, feat.code);
        return (
          <FeatureItem
            key={feat.code}
            icon={feat.icon}
            label={feat.label}
            status={status}
          />
        );
      })}
    </div>
  );
}

// Component cho từng feature item
function FeatureItem({ icon, label, status }) {
  // Feature không có trong gói → ẩn hoặc show upgrade
  if (status.reason === "not_in_plan") {
    return (
      <div className="feature-item disabled">
        <Icon name={icon} />
        <Text>{label}</Text>
        <Badge variant="gray">Nâng cấp gói</Badge>
      </div>
    );
  }

  // Unlimited
  if (status.reason === "unlimited") {
    return (
      <div className="feature-item enabled">
        <Icon name={icon} />
        <Text>{label}</Text>
        <Badge variant="green">Không giới hạn</Badge>
      </div>
    );
  }

  // Hết quota
  if (!status.allowed) {
    return (
      <div className="feature-item disabled">
        <Icon name={icon} />
        <Text>{label}</Text>
        <Badge variant="red">{status.used}/{status.limit} - Hết lượt</Badge>
      </div>
    );
  }

  // Còn quota
  return (
    <div className="feature-item enabled">
      <Icon name={icon} />
      <Text>{label}</Text>
      <Badge variant="blue">{status.used}/{status.limit} lượt</Badge>
    </div>
  );
}

// ====================================================================
// BƯỚC 5: Dùng ở bất kỳ đâu trong app — check 1 feature cụ thể
// ====================================================================

// Ví dụ: nút "Tạo order bằng AI" ở trang Order
function AIOrderButton({ locationId }: { locationId: number }) {
  const subscription = useSubscriptionUsage();
  const aiOrder = canUseFeature(subscription.features, "AI_ORDER");

  if (subscription.loading) return <Spinner />;
  if (!subscription.hasAccess) return null;  // ẩn nút
  if (!subscription.isActive) return null;   // ẩn nút
  if (!aiOrder.allowed) {
    return <Button disabled tooltip="Đã hết lượt">Tạo order bằng AI</Button>;
  }

  return (
    <Button onClick={() => createVoiceOrder(locationId)}>
      Tạo order bằng AI ({aiOrder.used}/{aiOrder.limit})
    </Button>
  );
}

// ====================================================================
// BƯỚC 5: Gọi API — BE check lại toàn bộ (không tin FE)
// ====================================================================

async function createVoiceOrder(locationId: number) {
  try {
    // locationId luôn được gửi kèm → BE dùng nó để tìm owner
    const response = await api.post("/api/orders/voice", {
      locationId: locationId,
      audio: audioBlob,
    });
    showSuccess("Order đã được tạo!");
  } catch (error) {
    if (error.status === 403) {
      // BE từ chối → có thể quota vừa hết (người khác dùng)
      // → reload Firestore data (listener tự cập nhật)
      showError("Bạn đã hết lượt sử dụng tính năng này");
    }
  }
}
```

#### Tóm tắt: Tại sao code giống nhau?

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  Owner Minh mở app        Employee Linh mở app                     │
│       │                         │                                   │
│       ▼                         ▼                                   │
│  Chọn location 5           Chọn location 5                         │
│  (ownerProfileId           (ownerProfileId                         │
│   = Minh's ID)              = Minh's ID)   ← cùng 1 giá trị       │
│       │                         │                                   │
│       ▼                         ▼                                   │
│  ┌────────────────────────────────────────────┐                     │
│  │  doc("usage_tracking", "{minh-id}_active") │  ← cùng 1 document │
│  └────────────────────┬───────────────────────┘                     │
│                       │                                             │
│              Firestore Security Rules                               │
│                       │                                             │
│            ┌──────────┴──────────┐                                  │
│            ▼                     ▼                                   │
│    myProfileId ==          exists(subscription_access               │
│    ownerProfileId?         /{minh}/members/{linh})?                 │
│    → YES → cho đọc         → YES + isActive + canReadUsage          │
│                              → cho đọc                              │
│            │                     │                                   │
│            ▼                     ▼                                   │
│    ┌──────────────────────────────────────┐                         │
│    │  Cùng 1 data trả về:                │                         │
│    │  { AI_ORDER: { used: 23, limit: 100 } }                       │
│    └──────────────────────────────────────┘                         │
│            │                     │                                   │
│            ▼                     ▼                                   │
│    ┌──────────────────────────────────────┐                         │
│    │  Cùng 1 component hiển thị:         │                         │
│    │  [Tạo order bằng AI]  23/100 lượt   │                         │
│    └──────────────────────────────────────┘                         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**FE không cần biết user là Owner hay Employee.** Chỉ cần:
1. Lấy `ownerProfileId` từ location đang làm việc
2. Đọc `usage_tracking/{ownerProfileId}_active`
3. Firestore Rules tự check quyền
4. Render UI theo data nhận được

### Owner cấp/thu hồi quyền cho Employee

Owner cần cấp quyền cho Employee thì Employee mới đọc được Firestore. API chỉ Owner gọi được:

```
POST /api/subscriptions/access-grants
{
  "memberProfileId": "linh-456",
  "canReadUsage": true,      // cho phép xem usage
  "isActive": true            // cho phép dùng tính năng
}

DELETE /api/subscriptions/access-grants/{memberProfileId}
→ Thu hồi hoàn toàn
```

---

## 9. Background Jobs

Các job chạy tự động đảm bảo hệ thống luôn chính xác:

| Job | Tần suất | Chức năng |
|-----|----------|-----------|
| `SubscriptionExpiryCheckJob` | Mỗi 30 phút | Check subscription hết hạn → Status = Expired, Firestore = expired |
| `SubscriptionReminderJob` | Mỗi ngày | Nhắc gia hạn T-3 và T-1 ngày trước khi hết hạn |
| `FirestoreSyncJob` | Mỗi 6 giờ | Đồng bộ SQL ↔ Firestore, sửa bất đồng bộ |
| `UsageSnapshotJob` | Mỗi ngày | Snapshot usage vào audit log |
| `StaleTransactionCleanupJob` | Mỗi giờ | Transaction Pending > 24h → Failed |
| `StripePendingReconcileJob` | Mỗi giờ | Kiểm tra Stripe payment thực tế cho transaction Pending |
| `StripeRefundReconcileJob` | Mỗi 2 giờ | Đồng bộ refund status từ Stripe |

### FirestoreSyncJob - Tại sao cần?

```
Vấn đề:
  Firestore: AI_ORDER.used = 25
  SQL:       AI_ORDER.UsedCount = 23

  → Sai lệch do: network error, Hangfire job fail, race condition

Giải pháp (FirestoreSyncJob):
  1. Đọc tất cả subscription Active từ SQL
  2. So sánh với Firestore
  3. Nếu sai lệch → SQL là source of truth → ghi đè Firestore
  4. Log anomaly vào SubscriptionAuditLog
```

---

## 10. API Endpoints

### Public (xem gói, không cần auth)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/api/subscription-plans` | Danh sách gói đăng ký (active) |
| GET | `/api/subscription-plans/{id}` | Chi tiết một gói |

### Subscription (cần auth)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/api/subscriptions/current` | Subscription hiện tại + usage |
| POST | `/api/subscriptions/checkout` | Tạo checkout session (mua mới) |
| POST | `/api/subscriptions/upgrade` | Upgrade/đổi gói |
| POST | `/api/subscriptions/renew` | Gia hạn |
| GET | `/api/subscriptions/transactions` | Lịch sử giao dịch |
| POST | `/api/subscriptions/access-grants` | Cấp quyền cho employee |
| DELETE | `/api/subscriptions/access-grants/{memberProfileId}` | Thu hồi quyền |

### Webhook (Stripe gọi, không cần auth)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| POST | `/api/webhooks/stripe` | Xử lý Stripe events |

### Admin (cần role admin)

| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/api/admin/subscription-plans` | Search gói (có phân trang) |
| GET | `/api/admin/subscription-plans/{id}` | Chi tiết gói (bao gồm cả inactive) |
| POST | `/api/admin/subscription-plans` | Tạo gói mới |
| PUT | `/api/admin/subscription-plans/{id}` | Sửa gói |
| DELETE | `/api/admin/subscription-plans/{id}` | Soft-delete gói |
| PATCH | `/api/admin/subscription-plans/{id}/status` | Bật/tắt gói (isActive) |
| PUT | `/api/admin/subscription-plans/{id}/price` | Cập nhật giá gói |
| GET | `/api/admin/subscription-plans/{id}/prices` | Lịch sử giá |
| GET | `/api/admin/features` | Danh sách feature |

---

## 11. FE gọi Firestore trực tiếp: Chi tiết kỹ thuật

### FE gọi thẳng Firestore, không qua BE API

FE dùng **Firebase SDK** nói chuyện trực tiếp với Firestore để đọc usage data. Không cần gọi BE API để hỏi "tôi có quyền không?". Ai được đọc gì do **Firestore Security Rules** quyết định.

### Luồng xác thực

```
FE đăng nhập BizFlow
    │
    ├── Firebase Auth cấp ID Token
    │   Token chứa custom claim: { profileId: "abc-123" }
    │
    └── FE dùng token này để gọi Firestore
        → Firestore Security Rules đọc token, check quyền tự động
```

### Firestore Security Rules

File: `firestore.rules`

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {

    // Lấy profileId từ Firebase Auth token
    function myProfileId() {
      return request.auth.token.profileId;
    }

    // Kill-switch: admin có thể tắt FE đọc Firestore bất cứ lúc nào
    function isClientReadEnabled() {
      let gatePath = /databases/.../system_config/firestore_gate;
      return exists(gatePath)
        && get(gatePath).data.allowClientRead == true;
    }

    // CHECK QUYỀN ĐỌC: Owner đọc trực tiếp, Employee đọc nếu được cấp
    function canReadOwnerUsage(ownerProfileId) {
      let me = myProfileId();
      let memberPath = /databases/.../subscription_access/{ownerProfileId}/members/{me};

      return me == ownerProfileId              // TÔI LÀ OWNER → cho đọc
        || (exists(memberPath)                  // HOẶC tồn tại doc access grant
            && get(memberPath).data.isActive == true    // VÀ đang active
            && get(memberPath).data.canReadUsage == true); // VÀ được cho phép
    }

    // usage_tracking: FE chỉ được ĐỌC, KHÔNG được GHI
    match /usage_tracking/{docId} {
      allow get: if isSignedIn()
                  && isClientReadEnabled()
                  && canReadOwnerUsage(resource.data.ownerProfileId);
      allow list: if false;                    // KHÔNG list toàn bộ collection
      allow create, update, delete: if false;  // KHÔNG được ghi
    }

    // subscription_access: FE KHÔNG đọc được trực tiếp
    // (chỉ BE ghi, Rules dùng nội bộ qua get() trong canReadOwnerUsage)
    match /subscription_access/{ownerProfileId}/members/{memberProfileId} {
      allow read, write: if false;
    }
  }
}
```

**Điểm then chốt:**

- `subscription_access` → FE **KHÔNG** đọc được trực tiếp (`allow read: if false`)
- Nhưng Firestore Rules **tự check ngầm** bên trong hàm `canReadOwnerUsage()` bằng `get()` và `exists()`
- Employee chỉ cần **thử đọc** `usage_tracking/{ownerProfileId}_active` → Rules tự kiểm tra employee có trong `subscription_access` không → Có thì trả data, không thì deny

### FE code cụ thể

#### Bước 1: Lấy `ownerProfileId`

FE lấy từ thông tin location (khi employee chọn quán/chi nhánh):

```typescript
// Từ API /locations hoặc lưu local khi đăng nhập
const ownerProfileId = currentLocation.ownerProfileId;
```

#### Bước 2: Đọc usage_tracking (Realtime)

```typescript
import { getFirestore, doc, getDoc, onSnapshot } from "firebase/firestore";

const db = getFirestore();

// Document ID = {ownerProfileId}_active
const usageDocRef = doc(db, "usage_tracking", `${ownerProfileId}_active`);

// ═══════════════════════════════════════
// Cách 1: Đọc 1 lần (one-time read)
// ═══════════════════════════════════════
const snapshot = await getDoc(usageDocRef);

if (snapshot.exists()) {
  const data = snapshot.data();
  // data = {
  //   status: "active",
  //   planName: "Gói Pro",
  //   features: {
  //     AI_ORDER:     { used: 23, limit: 100 },
  //     AI_ANALYTICS: { used: 10, limit: 50  },
  //     EXPORT_PDF:   { used: 45, limit: -1  }
  //   }
  // }
}

// ═══════════════════════════════════════
// Cách 2: Realtime listener (recommend)
// ═══════════════════════════════════════
const unsubscribe = onSnapshot(usageDocRef, (snapshot) => {
  if (!snapshot.exists()) {
    // Không có subscription → ẩn tính năng premium
    disableAllPremiumFeatures();
    return;
  }

  const data = snapshot.data();

  if (data.status !== "active") {
    showExpiredBanner();
    return;
  }

  // Cập nhật UI cho từng tính năng
  for (const [featureCode, usage] of Object.entries(data.features)) {
    updateFeatureUI(featureCode, usage.used, usage.limit);
  }
});
```

#### Bước 3: Check 1 tính năng cụ thể

```typescript
function canUseFeature(featureCode: string, usageData: any): boolean {
  if (!usageData || usageData.status !== "active") return false;

  const feature = usageData.features?.[featureCode];
  if (!feature) return false;

  // limit < 0 → unlimited
  if (feature.limit < 0) return true;

  // Còn quota?
  return feature.used < feature.limit;
}

// Sử dụng:
if (canUseFeature("AI_ORDER", usageData)) {
  showButton("Tạo order bằng AI");        // enabled
  showBadge("23/100 lần");
} else {
  showButton("Tạo order bằng AI", { disabled: true });
  showTooltip("Đã hết lượt hoặc cần nâng cấp gói");
}
```

#### Với Employee: không cần code khác biệt

```typescript
// Owner và Employee dùng CÙNG MỘT code
// Firestore Rules tự xử lý quyền đọc:
//   - Owner → đọc được (vì ownerProfileId == myProfileId)
//   - Employee → đọc được NẾU owner đã cấp access grant
//   - Người lạ → Permission Denied (Firestore tự chặn)

const usageDocRef = doc(db, "usage_tracking", `${ownerProfileId}_active`);

try {
  const snapshot = await getDoc(usageDocRef);
  if (snapshot.exists()) {
    // Đọc được → có quyền → hiển thị tính năng
    renderPremiumFeatures(snapshot.data());
  }
} catch (error) {
  if (error.code === "permission-denied") {
    // Không có quyền đọc → không được cấp access grant
    // → ẩn tính năng premium, hoặc hiển thị "Liên hệ chủ quán"
    hidePremiumFeatures();
  }
}
```

### 3 lớp bảo vệ

```
┌──────────────────────────────────────────────────────────────────┐
│  LỚP 1: FIRESTORE SECURITY RULES (ai được ĐỌC data)            │
│                                                                  │
│  Employee thử đọc usage_tracking/{ownerProfileId}_active         │
│    → Rules tự check: employee có trong subscription_access?      │
│    → CÓ + isActive + canReadUsage → cho đọc                     │
│    → KHÔNG → Permission Denied                                   │
│                                                                  │
│  ⚡ Chặn ngay ở tầng Firestore, BE không cần làm gì              │
├──────────────────────────────────────────────────────────────────┤
│  LỚP 2: FE CHECK (hiển thị UI thông minh)                       │
│                                                                  │
│  FE đọc được data → check:                                      │
│    status === "active"?                                          │
│    features.AI_ORDER.used < features.AI_ORDER.limit?             │
│    → CÒN → enable button                                        │
│    → HẾT → disable button, show message                         │
│                                                                  │
│  ⚡ UX tốt: user thấy ngay mình còn dùng được không              │
├──────────────────────────────────────────────────────────────────┤
│  LỚP 3: BE CHECK (không tin FE, tuyến phòng thủ cuối)           │
│                                                                  │
│  FE gọi POST /api/orders/voice                                  │
│    → [RequireFeature("AI_ORDER")] filter chạy                    │
│    → Check location access, tìm owner, check subscription,      │
│      check quota từ Firestore/SQL                                │
│    → PASS → thực hiện                                            │
│    → FAIL → 403 Forbidden                                        │
│                                                                  │
│  ⚡ Dù FE bị hack/bypass, BE vẫn chặn được                       │
└──────────────────────────────────────────────────────────────────┘
```

**Tóm lại:**
- **Lớp 1** (Firestore Rules): quyết định ai **thấy** data
- **Lớp 2** (FE logic): quyết định UI **hiển thị** thế nào
- **Lớp 3** (BE filter): quyết định có **thực sự cho làm** hay không

FE không cần gọi API riêng để "hỏi BE tôi có quyền không?". FE đọc thẳng Firestore, Rules đã check quyền. Khi thực sự gọi action (tạo order), BE check lại hoàn toàn độc lập một lần nữa.

---

## Tổng kết: Câu hỏi thường gặp

### Q: FE bypass check usage rồi gọi API thẳng thì sao?
**A:** BE luôn check lại bằng `[RequireFeature]`. FE check chỉ để **hiển thị UI đẹp** (disable button, show badge). Bảo mật nằm ở BE.

### Q: Employee dùng tính năng thì trừ quota của ai?
**A:** Luôn trừ quota của **Owner**. Employee không có subscription riêng. Logic: tìm owner qua location → check subscription của owner → trừ usage của owner.

### Q: Nếu Firestore chết thì sao?
**A:** BE fallback về SQL. Code check: nếu Firestore trả `null` → dùng SQL `FeatureUsage.UsedCount`. FE mất realtime nhưng vẫn gọi API `/subscriptions/current` được.

### Q: Thanh toán xong nhưng BE crash, user có mất tiền không?
**A:** Không. BE có **compensation refund**: nếu tạo subscription thất bại sau khi nhận tiền → tự động refund qua Stripe.

### Q: 2 employee dùng cùng lúc, race condition?
**A:** Firestore dùng `FieldValue.Increment(1)` (atomic operation) nên không bị race condition ở tầng realtime. SQL cập nhật qua Hangfire (eventual consistency) và `FirestoreSyncJob` reconcile mỗi 6 giờ.

### Q: Upgrade gói thì tính tiền sao?
**A:** Proration credit = Tiền đã trả × min(tỷ lệ thời gian còn lại, tỷ lệ usage còn lại). Nếu credit ≥ giá gói mới → upgrade miễn phí (không cần thanh toán). Nếu credit < giá gói mới → trả phần chênh lệch qua Stripe.
