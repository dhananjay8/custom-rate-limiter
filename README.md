# Custom Rate Limiter

A **production-grade rate limiting framework** built with Python and Flask. Demonstrates clean architecture, extensibility, and production readiness with pluggable algorithms and storage backends.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Flask Application                        │
├──────────────┬──────────────┬────────────────────────────────┤
│  Middleware  │    Routes    │        Error Handlers           │
│  (Auth+RL)   │ /foo /bar    │                                │
├──────────────┴──────────────┴────────────────────────────────┤
│                   Rate Limiter Service                        │
├──────────────────────────────────────────────────────────────┤
│                  Algorithm Layer (Strategy)                   │
│  ┌────────────┐ ┌──────────────┐ ┌───────────────────────┐  │
│  │Fixed Window│ │Sliding Window│ │Token Bucket            │  │
│  │Counter     │ │Log           │ │                        │  │
│  └────────────┘ └──────────────┘ └───────────────────────┘  │
│  ┌────────────────────────┐                                  │
│  │Sliding Window Counter  │                                  │
│  └────────────────────────┘                                  │
├──────────────────────────────────────────────────────────────┤
│                Repository Layer (Abstraction)                 │
│  ┌──────────────────┐  ┌───────────────────────────────┐    │
│  │MemoryRepository   │  │SQLiteRepository                │    │
│  └──────────────────┘  └───────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

## Features

- **4 Rate Limiting Algorithms**: Fixed Window, Sliding Window Log, Sliding Window Counter, Token Bucket
- **2 Storage Backends**: In-Memory (thread-safe), SQLite (WAL mode)
- **Configuration-driven**: Switch algorithms or storage via environment variables
- **Per-client, per-endpoint limits**: Different clients get different quotas
- **Structured JSON logging**: Every decision is logged with context
- **Metrics & monitoring**: Built-in `/health`, `/metrics`, `/admin/config`
- **Thread-safe**: Proper locking for concurrent access
- **Comprehensive tests**: Unit, integration, concurrency, edge cases

## Design Patterns

| Pattern | Where |
|---------|-------|
| Strategy | Algorithm selection |
| Factory | Algorithm & Repository creation |
| Repository | Storage abstraction |
| Dependency Injection | Application wiring |
| Chain of Responsibility | Auth → Rate Limit → Handler |
| Template Method | Common algorithm interface |

## Quick Start

### Prerequisites

- Python 3.12+
- pip or Poetry

### Installation

```bash
# Clone and enter project
cd custom-rate-limiter

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt
```

### Running the Application

```bash
# Development
python run.py

# Production (Gunicorn)
gunicorn --bind 0.0.0.0:5000 --workers 4 run:app
```

### Docker

```bash
docker-compose up --build
```

## API Endpoints

### Rate Limited

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/foo` | GET | Bearer | Rate limited (Fixed Window by default) |
| `/bar` | GET | Bearer | Rate limited (Sliding Window Log by default) |

### Monitoring

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/health` | GET | None | Health check |
| `/metrics` | GET | None | Request metrics |
| `/admin/config` | GET | None | Current configuration |
| `/admin/reset` | POST | None | Reset all state |

## Configuration

All configuration is environment-driven:

```env
RATE_LIMIT_STORAGE=memory          # memory | sqlite
FOO_ALGORITHM=fixed_window         # fixed_window | sliding_window_log | token_bucket | sliding_window_counter
BAR_ALGORITHM=sliding_window_log

CLIENT_BASIC_FOO_LIMIT=10
CLIENT_BASIC_FOO_WINDOW=60
CLIENT_PREMIUM_FOO_LIMIT=100
CLIENT_PREMIUM_FOO_WINDOW=60
```

### Switching Algorithms

To switch `/foo` from Fixed Window to Token Bucket:

```env
FOO_ALGORITHM=token_bucket
```

No code changes required. Restart the application.

## Client Configuration

| Client | Endpoint | Limit | Window |
|--------|----------|-------|--------|
| client-basic | /foo | 10 req | 60s |
| client-basic | /bar | 20 req | 60s |
| client-premium | /foo | 100 req | 60s |
| client-premium | /bar | 250 req | 60s |

## Algorithms

### Fixed Window Counter
- **Complexity**: O(1) time and space
- **Trade-off**: Can allow 2x burst at window boundaries
- **Best for**: Simple, low-overhead rate limiting

### Sliding Window Log
- **Complexity**: O(n) space, O(log n) time
- **Trade-off**: Higher memory, but precise
- **Best for**: Accurate rate limiting without boundary issues

### Sliding Window Counter
- **Complexity**: O(1) time and space
- **Trade-off**: Approximation of sliding window
- **Best for**: Balance between accuracy and efficiency

### Token Bucket
- **Complexity**: O(1) time and space
- **Trade-off**: Allows controlled bursts
- **Best for**: APIs that need to allow burst traffic (AWS, NGINX, Envoy)

## Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Specific test categories
pytest tests/unit/test_algorithms.py
pytest tests/unit/test_api.py
pytest tests/unit/test_concurrency.py
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
│   ├── algorithms/          # Rate limiting algorithms (Strategy)
│   │   ├── base.py          # Abstract base class
│   │   ├── fixed_window.py
│   │   ├── sliding_window_log.py
│   │   ├── sliding_window_counter.py
│   │   ├── token_bucket.py
│   │   └── factory.py       # Algorithm factory
│   ├── api/
│   │   ├── routes.py        # API endpoint definitions
│   │   └── middleware.py    # Auth + rate limit middleware
│   ├── auth/
│   │   └── bearer_auth.py   # Bearer token authentication
│   ├── config/
│   │   └── settings.py      # Pydantic Settings configuration
│   ├── exceptions/          # Custom exception hierarchy
│   ├── logging/
│   │   └── structured.py    # JSON structured logging
│   ├── repositories/        # Storage backends (Repository)
│   │   ├── base.py          # Abstract repository interface
│   │   ├── memory_repository.py
│   │   ├── sqlite_repository.py
│   │   └── factory.py       # Repository factory
│   ├── services/
│   │   ├── rate_limiter.py  # Core business logic + metrics
│   │   └── metrics.py       # Application metrics
│   └── factory.py           # Application factory (DI wiring)
├── tests/
│   ├── unit/
│   │   ├── test_algorithms.py
│   │   ├── test_repositories.py
│   │   ├── test_auth.py
│   │   ├── test_api.py
│   │   ├── test_config.py
│   │   ├── test_concurrency.py
│   │   ├── test_edge_cases.py
│   │   └── test_factory.py
│   └── integration/
│       └── test_full_flow.py
├── scripts/
│   └── benchmark.py
├── docs/
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Design Decisions & Trade-offs

1. **In-process rate limiting**: Simple, no external dependencies. Trade-off: not distributed.
2. **Thread locks**: Correct, simple. Trade-off: contention under very high load.
3. **SQLite with WAL**: Good concurrent read perf. Trade-off: single-writer bottleneck.
4. **Pydantic Settings**: Type-safe config. Trade-off: slightly more complex than raw env vars.
5. **Factory pattern**: Easy to extend. Trade-off: more indirection.

## Future Improvements

- **Redis Repository**: For distributed rate limiting across multiple pods
- **Lua Scripts**: Atomic operations in Redis
- **Prometheus Metrics**: Production monitoring integration
- **OpenAPI/Swagger**: Auto-generated API docs
- **Distributed rate limiting**: Consistent hashing, Redis Cluster
- **Circuit breaker**: For storage backend failures
- **GCRA Algorithm**: Telecom-grade rate limiting
- **Kubernetes deployment**: Horizontal scaling with shared state
- **API Gateway integration**: Envoy, Kong, or Istio

## Interview Discussion Points

- **How would you replace SQLite with Redis?** → Implement `RedisRepository` with same interface
- **How would you scale across pods?** → Redis as shared state, or consistent hashing
- **How would you implement distributed rate limiting?** → Redis Lua scripts for atomicity
- **How would you add Token Bucket?** → Already implemented, just change config
- **How would you integrate with an API Gateway?** → Adapter pattern, same algorithm layer
