# RetailAI Agent — Coding Standards

## Python (Backend)

### Style
- **PEP 8** enforced via `ruff`
- **Type hints** required on all public functions and class attributes
- **Docstrings** on all modules, classes, and non-trivial functions (Google style)
- Max line length: **100 characters**

### Naming Conventions
```python
# Modules/packages: snake_case
app/core/security.py

# Classes: PascalCase
class CurrentUser: ...

# Functions/variables: snake_case
def verify_password(plain: str, hashed: str) -> bool: ...

# Constants: SCREAMING_SNAKE_CASE
ACCESS_TOKEN_EXPIRE_MIN = 30

# Private: leading underscore
def _build_engine(): ...
```

### FastAPI Patterns
```python
# Always type-annotate route parameters
@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: DBDep) -> TokenResponse:
    ...

# Use Annotated for dependency injection
DBDep = Annotated[AsyncSession, Depends(get_db)]

# Prefer Depends(require_permission()) over inline auth checks
@router.delete("/{id}", dependencies=[Depends(require_permission("users:delete"))])
async def delete_user(id: str, db: DBDep): ...
```

### Database Patterns
```python
# Always use async sessions
async with AsyncSessionLocal() as session:
    result = await session.execute(select(User).where(User.id == id))
    user = result.scalar_one_or_none()

# Never use session.query() — use select() statements
# ✅ Correct
result = await db.execute(select(User).where(User.email == email))
# ❌ Wrong
user = db.query(User).filter(User.email == email).first()
```

### Error Handling
```python
# Always raise HTTPException — never return error dicts manually
raise HTTPException(status_code=404, detail="User not found")

# Log before raising in service layer
logger.warning("Resource not found", extra={"resource": "user", "id": id})
raise HTTPException(...)
```

### Logging
```python
logger = get_logger(__name__)   # Always use module name

# ✅ Structured logging with extra context
logger.info("Camera created", extra={"camera_id": cam.id, "user": user_id})

# ❌ Never use f-strings in log messages (defeats lazy evaluation)
logger.info(f"Camera {cam.id} created")
```

### Testing
- **Unit tests**: pure functions, no I/O, use `pytest`
- **Integration tests**: in-memory SQLite via `AsyncClient` + `ASGITransport`
- **Coverage target**: ≥ 70% overall, ≥ 90% for `core/security.py`
- Mark tests with `@pytest.mark.unit` / `@pytest.mark.integration`

```python
# Always use pytest-asyncio for async tests
@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User):
    ...
```

---

## TypeScript (Frontend)

### Style
- **ESLint** + **Prettier** enforced (Next.js defaults)
- **Strict TypeScript** — no `any` in production code (only in API response types)
- Max line length: **120 characters**

### Component Patterns
```tsx
// Prefer named exports over default for components
export function StatCard({ title, value }: StatCardProps) { ... }

// Always define Props interface above the component
interface StatCardProps {
  title: string;
  value: number | string;
  loading?: boolean;
}

// Use 'use client' directive only where needed
"use client";
```

### Data Fetching
```tsx
// Always use TanStack Query for server state
const { data, isLoading } = useQuery({
  queryKey: ["cameras"],
  queryFn: api.getCameras,
  refetchInterval: 60_000,
});

// Never fetch in useEffect for data that belongs in server state
```

### API Client
```tsx
// All API calls go through /src/lib/api.ts
// Never use fetch() directly in components
const data = await api.getCameras();          // ✅
const data = await fetch('/api/cameras/');    // ❌
```

---

## Git Workflow

### Branch naming
```
feature/  camera-zone-editor
fix/      queue-depth-overflow
chore/    update-dependencies
docs/     add-deployment-guide
```

### Commit format (Conventional Commits)
```
feat(auth): add refresh token endpoint
fix(heatmap): correct cell normalization for edge cameras
chore(deps): bump ultralytics to 8.3.55
docs(arch): update RBAC permission table
test(auth): add integration tests for /me endpoint
```

### PR Checklist
- [ ] Tests pass (`pytest` + `npm test`)
- [ ] No TypeScript errors (`npm run build`)
- [ ] Linting clean (`ruff check backend/`)
- [ ] Privacy rules unchanged (FEATURE_FACIAL_RECOG=false)
- [ ] API changes reflected in `/docs/api/README.md`
- [ ] Migrations created for schema changes (`alembic revision --autogenerate`)

---

## Privacy Rules (Non-Negotiable)

These rules are enforced at the code level and must never be violated:

1. **No facial recognition** — `detector.py` uses `classes=[0]` only (person bounding box)
2. **No biometric storage** — only normalized centroid (x, y) coordinates stored
3. **No identity linking** — Track IDs are session-ephemeral integers
4. **No video to cloud** — `FEATURE_CLOUD_SYNC=false` disables any cloud upload
5. **No PII in logs** — Never log names, faces, or identifying attributes
