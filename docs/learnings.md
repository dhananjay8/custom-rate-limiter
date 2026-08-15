# Learnings & Future Reference

## Algorithm Comparison (Industry Context)

| Algorithm | Used By | Key Trait | Storage Per Key |
|-----------|---------|-----------|-----------------|
| Fixed Window | Simple APIs | O(1), boundary burst risk | 1 counter + timestamp |
| Sliding Window Log | Precision APIs | Exact, O(n) memory | N timestamps |
| Sliding Window Counter | Balanced APIs | Approximation, O(1) | 2 counters |
| Token Bucket | AWS, NGINX, Envoy, Kong | Burst-friendly | 1 float + timestamp |
| Leaky Bucket | NGINX (limit_req), Cisco | Constant drain, no burst | 1 float + timestamp |
| GCRA | Stripe, Shopify, GitHub | Single CAS, atomic-friendly | 1 timestamp only |

### When to use which?
- **Fixed Window**: Simple, low traffic, where boundary burst is acceptable
- **Sliding Window Log**: Need exact counts, moderate traffic
- **Token Bucket**: Need burst tolerance (most common in cloud APIs)
- **Leaky Bucket**: Need traffic shaping with strict constant rate
- **GCRA**: Need distributed rate limiting (Redis), high-scale, atomic operations

## Architecture Decisions

### 1. Strategy Pattern for Algorithms
- Each algorithm implements `RateLimitAlgorithm.allow_request()`
- Switching algorithms is purely configuration-driven (`FOO_ALGORITHM=token_bucket`)
- No code changes needed to switch algorithms at runtime

### 2. Repository Pattern for Storage
- `RateLimitRepository` abstraction hides implementation details
- Business logic never knows if it's using Memory or SQLite
- Adding Redis would require implementing the same interface

### 3. Factory Pattern for Object Creation
- `AlgorithmFactory.create(AlgorithmType)` → returns the right algorithm
- `RepositoryFactory.create(Settings)` → returns the right storage backend
- Clean separation of construction from usage

### 4. Dependency Injection via App Factory
- `create_app(settings)` wires everything together
- Makes testing trivial: inject test settings to control behavior
- No global state, no singletons

## Key Technical Learnings

### Pydantic Settings
- Use `ConfigDict` instead of inner `class Config` (deprecation warning in Pydantic v2)
- Environment variables map directly to fields (case-insensitive)
- Settings can be overridden in tests via constructor args

### Flask Application Context
- Store app-level config in `app.config` dict
- Use `current_app.config["KEY"]` inside route handlers
- Never import settings directly in routes (breaks testability)

### Thread Safety
- `threading.Lock()` is sufficient for in-memory structures
- SQLite WAL mode allows concurrent reads, but writes still need locking
- Rate limit algorithms must be thread-safe since Flask with Gunicorn uses threads

### Podman vs Docker
- Commands are nearly identical (`podman build`, `podman run`)
- No daemon required (daemonless architecture)
- Network inside build steps may be restricted on macOS (apt-get fails, pip works)
- Use `--rm` flag to auto-cleanup test containers

### Testing Strategy
- **Unit tests**: Test each algorithm/repository in isolation
- **Integration tests**: Test full request lifecycle with Flask test client
- **HTTP tests**: Test against running container with `curl`
- **Concurrency tests**: Use `threading.Thread` to verify thread-safety
- **Edge cases**: Boundary conditions, window transitions, high volume

## Common Pitfalls

1. **Don't call `get_settings()` in routes** → It re-reads from env, ignoring test overrides
2. **SQLite `:memory:` is per-connection** → Thread-local connections won't share state
3. **Fixed window boundary** → Requests at window edge can allow 2x burst (known trade-off)
4. **Token bucket floating point** → Use `>= 1.0` not `> 0` for token check
5. **Sliding window log** → Check count BEFORE adding timestamp (to avoid off-by-one)

## How to Extend

### Add a new algorithm (e.g., Leaky Bucket)
1. Create `app/algorithms/leaky_bucket.py` implementing `RateLimitAlgorithm`
2. Add to `AlgorithmType` enum in `settings.py`
3. Register in `AlgorithmFactory._algorithms`
4. Set `FOO_ALGORITHM=leaky_bucket` in `.env`

### Add Redis storage
1. Create `app/repositories/redis_repository.py` implementing `RateLimitRepository`
2. Add `REDIS` to `StorageBackend` enum
3. Add creation logic to `RepositoryFactory.create()`
4. Set `RATE_LIMIT_STORAGE=redis` in `.env`

### Add a new client
1. Add env vars: `CLIENT_NEWCLIENT_FOO_LIMIT`, `CLIENT_NEWCLIENT_FOO_WINDOW`, etc.
2. Add fields to `Settings` class
3. Add to `get_clients()` method
4. Restart application

## File Quick Reference

| Need to... | Look at... |
|------------|------------|
| Add algorithm | `app/algorithms/base.py` → implement interface |
| Add storage | `app/repositories/base.py` → implement interface |
| Change limits | `.env` file |
| Add endpoint | `app/api/routes.py` + `settings.py` algorithm mapping |
| Run tests | `podman run --rm rate-limiter-test` |
| Run API | `podman run -d -p 5050:5000 rate-limiter-test python run.py` |
| HTTP tests | `bash scripts/test_api_http.sh` |
