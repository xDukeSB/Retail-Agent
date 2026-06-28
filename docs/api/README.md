# RetailAI Agent — API Reference (v1)

Base URL: `http://localhost:8000/api/v1`
Interactive docs: `http://localhost:8000/api/docs`

---

## Authentication

All protected endpoints require:
```
Authorization: Bearer <access_token>
```

### `POST /auth/login`
Obtain JWT access + refresh tokens.

**Request:**
```json
{ "email": "admin@retailai.local", "password": "YourPassword" }
```
**Response `200`:**
```json
{
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800
}
```

### `POST /auth/refresh`
Exchange a refresh token for a new access token.

### `GET /auth/me`
Returns the authenticated user's profile. Requires any role.

### `POST /auth/change-password`
Change own password. Requires current password.

### `POST /auth/logout`
Stateless — client discards the token.

---

## Health

### `GET /health/`
Full system health (DB latency, disk, memory).

```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "development",
  "uptime_seconds": 3600.5,
  "timestamp": "2024-01-15T10:30:00Z",
  "components": {
    "database": { "status": "ok", "latency_ms": 1.2, "detail": "sqlite" },
    "disk":     { "status": "ok", "detail": "42.3 GB free" },
    "memory":   { "status": "ok", "detail": "34.2% used" }
  }
}
```

### `GET /health/ready` — Readiness probe (Docker/K8s)
### `GET /health/live` — Liveness probe (Docker/K8s)

---

## Users *(Admin/Manager only)*

### `GET /users/` — List users (paginated)
Query params: `page`, `page_size`, `role`, `is_active`

### `POST /users/` — Create user *(Admin/Manager)*
```json
{
  "email": "manager@store.local",
  "full_name": "Jane Smith",
  "password": "SecurePass123!",
  "role": "manager"
}
```

### `GET /users/{id}` — Get user by ID
### `PATCH /users/{id}` — Update user
### `DELETE /users/{id}` — Delete user *(Admin only)*

---

## Error Format

All errors follow RFC 7807:
```json
{
  "detail": "Human-readable error message"
}
```

| Status | Meaning |
|--------|---------|
| 400 | Bad request / validation error |
| 401 | Missing or invalid token |
| 403 | Authenticated but insufficient role |
| 404 | Resource not found |
| 409 | Conflict (e.g. duplicate email) |
| 422 | Request body validation failed |
| 500 | Internal server error |

---

## Response Headers

Every response includes:
- `X-Correlation-ID` — Unique request ID for log tracing
- `X-Response-Time` — Server processing time in ms
