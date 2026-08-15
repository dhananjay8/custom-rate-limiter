# Testing Report

## Summary

| Category | Tests | Status |
|----------|-------|--------|
| Unit Tests (pytest) | 154 | ✅ All Passed |
| HTTP Integration Tests | 39 | ✅ All Passed |
| Coverage | 96% | ✅ Excellent |

## Test Environments

### Podman Container Testing

- **Image**: `rate-limiter-test` (built from `Containerfile.test`)
- **Base**: `python:3.12-slim`
- **No interference** with existing containers (elasticsearch, oracle-db, zookeeper, kafka, redis cluster)

### Storage Backends Tested

- **Memory** (port 5050): All endpoints verified
- **SQLite** (port 5051): All endpoints verified, persistent state confirmed

## Test Categories

### Unit Tests (`tests/unit/`)

| File | Tests | Coverage |
|------|-------|----------|
| `test_algorithms.py` | 53 | Fixed Window, Sliding Window Log, Sliding Window Counter, Token Bucket, Leaky Bucket, GCRA |
| `test_repositories.py` | 22 | Memory + SQLite: counters, timestamps, token buckets, lifecycle |
| `test_auth.py` | 10 | Valid clients, missing/invalid headers, case sensitivity |
| `test_api.py` | 18 | All endpoints, rate limits, headers, error responses |
| `test_config.py` | 8 | Settings validation, client config, algorithm mapping |
| `test_concurrency.py` | 6 | Thread-safety, concurrent limit enforcement |
| `test_edge_cases.py` | 14 | Boundaries, high volume, window transitions, storage switching |
| `test_factory.py` | 9 | Algorithm + Repository factory pattern (all 6 algorithms) |

### Integration Tests (`tests/integration/`)

| File | Tests | Coverage |
|------|-------|----------|
| `test_full_flow.py` | 16 | Full lifecycle, memory/SQLite, algorithm switching |

### HTTP Integration Tests (`scripts/test_api_http.sh`)

| Category | Tests |
|----------|-------|
| Health Endpoint | 4 |
| Authentication | 4 |
| Success Responses | 3 |
| Rate Limiting /foo | 3 |
| Rate Limiting /bar | 2 |
| Client Isolation | 2 |
| Endpoint Isolation | 1 |
| Rate Limit Headers | 4 |
| 429 Headers | 1 |
| Metrics | 5 |
| Admin Config | 5 |
| Admin Reset | 2 |
| Error Handling | 3 |

## Bugs Found & Fixed

1. **Health endpoint re-reading settings from env**: The `/health` and `/admin/config` routes were calling `get_settings()` which reads from environment variables, not the settings used to create the app. Fixed by storing settings in `app.config["SETTINGS"]` and using `current_app.config["SETTINGS"]` in routes.

2. **Auth test expectation mismatch**: Test expected `"unknown_client"` for `"Bearer "` (trailing space), but the authenticator correctly identifies it as `"empty_client_id"` since the token trims to empty string. Fixed test to match correct behavior.

## Performance Observations

- 154 pytest tests complete in **0.72 seconds** inside the container
- Rate limiting decisions are sub-millisecond for in-memory storage
- SQLite with WAL mode handles the test load without issues

## Podman Commands Used

```bash
# Build test image
podman build -t rate-limiter-test -f Containerfile.test .

# Run pytest suite
podman run --rm --name rate-limiter-tests rate-limiter-test

# Run API server (memory backend)
podman run -d --rm --name rate-limiter-api -p 5050:5000 \
  -e RATE_LIMIT_STORAGE=memory rate-limiter-test python run.py

# Run API server (SQLite backend)
podman run -d --rm --name rate-limiter-api-sqlite -p 5051:5000 \
  -e RATE_LIMIT_STORAGE=sqlite -e SQLITE_DB_PATH=/tmp/test.db \
  rate-limiter-test python run.py

# Cleanup
podman stop rate-limiter-api
podman stop rate-limiter-api-sqlite
```
