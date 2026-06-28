#!/usr/bin/env bash
# =============================================================================
#  RetailAI Agent — Project Setup Script
#  Run: bash scripts/setup.sh [--dev | --prod]
# =============================================================================
set -euo pipefail

MODE="${1:---dev}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"

# ── Colors ────────────────────────────────────────────────────────────────────
GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; CYAN="\033[36m"; RESET="\033[0m"
ok()   { echo -e "${GREEN}✓${RESET} $*"; }
info() { echo -e "${CYAN}→${RESET} $*"; }
warn() { echo -e "${YELLOW}⚠${RESET} $*"; }
err()  { echo -e "${RED}✗${RESET} $*"; exit 1; }

echo -e "\n${CYAN}╔══════════════════════════════════╗"
echo    "║   RetailAI Agent Setup            ║"
echo -e "╚══════════════════════════════════╝${RESET}\n"

# ── Check prerequisites ───────────────────────────────────────────────────────
info "Checking prerequisites..."
command -v python3  >/dev/null || err "python3 not found"
command -v node     >/dev/null || err "node not found"
command -v npm      >/dev/null || err "npm not found"
command -v docker   >/dev/null || warn "docker not found — Docker stack unavailable"
ok "Prerequisites OK"

# ── Create .env if missing ────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
    info "Creating .env from .env.example..."
    cp "$ROOT/.env.example" "$ROOT/.env"
    # Generate a secure secret key
    SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' "s/SECRET_KEY=.*/SECRET_KEY=${SECRET}/" "$ROOT/.env"
    else
        sed -i "s/SECRET_KEY=.*/SECRET_KEY=${SECRET}/" "$ROOT/.env"
    fi
    ok ".env created with generated SECRET_KEY"
else
    ok ".env already exists"
fi

# ── Create data directories ───────────────────────────────────────────────────
info "Creating data directories..."
mkdir -p "$ROOT/data/db" "$ROOT/data/reports" "$ROOT/data/models" "$ROOT/data/uploads"
ok "Data directories ready"

# ── Backend Python environment ────────────────────────────────────────────────
info "Setting up Python virtual environment..."
cd "$ROOT/backend"
if [ ! -d ".venv" ]; then
    $PYTHON -m venv .venv
    ok "Virtual environment created"
fi
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
ok "Backend dependencies installed"

# ── Frontend Node dependencies ─────────────────────────────────────────────────
info "Installing frontend dependencies..."
cd "$ROOT/apps/frontend"
npm install --silent
ok "Frontend dependencies installed"

# ── Database migrations ───────────────────────────────────────────────────────
info "Running database migrations..."
cd "$ROOT"
export PYTHONPATH="$ROOT/backend"
alembic -c database/alembic.ini upgrade head 2>/dev/null || {
    warn "Alembic migration failed — backend will auto-create tables on first run"
}

# ── Seed demo data (dev only) ─────────────────────────────────────────────────
if [ "$MODE" = "--dev" ]; then
    info "Seeding demo data..."
    cd "$ROOT"
    $PYTHON scripts/seed-demo.py && ok "Demo data seeded" || warn "Seeding skipped (backend may not be ready yet)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo -e "\n${GREEN}╔══════════════════════════════════════════════╗"
echo    "║  Setup Complete!                              ║"
echo    "╠══════════════════════════════════════════════╣"
echo    "║  Backend:    cd backend && uvicorn main:app   ║"
echo    "║              --reload --port 8000             ║"
echo    "║  Frontend:   cd apps/frontend && npm run dev  ║"
echo    "║  Dashboard:  http://localhost:3000            ║"
echo    "║  API Docs:   http://localhost:8000/api/docs   ║"
echo    "║  Docker:     docker compose -f docker/        ║"
echo    "║              docker-compose.dev.yml up        ║"
echo -e "╚══════════════════════════════════════════════╝${RESET}\n"
