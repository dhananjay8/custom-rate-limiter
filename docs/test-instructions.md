# Showpad Backend Take Home Assignment

## Objective

Develop a production-quality REST API that demonstrates custom API throttling.

The implementation must demonstrate:
- Clean Architecture
- Extensibility
- Testability
- Production readiness

---

# Functional Requirements

## Endpoints

GET /foo

GET /bar

---

## Authentication

Authorization: Bearer <client-id>

Every request must contain the Authorization header.

Unknown clients must return 403.

Missing Authorization header returns 401.

---

## Success Response

HTTP 200

{
"success": true
}

---

## Rate Limited Response

HTTP 429

{
"error": "rate limit exceeded"
}

---

## Mandatory Requirements

- Custom rate limiter
- Different algorithms for /foo and /bar
- Configurable clients
- Different limits per client
- Two storage backends
    - In Memory
    - Persistent
- At least one automated test
- README
- Deployment (Stretch Goal)

---

## Demonstration

Prepare demo for

Client A

Client B

Memory Storage

SQLite Storage

Different algorithms

...