# Custom Rate Limiter

A **production-grade rate limiting framework** built with Python and Flask, featuring 6 industry-standard algorithms, 3 storage backends, adaptive limiting, circuit breaker resilience, and OpenAPI documentation.

## Quick Start

### Prerequisites

- Python 3.12+
- pip or Poetry
- Docker/Podman (optional, for containerized runs)

### Installation

```bash
cd custom-rate-limiter

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt

# Copy environment config
cp .env.example .env
```

### Run Locally

```bash
# Development (auto-reload)
python run.py

# Production (Gunicorn)
gunicorn --bind 0.0.0.0:5000 --workers 4 run:app
```

### Run with Docker Compose (Redis backend)

```bash
docker-compose up --build
```

This starts the app + Redis. The rate limiter uses Redis for distributed state.

### Run with Podman (Memory backend, testing)

```bash
# Build test image
podman build -t rate-limiter-test -f Containerfile.test .

# Run all 202 tests
podman run --rm rate-limiter-test

# Run app (memory backend)
podman build -t rate-limiter -f Dockerfile .
podman run --rm -p 5050:5000 -e RATE_LIMIT_STORAGE=memory rate-limiter
```

## Testing the API

```bash
# Health check
curl http://localhost:5000/health

# Successful request (not throttled)
curl -X GET http://localhost:5000/foo -H "Authorization: Bearer client-basic"
# → 200 {"success": true}

# Weighted request (consumes 3 units of quota)
curl -X GET http://localhost:5000/foo \
  -H "Authorization: Bearer client-basic" \
  -H "X-Request-Weight: 3"

# After exhausting limit (throttled)
curl -X GET http://localhost:5000/foo -H "Authorization: Bearer client-basic"
# → 429 {"error": "rate limit exceeded"}

# Different client with higher limits
curl -X GET http://localhost:5000/foo -H "Authorization: Bearer client-premium"
# → 200 {"success": true}

# Bar endpoint (different algorithm)
curl -X GET http://localhost:5000/bar -H "Authorization: Bearer client-basic"

# Swagger UI
open http://localhost:5000/docs
```

## API Endpoints

### Rate Limited

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/foo` | GET | `Bearer <client-id>` | Rate limited (Fixed Window by default) |
| `/foo` | POST | `Bearer <client-id>` | Write operation (cost = `FOO_POST_WEIGHT`, default 5) |
| `/bar` | GET | `Bearer <client-id>` | Rate limited (Sliding Window Log by default) |
| `/bar` | POST | `Bearer <client-id>` | Write operation (cost = `BAR_POST_WEIGHT`, default 3) |

### Monitoring & Admin

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (storage, algorithms, circuit breaker) |
| `/metrics` | GET | Request metrics per client/endpoint |
| `/metrics/prometheus` | GET | Prometheus exposition format for scraping |
| `/admin/config` | GET | Current configuration (see `ADMIN_TOKEN` note below) |
| `/admin/dry-run` | GET | Non-invasive diagnostics (config + storage + feature status) |
| `/admin/reset` | POST | Reset all rate limit state |
| `/admin/config` | POST | Update and persist configuration (when dynamic config enabled) |
| `/admin/adaptive` | GET | Adaptive rate limiter status |
| `/admin/circuit-breaker` | GET | Circuit breaker state |
| `/admin/quotas` | GET | Quota pool usage |
| `/admin/coalescing` | GET | Request coalescing stats |
| `/admin/weights` | GET | Weighted operation config |
| `/docs` | GET | Swagger UI |
| `/openapi.json` | GET | OpenAPI 3.1 spec |

## Configuration

All configuration is via environment variables (see `.env.example`):

```env
RATE_LIMIT_STORAGE=memory          # memory | sqlite | redis
FOO_ALGORITHM=fixed_window         # fixed_window | sliding_window_log | sliding_window_counter | token_bucket | leaky_bucket | gcra
BAR_ALGORITHM=sliding_window_log

# Per-client limits
CLIENT_BASIC_FOO_LIMIT=10
CLIENT_BASIC_FOO_WINDOW=60
CLIENT_PREMIUM_FOO_LIMIT=100
CLIENT_PREMIUM_FOO_WINDOW=60

# Redis (when using redis backend)
REDIS_URL=redis://localhost:6379/0

# Advanced features
CIRCUIT_BREAKER_ENABLED=true
ADAPTIVE_ENABLED=true
COALESCING_ENABLED=true
FOO_GET_WEIGHT=1
FOO_POST_WEIGHT=5
```

### Write operations

`POST /foo` and `POST /bar` are rate-limited write endpoints. They consume
`FOO_POST_WEIGHT` (default `5`) and `BAR_POST_WEIGHT` (default `3`) units per
request, configurable via `.env` or environment variables.

```bash
curl -X POST http://localhost:5000/foo \
  -H "Authorization: Bearer client-basic" \
  -H "X-Request-Weight: 2"
# → 200 {"success": true}
```

### Shadow mode

When `SHADOW_MODE_ENABLED=true`, you can preview rate limit decisions without
blocking traffic by passing `X-Shadow-Mode: true` on any rate-limited
endpoint. The response returns the decision and remaining quota but does not
mutate the live rate limit state.

```bash
curl -X GET http://localhost:5000/foo \
  -H "Authorization: Bearer client-basic" \
  -H "X-Shadow-Mode: true"
# → 200 {"success": true, "shadow": true, "decision": "allowed", ...}
```

### Optional request weight override

For authenticated rate-limited endpoints (`/foo`, `/bar`), you can pass
`X-Request-Weight: <int>` to override the default endpoint/method weight
for that request.

- Invalid header values return `400`.
- Minimum accepted value is `1`.

### Dynamic configuration (runtime, persisted)

When `DYNAMIC_CONFIG_ENABLED=true`, you can update client limits, endpoint
algorithms, and method weights at runtime via `POST /admin/config`. The update
is persisted to `DYNAMIC_CONFIG_PATH` and re-applied on the next startup.

```bash
curl -X POST http://localhost:5000/admin/config \
  -H "Content-Type: application/json" \
  -d '{
    "clients": {
      "client-basic": {
        "foo": {"limit": 5, "window": 60}
      }
    },
    "algorithms": {
      "foo": "token_bucket"
    },
    "weights": {
      "foo": {"default_cost": 1, "method_costs": {"GET": 1, "POST": 2}}
    }
  }'
```

### Admin route authentication

If `ADMIN_TOKEN` is set, all `/admin/*` endpoints require
`Authorization: Bearer <admin-token>`. When `ADMIN_TOKEN` is not set,
admin routes remain public (development convenience).

### Switching Algorithms (zero code change)

```bash
# Change /foo from Fixed Window to GCRA
export FOO_ALGORITHM=gcra
# Restart app
```

## Client Configuration

| Client | Endpoint | Limit | Window |
|--------|----------|-------|--------|
| client-basic | /foo | 10 req | 60s |
| client-basic | /bar | 20 req | 60s |
| client-premium | /foo | 100 req | 60s |
| client-premium | /bar | 250 req | 60s |

## Running Tests

```bash
# Logical dry-run diagnostics (no external infra mutation)
python scripts/dry_run.py

# All tests (202 tests, 87% coverage)
pytest

# With coverage report
pytest --cov=app --cov-report=html

# Specific categories
pytest tests/unit/test_algorithms.py
pytest tests/unit/test_circuit_breaker.py
pytest tests/unit/test_advanced_features.py
pytest tests/integration/
```

## Benchmark

```bash
python scripts/benchmark.py
```

## Project Structure

```
custom-rate-limiter/
├── app/
│   ├── algorithms/           # 6 rate limiting algorithms (Strategy pattern)
│   ├── api/                  # Routes, middleware, OpenAPI spec
│   ├── auth/                 # Bearer token authentication
│   ├── config/               # Pydantic Settings (env-driven)
│   ├── repositories/         # Storage backends (Memory, SQLite, Redis)
│   ├── resilience/           # Circuit breaker pattern
│   ├── services/             # Rate limiter, adaptive, weighted, coalescing, quota
│   └── factory.py            # Application factory (DI wiring)
├── tests/                    # 202 tests (unit, integration, concurrency)
├── scripts/                  # Benchmark, HTTP test scripts
├── infra/azure/              # Azure deployment (Bicep, scripts)
├── Dockerfile                # Production container
├── Containerfile.test        # Test container
├── docker-compose.yml        # App + Redis stack
└── .env.example              # All configuration options
```

## Further Documentation

- **[crl-architecture.md](crl-architecture.md)** — In-depth architecture, algorithms, design patterns
- **[infra/azure/README.md](infra/azure/README.md)** — Azure deployment guide
