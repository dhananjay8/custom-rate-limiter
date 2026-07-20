# Production-Grade Custom Rate Limiter (Showpad Backend Take Home Assignment)

## Objective

Build a **production-grade Python Flask application** for the attached Showpad Backend Take Home assignment.

This project will eventually be pushed to a **private GitHub repository** as part of a **Staff Software Engineer interview**.

> **Do NOT build a simple coding assignment.**

Instead, build something that demonstrates:

- Senior architecture
- Clean engineering principles
- Extensibility
- Scalability
- Production readiness

The implementation should resemble a backend microservice that could evolve into a production system.

---

# Assignment Requirements (Mandatory)

## Implement

```
GET /foo
GET /bar
```

Every request requires:

```
Authorization: Bearer <client-id>
```

### Success Response

```json
HTTP 200

{
  "success": true
}
```

### Rate Limited Response

```json
HTTP 429

{
  "error": "rate limit exceeded"
}
```

## Requirements

- Implement completely custom rate limiting logic.
- Do **NOT** use Flask-Limiter or any third-party rate limiter.
- Every client has configurable limits.
- Support a minimum of **two clients**.
- Different clients have different limits.
- `/foo` and `/bar` must use different rate limiting algorithms.
- Support two storage strategies:
    - InMemory
    - Persistent Storage
- Make storage strategy configurable.
- Include automated tests.

---

# This is NOT enough.

Enhance the solution to **Staff Software Engineer quality**.

---

# Tech Stack

- Python 3.12
- Flask
- SQLite (persistent storage)
- pytest
- Docker
- Docker Compose
- Pydantic
- Poetry or uv
- SQLAlchemy
- Gunicorn
- Black
- isort
- mypy
- pre-commit
- GitHub Actions

---

# Project Goals

The codebase should demonstrate:

- SOLID
- DRY
- KISS
- Clean Architecture
- Hexagonal Architecture principles
- Dependency Injection
- Strategy Pattern
- Repository Pattern
- Factory Pattern
- Configuration Management
- Structured Logging
- Production-ready Error Handling
- High Testability

---

# Project Structure

```text
custom-rate-limiter/

├── app/
│   ├── api/
│   │   ├── routes.py
│   │   └── middleware.py
│   │
│   ├── algorithms/
│   │   ├── base.py
│   │   ├── fixed_window.py
│   │   └── sliding_window_log.py
│   │
│   ├── auth/
│   │   └── bearer_auth.py
│   │
│   ├── services/
│   │   └── rate_limiter.py
│   │
│   ├── repositories/
│   │   ├── rate_limit_repository.py
│   │   ├── sqlite_repository.py
│   │   └── memory_repository.py
│   │
│   ├── storage/
│   │   ├── models.py
│   │   └── sqlite.py
│   │
│   ├── config/
│   │   └── settings.py
│   │
│   ├── exceptions/
│   ├── utils/
│   ├── logging/
│   └── dependency_injection.py
│
├── tests/
│   ├── unit/
│   ├── integration/ - skip for now
│   └── stress/ - skip for now
│
├── docs/
├── scripts/
├── docker/
└── README.md
```

---

# Rate Limiting Algorithms

## `/foo`

Use:

**Fixed Window Counter**

## `/bar`

Use:

**Sliding Window Log**

Requirements:

- Implement algorithms from scratch.
- Do **NOT** use external packages.
- Every algorithm must implement a common interface.

Example:

```python
RateLimiterAlgorithm

allow_request(...)
```

This architecture should allow adding new algorithms without changing business logic.

Examples:

- Token Bucket
- Leaky Bucket
- Sliding Window Counter

---

# Storage Abstraction

Create an interface:

```
RateLimitRepository
```

Implement:

- MemoryRepository
- SQLiteRepository

The business layer must never know which implementation is used.

Storage selection must be configuration-driven.

---

# Configuration

Use environment variables.

Example:

```text
RATE_LIMIT_STORAGE=memory

CLIENT_1_LIMIT=10
CLIENT_1_WINDOW=60

CLIENT_2_LIMIT=100
CLIENT_2_WINDOW=60
```

---

# Authentication

Middleware should extract:

```
Authorization: Bearer <client-id>
```

Return:

- **401** if Authorization header is missing.
- **403** if client is unknown.

---

# Clients

## client-basic

### /foo

```
10 requests / minute
```

### /bar

```
20 requests / minute
```

---

## client-premium

### /foo

```
100 requests / minute
```

### /bar

```
250 requests / minute
```

Everything must be configuration-driven.

---

# Persistent Storage

Use SQLite.

Design an appropriate schema.

Store:

- client
- endpoint
- timestamp
- window
- counter

Support both algorithms.

---

# Concurrency

Implementation must be thread-safe.

Requirements:

- Proper locking around in-memory structures.
- Repository operations should avoid race conditions.

---

# Logging

Implement structured JSON logging.

Log:

- request
- client
- endpoint
- decision
- remaining quota
- algorithm
- latency

---

# Error Handling

Implement:

- Central exception handlers
- Meaningful responses
- Validation

---

# Health Endpoint

```
GET /health
```

Return:

- status
- storage
- algorithm configuration
- uptime

---

# Metrics Endpoint

```
GET /metrics
```

Return:

- Total Requests
- Allowed Requests
- Blocked Requests
- Per Client
- Per Endpoint

---

# Admin Endpoint

```
GET /admin/config
```

Return:

- Current configuration
- Current clients
- Algorithms
- Storage

---

# Testing

Include:

- Unit Tests
- Repository Tests
- Algorithm Tests
- Authentication Tests
- API Tests
- Concurrency Tests
- Integration Tests
- Stress Tests
- Edge Cases
- Boundary Conditions
- Window Reset
- Multiple Clients
- Storage Switching

---

# Benchmark

Provide a benchmark script.

Benchmark:

- 1,000 requests
- 5,000 requests
- 10,000 requests

Measure:

- Average latency
- P95
- Allowed requests
- Rejected requests

---

# Docker

Provide:

- Dockerfile
- docker-compose.yml

The application should run with a single command.

---

# README

Create professional documentation.

Include:

- Architecture
- Folder Structure
- Design Decisions
- Tradeoffs
- Algorithms
- Storage
- Running the Application
- Running Tests
- Benchmark Results
- Future Improvements

---

# Interview Readiness

Design the project so the interviewer can ask:

- How would you replace SQLite with Redis?
- How would you scale across multiple pods?
- How would you implement distributed rate limiting?
- How would you use Redis Lua scripts?
- How would you implement Token Bucket?
- How would you implement Leaky Bucket?
- How would you integrate Envoy or an API Gateway?
- How would you deploy this on Kubernetes?
- How would you make it horizontally scalable?

The architecture should already support these extensions.

---

# Stretch Goals

Implement:

- Redis Repository (optional)
- Token Bucket algorithm
- OpenAPI (Swagger)
- Prometheus Metrics
- GitHub Actions CI
- Docker Healthcheck
- Request IDs
- Correlation IDs
- Graceful Shutdown
- Performance Benchmark Report

---

# Coding Standards

- Use complete type hints.
- Every public method must have docstrings.
- Avoid global variables.
- Avoid code duplication.
- Prefer composition over inheritance.
- Keep functions small.
- Avoid magic numbers.
- Use meaningful names.
- High cohesion.
- Low coupling.

---

# Execution Plan

## Step 1

Architecture

## Step 2

Configuration

## Step 3

Repositories

## Step 4

Algorithms

## Step 5

Middleware

## Step 6

Business Layer

## Step 7

REST APIs

## Step 8

Tests

## Step 9

Docker

## Step 10

Documentation

---

# Validation Checklist

After every step ensure:

- Code compiles
- Tests pass
- Formatting passes
- mypy passes

Never skip any implementation detail.

---

# Final Goal

The final output should resemble **production-quality backend software** suitable for a **Staff Software Engineer interview**, rather than a simple coding exercise.