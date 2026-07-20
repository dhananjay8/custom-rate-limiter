# Architecture & Algorithms Deep Dive

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Flask Application                              │
├───────────────┬───────────────┬───────────────────────────────────────┤
│  Middleware   │    Routes     │          Error Handlers                │
│  Auth + RL    │  /foo  /bar   │  404, 405, 429, 500                   │
├───────────────┴───────────────┴───────────────────────────────────────┤
│                    Rate Limiter Service                                │
│  ┌────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐  │
│  │ Adaptive   │ │ Weighted     │ │ Coalescing   │ │ Quota        │  │
│  │ Limiting   │ │ Operations   │ │ (Dedup)      │ │ Sharing      │  │
│  └────────────┘ └──────────────┘ └──────────────┘ └──────────────┘  │
├──────────────────────────────────────────────────────────────────────┤
│                    Algorithm Layer (Strategy Pattern)                  │
│  ┌────────────┐ ┌───────────────┐ ┌────────────────────────────┐    │
│  │Fixed Window│ │Sliding Window │ │Sliding Window Counter      │    │
│  │Counter     │ │Log            │ │                            │    │
│  └────────────┘ └───────────────┘ └────────────────────────────┘    │
│  ┌────────────┐ ┌───────────────┐ ┌────────────────────────────┐    │
│  │Token Bucket│ │Leaky Bucket   │ │GCRA (Generic Cell Rate)    │    │
│  └────────────┘ └───────────────┘ └────────────────────────────┘    │
├──────────────────────────────────────────────────────────────────────┤
│                  Repository Layer (Repository Pattern)                 │
│  ┌────────────────┐ ┌──────────────┐ ┌──────────────────────────┐   │
│  │ Memory         │ │ SQLite (WAL) │ │ Redis (Lua Scripts)      │   │
│  └────────────────┘ └──────────────┘ └──────────────────────────┘   │
├──────────────────────────────────────────────────────────────────────┤
│                   Resilience Layer (Circuit Breaker)                   │
│  CLOSED → OPEN → HALF_OPEN → CLOSED (fail-open strategy)            │
└──────────────────────────────────────────────────────────────────────┘
```

## Request Flow

```
HTTP Request
    │
    ▼
┌─────────────────┐
│ before_request  │ → Generate X-Request-ID, start timer
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│ @require_auth   │ → Extract Bearer token → validate client ID
│                 │   ✗ → 401/403
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│@require_rate    │ → check_rate_limit(client, endpoint, method)
│  _limit         │   │
│                 │   ├─ 1. Check coalescing cache (dedup)
│                 │   ├─ 2. Get operation weight (GET=1, POST=5)
│                 │   ├─ 3. Check quota pool (shared limits)
│                 │   ├─ 4. Apply adaptive multiplier (load-based)
│                 │   ├─ 5. Run algorithm (via repository)
│                 │   ├─ 6. Record metrics + cache result
│                 │   │
│                 │   ├─ ALLOWED → set X-RateLimit headers → continue
│                 │   └─ REJECTED → 429 + Retry-After header
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│ Route Handler   │ → return {"success": true}, 200
└────────┬────────┘
         │
    ▼
┌─────────────────┐
│ after_request   │ → Set X-RateLimit-Limit, X-RateLimit-Remaining,
│                 │   X-RateLimit-Reset, X-Request-ID headers
└─────────────────┘
```

## Design Patterns

| Pattern | Where | Why |
|---------|-------|-----|
| **Strategy** | `app/algorithms/` | Each algorithm is interchangeable at runtime |
| **Factory** | `AlgorithmFactory`, `RepositoryFactory` | Decouple creation from usage |
| **Repository** | `app/repositories/` | Abstract storage, swap backends without code changes |
| **Dependency Injection** | `app/factory.py` | Wire components in one place, testable |
| **Chain of Responsibility** | Middleware stack | Auth → Rate Limit → Handler, each can short-circuit |
| **Template Method** | `RateLimitAlgorithm.allow_request()` | Common interface, different implementations |
| **Decorator** | Flask `@wraps` middleware | Transparently wrap route handlers |
| **Circuit Breaker** | `app/resilience/` | Protect against storage failures |
| **Adapter** | Redis sorted sets for timestamp logs | Same interface, different data structure |

## Algorithms In-Depth

### 1. Fixed Window Counter

```
Time:  |────── Window 1 ──────|────── Window 2 ──────|
Reqs:  ████████░░              ████░░░░░░░░░░░░░░░░░░
Count: 8/10                    4/10
```

**How it works:**
- Divide time into fixed windows (e.g., 60s)
- Increment counter for each request within the window
- Reset counter at window boundary

**Implementation:** Single counter with TTL. Key = `{client}:{endpoint}:{window_start}`.

**Boundary problem:** At window edges, a client can get 2x burst:
- 10 requests at T=59s (end of window 1)
- 10 requests at T=60s (start of window 2)
- = 20 requests in 1 second span

**Storage:** 1 integer counter + 1 timestamp = O(1)

---

### 2. Sliding Window Log

```
Time:    [──────────── 60s window ────────────]
Stamps:  │ t1 │ t2 │ t3 │ ... │ tN │
         ▲────── count all in window ────────▲
```

**How it works:**
- Store exact timestamp of every request
- Count timestamps within `[now - window, now]`
- Periodically evict expired entries

**Implementation:** Sorted list of timestamps per key. Count = len(timestamps in window).

**Precision:** Exact — no boundary problem. But O(n) space per key.

**Storage:** N timestamps per key (where N = number of requests in window)

---

### 3. Sliding Window Counter

```
Window:    [── prev window ──]──[── curr window ──]
                              ▲
                              now (40% into current)

Count = prev_count * (1 - 0.4) + curr_count
      = prev_count * 0.6 + curr_count
```

**How it works:**
- Combines Fixed Window efficiency with Sliding Window accuracy
- Weighted average of current + previous window counts
- Weight based on position within current window

**Implementation:** Store counters for current and previous windows. Weighted sum gives approximate sliding window count.

**Approximation error:** Up to ±12% in worst case (empirically proven acceptable).

**Storage:** 2 counters + 2 timestamps = O(1)

---

### 4. Token Bucket

```
Bucket:   [●●●●●●●○○○]  (7/10 tokens)
           ▲ refill rate: 1 token per 6s (10 tokens / 60s window)

Request arrives:
  tokens > 0? → consume 1 token → ALLOW
  tokens = 0? → REJECT, retry when bucket refills
```

**How it works:**
- Bucket has capacity = limit (e.g., 10)
- Tokens refill at rate = limit/window (e.g., 10/60 = 0.167/s)
- Each request consumes 1 token (or more for weighted)
- Allows burst up to bucket capacity

**Implementation:** Store (tokens, last_refill_time). On each request:
1. Calculate elapsed time since last refill
2. Add tokens: `tokens += elapsed * refill_rate`
3. Cap at max: `tokens = min(tokens, limit)`
4. Try to consume: if tokens >= 1, allow

**Key property:** Allows controlled bursts (unlike Fixed Window which resets entirely).

**Storage:** 1 float (tokens) + 1 timestamp (last_refill) = O(1)

---

### 5. Leaky Bucket

```
     ┌─── Incoming requests
     ▼
╔════════════╗
║  ████████  ║  ← bucket (queue)
║  ████████  ║    capacity = max_limit
║            ║
╚════╤═══════╝
     │  ← constant drain rate (limit/window per second)
     ▼
  Processed
```

**How it works:**
- Requests fill the bucket (queue)
- Bucket drains at a constant rate
- If bucket is full → reject
- Smooths out bursts (constant output rate)

**Implementation:** Track `water_level` (current fill). On each request:
1. Drain: `water_level -= elapsed * drain_rate`
2. Clamp: `water_level = max(0, water_level)`
3. Check: if `water_level + 1 > capacity` → reject
4. Add: `water_level += 1`

**Key property:** No bursts allowed — constant drain enforces even spacing.

**Used by:** NGINX `limit_req`, Cisco IOS traffic shaping, ITU-T I.371

**Storage:** 1 float (water_level) + 1 timestamp = O(1)

---

### 6. GCRA (Generic Cell Rate Algorithm)

```
TAT (Theoretical Arrival Time):
  ────────────────────────────────────▶ time
       │        │        │        │
       t1       t2       t3       t4  ← expected arrival times (emission_interval apart)
                              ▲
                              │ actual request arrives here
                              │
  if actual_time >= TAT - tolerance → ALLOW, update TAT
  else → REJECT (arrived too early)
```

**How it works:**
- Single value per key: TAT (Theoretical Arrival Time)
- `emission_interval` = window / limit (time between expected requests)
- `tolerance` = window (burst window)
- On request:
  1. `new_tat = max(now, tat) + emission_interval`
  2. `allow_at = new_tat - tolerance`
  3. If `now >= allow_at` → ALLOW, set TAT = new_tat
  4. Else → REJECT

**Key property:** 
- Single CAS operation (compare-and-swap) — perfect for Redis `EVAL`
- Mathematically equivalent to Token Bucket but more memory-efficient
- Only stores 1 float (TAT) per key

**Used by:** Stripe, Shopify, GitHub, ATM networks (ITU-T I.371)

**Storage:** 1 timestamp (TAT) = O(1) — most memory-efficient

---

## Algorithm Comparison

| Algorithm | Time | Space/Key | Burst | Precision | Atomic | Best For |
|-----------|------|-----------|-------|-----------|--------|----------|
| Fixed Window | O(1) | 1 counter | 2x at boundary | Low | Yes | Simple APIs |
| Sliding Log | O(n) | N timestamps | None | Exact | No | Precision APIs |
| Sliding Counter | O(1) | 2 counters | Minimal | ~88% | Yes | Balanced APIs |
| Token Bucket | O(1) | 1 float+ts | Controlled | High | Yes | AWS/NGINX/Envoy |
| Leaky Bucket | O(1) | 1 float+ts | None | High | Yes | Traffic shaping |
| GCRA | O(1) | 1 timestamp | Controlled | High | CAS | Distributed/Redis |

## Storage Backends

### Memory Repository
- **Thread-safe** via `threading.Lock`
- **Best for:** Single-process, development, testing
- **Trade-off:** Lost on restart, not shared across processes

### SQLite Repository
- **WAL mode** for concurrent reads
- **Persistent** across restarts
- **Best for:** Single-node production, moderate load
- **Trade-off:** Single-writer bottleneck, not distributed

### Redis Repository
- **Lua scripts** for atomic increment-with-TTL
- **Sorted sets** for timestamp logs (O(log N) range queries)
- **Hash fields** for token bucket state
- **Connection pooling** for performance
- **Best for:** Distributed, multi-pod, high-scale
- **Trade-off:** External dependency, network latency

## Advanced Features

### Circuit Breaker (Resilience)
- **States:** CLOSED → OPEN → HALF_OPEN → CLOSED
- **Fail-open strategy:** When storage is down, ALLOW all requests (don't punish users for infra failure)
- **Configurable:** failure_threshold=5, recovery_timeout=30s

### Adaptive Rate Limiting
- **Monitors:** CPU%, memory%, average response latency, active requests
- **Adjusts:** Multiplier applied to base limits (0.4x–1.5x)
- **Load levels:** LOW (relax 20%) → NORMAL → HIGH (tighten 30%) → CRITICAL (tighten 60%)
- **Smooth transitions:** Exponential moving average prevents oscillation

### Request Coalescing
- **Purpose:** Deduplicate concurrent rate limit checks for same client+endpoint
- **Window:** 25ms default (configurable)
- **Benefit:** Reduces storage backend calls by up to N-1 under thundering herd

### Quota Sharing
- **Hierarchical pools:** Multiple clients share a parent limit
- **Example:** "standard" pool (500 req/min) shared by all basic clients
- **Dual check:** Both individual limit AND pool limit must allow

### Weighted Operations
- **Per-method costs:** GET=1, POST=5, DELETE=10 (configurable)
- **Use case:** Write operations are more expensive than reads
