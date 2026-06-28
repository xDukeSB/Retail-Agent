"""
Integration tests for auth endpoints — login, refresh, change password.
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import AsyncSessionLocal
from app.core.security import hash_password, Role
from app.models.user import User
from main import app
from app.core.deps import get_db

# ── In-memory test database ───────────────────────────────────────────────────
TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    async with TestSessionLocal() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession) -> User:
    user = User(
        email="admin@test.local",
        full_name="Test Admin",
        hashed_password=hash_password("AdminPass123!"),
        role=Role.ADMIN.value,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def test_viewer(db_session: AsyncSession) -> User:
    user = User(
        email="viewer@test.local",
        full_name="Test Viewer",
        hashed_password=hash_password("ViewerPass123!"),
        role=Role.VIEWER.value,
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestLogin:
    async def test_login_success(self, client: AsyncClient, test_admin: User):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "admin@test.local",
            "password": "AdminPass123!",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token"  in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient, test_admin: User):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "admin@test.local",
            "password": "WrongPass999!",
        })
        assert resp.status_code == 401

    async def test_login_unknown_email(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "nobody@test.local",
            "password": "SomePass123!",
        })
        assert resp.status_code == 401


class TestGetMe:
    async def test_get_me_authenticated(self, client: AsyncClient, test_admin: User):
        login = await client.post("/api/v1/auth/login", json={
            "email": "admin@test.local",
            "password": "AdminPass123!",
        })
        token = login.json()["access_token"]
        resp  = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["email"] == "admin@test.local"
        assert resp.json()["role"]  == "admin"

    async def test_get_me_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 403


class TestHealthEndpoints:
    async def test_liveness(self, client: AsyncClient):
        resp = await client.get("/api/v1/health/live")
        assert resp.status_code == 200
        assert resp.json()["alive"] is True

    async def test_readiness(self, client: AsyncClient):
        resp = await client.get("/api/v1/health/ready")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True

    async def test_full_health(self, client: AsyncClient):
        resp = await client.get("/api/v1/health/")
        assert resp.status_code == 200
        data = resp.json()
        assert "status"     in data
        assert "components" in data
        assert "uptime_seconds" in data
