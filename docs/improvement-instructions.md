# 1. Do NOT implement only two algorithms.

This is where Staff Engineer candidates differentiate themselves.

Instead implement a **Rate Limiting Framework**.

Something like

```
RateLimiterAlgorithm

    allow_request()

        ▲

        │

──────────────────────────────────

Fixed Window

Sliding Window Log

Sliding Window Counter

Token Bucket

Leaky Bucket

GCRA

Rolling Window

Adaptive Rate Limiter

Burst Rate Limiter

Composite Rate Limiter
```

Then

```
/foo

↓

algorithm=fixed_window
```

During interview

```
algorithm=token_bucket
```

One config change.

No code changes.

That demonstrates extensibility.

---

# Algorithms I would implement

## Required

✅ Fixed Window

O(1)

---

✅ Sliding Window Log

O(log n)

---

## Additional

### Sliding Window Counter

Very common production algorithm.

Lower memory than Sliding Window Log.

---

### Token Bucket ⭐⭐⭐⭐⭐

One of the most asked interview algorithms.

Supports bursts.

Used by

AWS

NGINX

Envoy

Istio

Kong

Cloudflare

---

### Leaky Bucket ⭐⭐⭐⭐

Smooth traffic.

Frequently asked.

---

### GCRA (Generic Cell Rate Algorithm) ⭐⭐⭐⭐⭐

Used in

Stripe

Envoy

Cloudflare

Telecom

Much harder.

Interviewers love seeing this.

---

### Rolling Window Counter

Alternative implementation.

---

### Burst Limiter

Allow

100 requests instantly

then

10/sec

---

### Adaptive Rate Limiter

Increase/decrease limits dynamically.

Can be based on

CPU

Latency

Queue depth

Stretch goal.

---

### Composite Rate Limiter

Example

```
Client

↓

Global Limit

↓

Endpoint Limit

↓

Burst Limit

↓

Tenant Limit

↓

Pass
```

Very senior design.

---

# Storage implementations

Instead of only

Memory

SQLite

Design

```
RateLimitRepository

↑

MemoryRepository

SQLiteRepository

RedisRepository

DynamoDBRepository

PostgresRepository

MongoRepository
```

Only implement

Memory

SQLite

Leave remaining ready.

---

# Configuration

Avoid

```python
if endpoint=="foo":
```

Instead

```yaml
algorithms:

  foo:
      algorithm: fixed_window

  bar:
      algorithm: sliding_log
```

During interview

```
bar:
    algorithm: token_bucket
```

Done.

---

# Patterns to demonstrate

I would intentionally include these.

✅ Strategy Pattern

Algorithm selection

---

✅ Factory Pattern

Storage creation

---

✅ Repository Pattern

Persistence

---

✅ Dependency Injection

Application wiring

---

✅ Builder Pattern

Configuration

---

✅ Template Method

Common algorithm execution flow

---

✅ Chain of Responsibility

Authentication

↓

Validation

↓

Rate Limit

↓

Controller

---

✅ Adapter Pattern

Storage adapters

---

# Extra endpoints

Besides assignment

```
GET /foo

GET /bar

GET /health

GET /metrics

GET /version

GET /admin/config

GET /admin/algorithms

GET /admin/storage

POST /admin/reset
```

Very impressive.

---

# Metrics

Track

```
Allowed Requests

Rejected Requests

Remaining Tokens

Window Reset

Algorithm

Latency

Client

Storage

Cache Hit

Cache Miss
```

---

# Tests

Don't stop at one.

```
tests/

    unit/

        algorithms/

        repositories/

        auth/

        middleware/

    integration/

    concurrency/

    benchmark/

    load/

    edge_cases/

    contract/
```

---

# Benchmark

Provide

```
python benchmark.py

100

1000

10000

50000

100000
```

Print

```
Average

Median

P95

P99

Rejected

Allowed

Memory

CPU

Requests/sec
```

---

# Interview features

Prepare easy switches.

```
Current

/foo

↓

Fixed Window

```

Interviewer

> Can you make it Token Bucket?

You change

```
algorithm: token_bucket
```

Restart.

Done.

No code edits.

---

# Future-ready interfaces

Even if not implemented.

```
IRateLimiter

IRateLimitAlgorithm

IRateLimitRepository

IClock

IStorage

IClientProvider

IConfigurationProvider

IMetricsCollector

ILogger

IAuthenticationProvider
```

This makes the design look like an internal SDK rather than a coding assignment.

---

## Recommendation

I would build this as a **mini rate-limiting framework**, not just an API. The assignment only mandates two endpoints and two algorithms, but the interview explicitly states they'll ask you to explain design choices and extend the project.  A framework with pluggable algorithms, storage backends, configuration-driven endpoint mapping, comprehensive tests, and production-oriented architecture gives you the ability to demonstrate those extensions by changing configuration rather than rewriting core logic.
