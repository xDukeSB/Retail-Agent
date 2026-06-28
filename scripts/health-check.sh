#!/usr/bin/env bash
# Health-check script for all services
set -euo pipefail
GREEN="\033[32m"; RED="\033[31m"; RESET="\033[0m"
pass() { echo -e "${GREEN}✓${RESET} $*"; }
fail() { echo -e "${RED}✗${RESET} $*"; }

BACKEND="${BACKEND_URL:-http://localhost:8000}"
FRONTEND="${FRONTEND_URL:-http://localhost:3000}"

echo "RetailAI Agent — Service Health Check"
echo "======================================"

# Backend liveness
curl -sf "$BACKEND/api/v1/health/live" > /dev/null \
    && pass "Backend alive ($BACKEND)" \
    || fail "Backend unreachable ($BACKEND)"

# Backend readiness (DB)
curl -sf "$BACKEND/api/v1/health/ready" > /dev/null \
    && pass "Backend ready (DB connected)" \
    || fail "Backend not ready (DB may be down)"

# Full health
HEALTH=$(curl -sf "$BACKEND/api/v1/health/" 2>/dev/null || echo '{"status":"down"}')
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','unknown'))")
[ "$STATUS" = "ok" ] \
    && pass "Backend health: $STATUS" \
    || fail "Backend health: $STATUS"

# Frontend
curl -sf "$FRONTEND" > /dev/null \
    && pass "Frontend reachable ($FRONTEND)" \
    || fail "Frontend unreachable ($FRONTEND)"

echo "======================================"
