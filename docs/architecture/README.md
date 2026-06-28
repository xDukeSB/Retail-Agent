# RetailAI Agent — Architecture Documentation

## System Overview

RetailAI Agent is a **Local-First Retail Intelligence Platform** that transforms existing CCTV cameras into anonymous retail analytics — with zero cloud dependency.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         LOCAL MACHINE                                │
│                                                                      │
│  ┌──────────┐   RTSP    ┌──────────────────┐  HTTP  ┌───────────┐  │
│  │  Camera  │──────────▶│  CV Pipeline     │───────▶│  Backend  │  │
│  │ (IP/USB) │           │  YOLOv11n        │        │  FastAPI  │  │
│  └──────────┘           │  ByteTrack       │        │  SQLite   │  │
│                         │  Zone Manager    │        └─────┬─────┘  │
│                         └──────────────────┘              │ WS      │
│                                                           ▼         │
│                                                    ┌────────────┐   │
│                                                    │  Frontend  │   │
│                                                    │  Next.js   │   │
│                                                    │  :3000     │   │
│                                                    └────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                              ↑
                   Cloud sync (OPTIONAL, disabled by default)
```

## Directory Structure

```
retail-ai-agent/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── api/v1/             # Versioned REST API
│   │   │   └── endpoints/      # health, auth, users, cameras, analytics
│   │   ├── core/               # Cross-cutting concerns
│   │   │   ├── config.py       # Pydantic Settings (layered env)
│   │   │   ├── security.py     # JWT + bcrypt + RBAC
│   │   │   ├── logging.py      # Structured JSON/text logging
│   │   │   └── deps.py         # Dependency injection
│   │   ├── db/                 # Database abstraction
│   │   │   ├── base.py         # Declarative base + mixins
│   │   │   └── session.py      # SQLite/PostgreSQL engine factory
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/           # Business logic
│   │   └── middleware/         # Request logging, correlation IDs
│   ├── main.py                 # App factory + lifespan hooks
│   ├── requirements.txt
│   └── Dockerfile
├── apps/frontend/              # Next.js 15 dashboard
├── services/
│   ├── cv-pipeline/            # YOLOv11n + ByteTrack
│   └── stream-relay/           # MediaMTX (RTSP → HLS)
├── database/
│   ├── migrations/             # Alembic async migrations
│   └── seeds/                  # Demo data
├── docker/
│   ├── docker-compose.yml      # Production
│   ├── docker-compose.dev.yml  # Development (hot reload)
│   └── nginx/nginx.conf        # Reverse proxy
├── docs/                       # Architecture + API docs
├── scripts/
│   ├── setup.sh                # One-command project setup
│   ├── health-check.sh         # Service health verification
│   └── seed-demo.py            # 30-day demo data generator
└── tests/
    ├── unit/                   # Pure unit tests (no I/O)
    └── integration/            # In-memory DB integration tests
```

## Security Architecture

### Authentication Flow
```
Client → POST /api/v1/auth/login → {access_token, refresh_token}
Client → GET  /api/v1/auth/me   → Bearer {access_token}
Client → POST /api/v1/auth/refresh → new {access_token}
```

### Role-Based Access Control

| Permission         | Viewer | Manager | Admin |
|--------------------|--------|---------|-------|
| analytics:read     | ✅     | ✅      | ✅    |
| reports:export     | ❌     | ✅      | ✅    |
| cameras:write      | ❌     | ✅      | ✅    |
| cameras:delete     | ❌     | ❌      | ✅    |
| users:write        | ❌     | ❌      | ✅    |
| system:config      | ❌     | ❌      | ✅    |

## Database Migration Path

### SQLite → PostgreSQL (Zero-downtime)

1. Export data: `sqlite3 data/db/retailai.db .dump > backup.sql`
2. Set `DB_DIALECT=postgresql` and `POSTGRES_DSN=...` in `.env`
3. Run migrations: `alembic -c database/alembic.ini upgrade head`
4. Import data via pgloader or custom migration script
5. Restart services

SQLAlchemy's dialect abstraction ensures **no application code changes** are needed.

## Logging

All logs emit as **structured JSON** in production:
```json
{
  "timestamp": "2024-01-15T10:30:00.123Z",
  "level": "INFO",
  "logger": "app.api.v1.endpoints.auth",
  "message": "User logged in",
  "correlation_id": "a1b2c3d4-...",
  "user_id": "uuid",
  "role": "manager"
}
```

Each HTTP request receives a `X-Correlation-ID` header for end-to-end tracing.

## API Versioning

All endpoints are namespaced under `/api/v1/`. Future versions use `/api/v2/` with backward compatibility maintained via deprecation notices and migration periods.
