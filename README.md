# RetailAI Agent

> **Local-First Retail Intelligence Platform** — Transform existing CCTV cameras into anonymous business analytics. Zero cloud dependency. Works offline. Privacy by design.

---

## ✨ Features

| Feature | Status |
|---------|--------|
| Customer Count (In/Out) | ✅ |
| Dwell Time Analytics | ✅ |
| Store Heatmap | ✅ |
| Queue Analytics | ✅ |
| Checkout Analytics | ✅ |
| Conversion Funnel | ✅ |
| Anonymous Timeline | ✅ |
| Business Reports (PDF/CSV) | ✅ |
| Role-Based Access (Admin/Manager/Viewer) | ✅ |
| Local-First (Offline Mode) | ✅ |
| PostgreSQL Migration Path | ✅ |

---

## 🏗️ Architecture

```
RTSP Camera → CV Pipeline (YOLOv11n + ByteTrack) → FastAPI Backend → Next.js Dashboard
```

**Stack:**
- **Backend**: FastAPI 0.115 · SQLAlchemy 2.0 · SQLite (→ PostgreSQL) · Alembic
- **Frontend**: Next.js 15 · TanStack Query · Recharts · Tailwind CSS
- **CV**: YOLOv11n · ByteTrack · OpenCV
- **Streaming**: MediaMTX (RTSP → HLS)
- **Auth**: JWT (HS256) · bcrypt · RBAC

---

## 🚀 Quick Start

### Option A — One Command Setup

```bash
git clone <repo> retail-ai-agent && cd retail-ai-agent
bash scripts/setup.sh --dev
```

### Option B — Manual

```bash
# 1. Environment
cp .env.example .env
# Edit .env — set a real SECRET_KEY

# 2. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd .. && mkdir -p data/db data/reports data/models

uvicorn backend.main:app --reload --port 8000
# → http://localhost:8000/api/docs

# 3. Seed demo data (optional)
python scripts/seed-demo.py

# 4. Frontend
cd apps/frontend
npm install && npm run dev
# → http://localhost:3000
```

### Option C — Docker (Full Stack)

```bash
cp .env.example .env
# Set SECRET_KEY and ADMIN_PASSWORD in .env

docker compose -f docker/docker-compose.yml up -d
# → http://localhost:3000   (Dashboard)
# → http://localhost:8000   (API)
```

---

## 🔐 Default Credentials

| Field | Value |
|-------|-------|
| Email | `admin@retailai.local` |
| Password | `ChangeMe123!` |
| Role | Admin |

> ⚠️ **Change the password on first login.** The system forces this via `must_change_password: true`.

---

## 👥 Roles

| Role | Description |
|------|-------------|
| **Admin** | Full system access — user management, system config |
| **Manager** | Camera config, zone editor, reports export, analytics |
| **Viewer** | Read-only dashboard and analytics |

---

## 📁 Project Structure

```
retail-ai-agent/
├── backend/          # FastAPI + SQLAlchemy (Python)
├── apps/frontend/    # Next.js 15 dashboard
├── services/
│   ├── cv-pipeline/  # YOLOv11n + ByteTrack
│   └── stream-relay/ # MediaMTX
├── database/         # Alembic migrations
├── docker/           # Docker Compose + Nginx
├── docs/             # Architecture + API docs
├── scripts/          # Setup, seed, health-check
└── tests/            # Unit + integration tests
```

---

## 🧪 Testing

```bash
# Install test dependencies
cd backend && pip install -r ../tests/requirements-test.txt

# Run all tests
cd .. && PYTHONPATH=backend pytest

# With coverage
PYTHONPATH=backend pytest --cov=app --cov-report=term-missing

# Unit tests only
PYTHONPATH=backend pytest -m unit

# Integration tests only
PYTHONPATH=backend pytest -m integration
```

---

## 🗄️ Database

Default: **SQLite** at `./data/db/retailai.db`

### Migrate to PostgreSQL

1. Set in `.env`:
   ```
   DB_DIALECT=postgresql
   POSTGRES_DSN=postgresql+asyncpg://user:pass@host:5432/retailai
   ```
2. Run migrations:
   ```bash
   alembic -c database/alembic.ini upgrade head
   ```

No application code changes required — SQLAlchemy abstracts the dialect.

### Migrations

```bash
# Create a new migration
PYTHONPATH=backend alembic -c database/alembic.ini revision --autogenerate -m "add_column_x"

# Apply migrations
PYTHONPATH=backend alembic -c database/alembic.ini upgrade head

# Rollback one
PYTHONPATH=backend alembic -c database/alembic.ini downgrade -1
```

---

## 🔍 Health Check

```bash
bash scripts/health-check.sh
# Or:
curl http://localhost:8000/api/v1/health/ | python3 -m json.tool
```

---

## 🔒 Privacy Guarantees

| Guarantee | Implementation |
|-----------|---------------|
| No facial recognition | Detector hardcoded to `classes=[0]` (bounding box only) |
| No biometrics stored | Only normalized centroid (x, y) per frame |
| No identity linking | Track IDs are ephemeral session integers |
| No video to cloud | `FEATURE_CLOUD_SYNC=false` enforced at startup |
| No PII in logs | Structured logger never emits identifying data |

---

## 📖 Documentation

- [Architecture](docs/architecture/README.md)
- [API Reference](docs/api/README.md)
- [Coding Standards](docs/CODING_STANDARDS.md)

---

## 📄 License

Proprietary — RetailAI Agent © 2024. All rights reserved.
