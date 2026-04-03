# 1. BIZFLOW BUSINESS CONTEXT (Quy định cao nhất)
- Tệp khách hàng: Hộ Kinh Doanh (HKD) nhỏ lẻ.
- Tôn chỉ: Đơn giản, hiệu quả, dễ giải thích. KHÔNG over-engineering.
- Output & Giải thích: Luôn trả về dữ liệu hoặc text phân tích bằng Tiếng Việt.
- Hạn chế: Không dùng các thư viện ML nặng (scikit-learn, prophet) trừ khi có yêu cầu. Ưu tiên Pandas hoặc logic Rule-based.
- Chi tiết context xem tại: BIZFLOW_PLATFORM_TO_SUPPORT_DIGITAL_TRANSFORMATION.md

# 2. PYTHON & ARCHITECTURE RULES
- Project sử dụng Python, FastAPI.
- Phân tách layer rõ ràng: Routers (chỉ nhận/trả request) -> Services (Core logic) -> Repositories/Clients (gọi external API, DB).
- Type hints: Bắt buộc sử dụng Python type hints (typing) nghiêm ngặt cho mọi tham số và return type.

# 3. AI FEATURES HANDLING
- Speech-to-Text: Mặc định dùng Google STT REST đồng bộ (sync), chỉ dùng OpenAI Whisper làm fallback.
- OCR (GPT-4o Vision): Luôn kiểm tra và yêu cầu client pre-process (resize/compress) ảnh trước khi gọi API để tối ưu cost.
- Forecasting & Reorder: Dùng Pandas vectorized functions (SMA, EMA, Reorder formula) để tính toán. Chỉ dùng LLM để generate câu giải thích.

# 4. FASTAPI BEST PRACTICES
When to use
Use this skill when working with FastAPI code. It teaches current best practices and prevents common mistakes that AI agents make with outdated patterns.

Critical Rules
1. Use async def for I/O-bound endpoints, def for CPU-bound
Wrong (agents do this):

@app.get("/users")
def get_users():
    users = db.query(User).all()
    return users

@app.get("/data")
async def get_data():
    result = heavy_computation()
    return result
Correct:

@app.get("/users")
async def get_users(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User))
    return result.scalars().all()

@app.get("/data")
def get_data():
    return heavy_computation()
Why: FastAPI runs async endpoints in the event loop; sync endpoints run in a thread pool. Use async for I/O (DB, HTTP, file) to avoid blocking. Use def for CPU-bound work; making it async would block the event loop.

2. Use Depends() for dependency injection
Wrong (agents do this):

db = get_database()

@app.get("/items")
async def get_items():
    return db.query(Item).all()
Correct:

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/items")
async def get_items(db: Annotated[Session, Depends(get_db)]):
    return db.query(Item).all()
Why: Global DB connections leak, are not testable, and bypass FastAPI's dependency system. Depends() provides proper scoping, cleanup, and test overrides.

3. Use Pydantic v2 patterns
Wrong (agents do this):

from pydantic import validator

class Item(BaseModel):
    name: str
    price: float

    class Config:
        orm_mode = True

    @validator("price")
    def price_positive(cls, v):
        if v <= 0:
            raise ValueError("must be positive")
        return v
Correct:

from pydantic import BaseModel, field_validator, ConfigDict

class Item(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    price: float

    @field_validator("price")
    @classmethod
    def price_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("must be positive")
        return v
Why: Pydantic v1 validator, Config, and orm_mode are deprecated. Use field_validator, model_validator, ConfigDict, and from_attributes.

4. Use lifespan context manager
Wrong (agents do this):

@app.on_event("startup")
async def startup():
    app.state.db = await create_pool()

@app.on_event("shutdown")
async def shutdown():
    await app.state.db.close()
Correct:

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await create_pool()
    yield
    await app.state.db.close()

app = FastAPI(lifespan=lifespan)
Why: on_event is deprecated. The lifespan context manager gives a single place for startup and shutdown with proper resource ordering.

5. Use BackgroundTasks for fire-and-forget work
Wrong (agents do this):

@app.post("/send-email")
async def send_email(email: str):
    asyncio.create_task(send_email_async(email))
    return {"status": "queued"}
Correct:

@app.post("/send-email")
async def send_email(email: str, background_tasks: BackgroundTasks):
    background_tasks.add_task(send_email_async, email)
    return {"status": "queued"}
Why: asyncio.create_task can outlive the request and is not awaited on shutdown. BackgroundTasks runs after the response is sent and is tied to the request lifecycle.

6. Use APIRouter for route organization
Wrong (agents do this):

# main.py - 500 lines of routes
@app.get("/users")
@app.get("/users/{id}")
@app.post("/items")
@app.get("/items")
Correct:

# main.py
app.include_router(users.router, prefix="/users", tags=["users"])
app.include_router(items.router, prefix="/items", tags=["items"])

# routers/users.py
router = APIRouter()
@router.get("/")
@router.get("/{id}")
Why: Single-file apps become unmaintainable. APIRouter enables routers/, models/, services/, dependencies/ structure.

7. Use response_model for output validation
Wrong (agents do this):

@app.get("/items/{id}")
async def get_item(id: int):
    item = await db.get(Item, id)
    return {"id": item.id, "name": item.name}
Correct:

@app.get("/items/{id}", response_model=ItemOut)
async def get_item(id: int, db: Session = Depends(get_db)):
    item = await db.get(Item, id)
    if not item:
        raise HTTPException(status_code=404)
    return item
Why: Raw dicts bypass validation and OpenAPI. response_model ensures schema consistency, serialization, and docs.

8. Use status codes from fastapi.status
Wrong (agents do this):

raise HTTPException(status_code=404, detail="Not found")
raise HTTPException(status_code=401, detail="Unauthorized")
Correct:

from fastapi import status

raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
Why: Magic numbers are error-prone. status constants are self-documenting and match HTTP spec.

9. Use Annotated for dependencies
Wrong (agents do this):

@app.get("/me")
async def read_me(current_user: User = Depends(get_current_user)):
    return current_user
Correct:

@app.get("/me")
async def read_me(current_user: Annotated[User, Depends(get_current_user)]):
    return current_user
Why: Annotated is the recommended FastAPI pattern. It keeps types and dependencies in one place and supports dependency reuse.

10. Use pydantic-settings for configuration
Wrong (agents do this):

import os
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///db.sqlite")
Correct:

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///db.sqlite"
    debug: bool = False
    model_config = {"env_file": ".env"}

settings = Settings()
Why: os.getenv has no validation or typing. BaseSettings provides validation, .env loading, and type safety.

Patterns
Define routers in routers/ with prefix and tags
Put shared dependencies in dependencies.py
Use HTTPException with status constants for errors
Use Path, Query, Body, Header with validation (min_length, ge, le)
Register custom exception handlers with app.add_exception_handler
Use middleware sparingly; order matters (first added runs last for requests)
Anti-Patterns
Do not use @app.on_event("startup") or @app.on_event("shutdown")
Do not use asyncio.create_task for request-scoped background work
Do not use global variables for DB, cache, or config
Do not use Pydantic v1 @validator or class Config
Do not return raw dicts without response_model
Do not use magic numbers for status codes
Do not put all routes in main.py

# 5. PANDAS BEST PRACTICES
Pandas Pro
Expert pandas developer specializing in efficient data manipulation, analysis, and transformation workflows with production-grade performance patterns.

Core Workflow
Assess data structure — Examine dtypes, memory usage, missing values, data quality:
print(df.dtypes)
print(df.memory_usage(deep=True).sum() / 1e6, "MB")
print(df.isna().sum())
print(df.describe(include="all"))
Design transformation — Plan vectorized operations, avoid loops, identify indexing strategy
Implement efficiently — Use vectorized methods, method chaining, proper indexing
Validate results — Check dtypes, shapes, null counts, and row counts:
assert result.shape[0] == expected_rows, f"Row count mismatch: {result.shape[0]}"
assert result.isna().sum().sum() == 0, "Unexpected nulls after transform"
assert set(result.columns) == expected_cols
Optimize — Profile memory, apply categorical types, use chunking if needed
Reference Guide
Load detailed guidance based on context:

Topic	Reference	Load When
DataFrame Operations	references/dataframe-operations.md	Indexing, selection, filtering, sorting
Data Cleaning	references/data-cleaning.md	Missing values, duplicates, type conversion
Aggregation & GroupBy	references/aggregation-groupby.md	GroupBy, pivot, crosstab, aggregation
Merging & Joining	references/merging-joining.md	Merge, join, concat, combine strategies
Performance Optimization	references/performance-optimization.md	Memory usage, vectorization, chunking
Code Patterns
Vectorized Operations (before/after)
# ❌ AVOID: row-by-row iteration
for i, row in df.iterrows():
    df.at[i, 'tax'] = row['price'] * 0.2

# ✅ USE: vectorized assignment
df['tax'] = df['price'] * 0.2
Safe Subsetting with .copy()
# ❌ AVOID: chained indexing triggers SettingWithCopyWarning
df['A']['B'] = 1

# ✅ USE: .loc[] with explicit copy when mutating a subset
subset = df.loc[df['status'] == 'active', :].copy()
subset['score'] = subset['score'].fillna(0)
GroupBy Aggregation
summary = (
    df.groupby(['region', 'category'], observed=True)
    .agg(
        total_sales=('revenue', 'sum'),
        avg_price=('price', 'mean'),
        order_count=('order_id', 'nunique'),
    )
    .reset_index()
)
Merge with Validation
merged = pd.merge(
    left_df, right_df,
    on=['customer_id', 'date'],
    how='left',
    validate='m:1',          # asserts right key is unique
    indicator=True,
)
unmatched = merged[merged['_merge'] != 'both']
print(f"Unmatched rows: {len(unmatched)}")
merged.drop(columns=['_merge'], inplace=True)
Missing Value Handling
# Forward-fill then interpolate numeric gaps
df['price'] = df['price'].ffill().interpolate(method='linear')

# Fill categoricals with mode, numerics with median
for col in df.select_dtypes(include='object'):
    df[col] = df[col].fillna(df[col].mode()[0])
for col in df.select_dtypes(include='number'):
    df[col] = df[col].fillna(df[col].median())
Time Series Resampling
daily = (
    df.set_index('timestamp')
    .resample('D')
    .agg({'revenue': 'sum', 'sessions': 'count'})
    .fillna(0)
)
Pivot Table
pivot = df.pivot_table(
    values='revenue',
    index='region',
    columns='product_line',
    aggfunc='sum',
    fill_value=0,
    margins=True,
)
Memory Optimization
# Downcast numerics and convert low-cardinality strings to categorical
df['category'] = df['category'].astype('category')
df['count'] = pd.to_numeric(df['count'], downcast='integer')
df['score'] = pd.to_numeric(df['score'], downcast='float')
print(df.memory_usage(deep=True).sum() / 1e6, "MB after optimization")
Constraints
MUST DO
Use vectorized operations instead of loops
Set appropriate dtypes (categorical for low-cardinality strings)
Check memory usage with .memory_usage(deep=True)
Handle missing values explicitly (don't silently drop)
Use method chaining for readability
Preserve index integrity through operations
Validate data quality before and after transformations
Use .copy() when modifying subsets to avoid SettingWithCopyWarning
MUST NOT DO
Iterate over DataFrame rows with .iterrows() unless absolutely necessary
Use chained indexing (df['A']['B']) — use .loc[] or .iloc[]
Ignore SettingWithCopyWarning messages
Load entire large datasets without chunking
Use deprecated methods (.ix, .append() — use pd.concat())
Convert to Python lists for operations possible in pandas
Assume data is clean without validation
Output Templates
When implementing pandas solutions, provide:

Code with vectorized operations and proper indexing
Comments explaining complex transformations
Memory/performance considerations if dataset is large
Data validation checks (dtypes, nulls, shapes)

