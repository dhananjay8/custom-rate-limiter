#!/bin/bash
# HTTP Integration Test Script for Rate Limiter API
# Runs against a live container on localhost:5050

set -e

BASE_URL="http://localhost:5050"
PASS=0
FAIL=0
TOTAL=0

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

assert_status() {
    local test_name="$1"
    local expected="$2"
    local actual="$3"
    TOTAL=$((TOTAL + 1))
    if [ "$expected" == "$actual" ]; then
        echo -e "  ${GREEN}✓ PASS${NC}: $test_name (HTTP $actual)"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}✗ FAIL${NC}: $test_name (expected $expected, got $actual)"
        FAIL=$((FAIL + 1))
    fi
}

assert_contains() {
    local test_name="$1"
    local expected="$2"
    local actual="$3"
    TOTAL=$((TOTAL + 1))
    if echo "$actual" | grep -q "$expected"; then
        echo -e "  ${GREEN}✓ PASS${NC}: $test_name"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}✗ FAIL${NC}: $test_name (expected to contain '$expected')"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "============================================================"
echo "  RATE LIMITER HTTP INTEGRATION TESTS"
echo "============================================================"
echo ""

# Reset state first
curl -s -X POST "$BASE_URL/admin/reset" > /dev/null

# ============================================================
echo -e "${YELLOW}--- Test: Health Endpoint ---${NC}"
# ============================================================
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
assert_status "GET /health returns 200" "200" "$STATUS"

BODY=$(curl -s "$BASE_URL/health")
assert_contains "Health has status field" '"status"' "$BODY"
assert_contains "Health shows healthy" '"healthy"' "$BODY"
assert_contains "Health shows algorithms" '"algorithms"' "$BODY"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: Authentication ---${NC}"
# ============================================================
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/foo")
assert_status "GET /foo without auth returns 401" "401" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Basic token" "$BASE_URL/foo")
assert_status "GET /foo with wrong auth format returns 401" "401" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer unknown-client" "$BASE_URL/foo")
assert_status "GET /foo with unknown client returns 403" "403" "$STATUS"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer client-basic" "$BASE_URL/foo")
assert_status "GET /foo with valid client returns 200" "200" "$STATUS"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: Success Responses ---${NC}"
# ============================================================
# Reset to clear any previous calls
curl -s -X POST "$BASE_URL/admin/reset" > /dev/null

BODY=$(curl -s -H "Authorization: Bearer client-basic" "$BASE_URL/foo")
assert_contains "GET /foo returns success:true" '"success": true' "$BODY"

BODY=$(curl -s -H "Authorization: Bearer client-basic" "$BASE_URL/bar")
assert_contains "GET /bar returns success:true" '"success": true' "$BODY"

BODY=$(curl -s -H "Authorization: Bearer client-premium" "$BASE_URL/foo")
assert_contains "GET /foo (premium) returns success:true" '"success": true' "$BODY"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: Rate Limiting (client-basic on /foo, limit=10) ---${NC}"
# ============================================================
curl -s -X POST "$BASE_URL/admin/reset" > /dev/null

# Send 10 requests (should all succeed)
for i in $(seq 1 10); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer client-basic" "$BASE_URL/foo")
    if [ "$STATUS" != "200" ]; then
        echo -e "  ${RED}✗ FAIL${NC}: Request $i should be 200, got $STATUS"
        FAIL=$((FAIL + 1))
        TOTAL=$((TOTAL + 1))
    fi
done
TOTAL=$((TOTAL + 1))
echo -e "  ${GREEN}✓ PASS${NC}: First 10 requests to /foo succeed (HTTP 200)"
PASS=$((PASS + 1))

# 11th request should be rate limited
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer client-basic" "$BASE_URL/foo")
assert_status "11th request to /foo returns 429" "429" "$STATUS"

BODY=$(curl -s -H "Authorization: Bearer client-basic" "$BASE_URL/foo")
assert_contains "429 body has 'rate limit exceeded'" '"rate limit exceeded"' "$BODY"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: Rate Limiting (client-basic on /bar, limit=20) ---${NC}"
# ============================================================
curl -s -X POST "$BASE_URL/admin/reset" > /dev/null

for i in $(seq 1 20); do
    STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer client-basic" "$BASE_URL/bar")
    if [ "$STATUS" != "200" ]; then
        echo -e "  ${RED}✗ FAIL${NC}: Request $i to /bar should be 200, got $STATUS"
        FAIL=$((FAIL + 1))
        TOTAL=$((TOTAL + 1))
    fi
done
TOTAL=$((TOTAL + 1))
echo -e "  ${GREEN}✓ PASS${NC}: First 20 requests to /bar succeed (HTTP 200)"
PASS=$((PASS + 1))

STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer client-basic" "$BASE_URL/bar")
assert_status "21st request to /bar returns 429" "429" "$STATUS"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: Client Isolation ---${NC}"
# ============================================================
curl -s -X POST "$BASE_URL/admin/reset" > /dev/null

# Exhaust client-basic on /foo
for i in $(seq 1 10); do
    curl -s -o /dev/null -H "Authorization: Bearer client-basic" "$BASE_URL/foo"
done

# client-basic should be rate limited
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer client-basic" "$BASE_URL/foo")
assert_status "client-basic exhausted on /foo (429)" "429" "$STATUS"

# client-premium should still work
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer client-premium" "$BASE_URL/foo")
assert_status "client-premium still works on /foo (200)" "200" "$STATUS"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: Endpoint Isolation ---${NC}"
# ============================================================
# client-basic is exhausted on /foo but /bar should work
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer client-basic" "$BASE_URL/bar")
assert_status "client-basic still works on /bar after /foo exhausted (200)" "200" "$STATUS"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: Rate Limit Headers ---${NC}"
# ============================================================
curl -s -X POST "$BASE_URL/admin/reset" > /dev/null

HEADERS=$(curl -s -D - -o /dev/null -H "Authorization: Bearer client-basic" "$BASE_URL/foo")
assert_contains "Response has X-RateLimit-Limit header" "X-RateLimit-Limit" "$HEADERS"
assert_contains "Response has X-RateLimit-Remaining header" "X-RateLimit-Remaining" "$HEADERS"
assert_contains "Response has X-RateLimit-Reset header" "X-RateLimit-Reset" "$HEADERS"
assert_contains "Response has X-Request-ID header" "X-Request-ID" "$HEADERS"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: 429 Response Headers ---${NC}"
# ============================================================
# Exhaust limit
for i in $(seq 1 10); do
    curl -s -o /dev/null -H "Authorization: Bearer client-basic" "$BASE_URL/foo"
done

HEADERS=$(curl -s -D - -o /dev/null -H "Authorization: Bearer client-basic" "$BASE_URL/foo")
assert_contains "429 has Retry-After header" "Retry-After" "$HEADERS"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: Metrics ---${NC}"
# ============================================================
BODY=$(curl -s "$BASE_URL/metrics")
assert_contains "Metrics has total_requests" '"total_requests"' "$BODY"
assert_contains "Metrics has allowed_requests" '"allowed_requests"' "$BODY"
assert_contains "Metrics has rejected_requests" '"rejected_requests"' "$BODY"
assert_contains "Metrics has per_client" '"per_client"' "$BODY"
assert_contains "Metrics has per_endpoint" '"per_endpoint"' "$BODY"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: Admin Config ---${NC}"
# ============================================================
BODY=$(curl -s "$BASE_URL/admin/config")
assert_contains "Admin config has storage" '"storage"' "$BODY"
assert_contains "Admin config has algorithms" '"algorithms"' "$BODY"
assert_contains "Admin config has clients" '"clients"' "$BODY"
assert_contains "Admin config shows client-basic" '"client-basic"' "$BODY"
assert_contains "Admin config shows client-premium" '"client-premium"' "$BODY"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: Admin Reset ---${NC}"
# ============================================================
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/admin/reset")
assert_status "POST /admin/reset returns 200" "200" "$STATUS"

# After reset, rate limit should be cleared
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer client-basic" "$BASE_URL/foo")
assert_status "After reset, client-basic can access /foo again (200)" "200" "$STATUS"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: 404 for unknown route ---${NC}"
# ============================================================
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/unknown")
assert_status "GET /unknown returns 404" "404" "$STATUS"

BODY=$(curl -s "$BASE_URL/unknown")
assert_contains "404 body has error field" '"error"' "$BODY"

# ============================================================
echo ""
echo -e "${YELLOW}--- Test: 405 Method Not Allowed ---${NC}"
# ============================================================
STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST -H "Authorization: Bearer client-basic" "$BASE_URL/foo")
assert_status "POST /foo returns 405" "405" "$STATUS"

# ============================================================
echo ""
echo "============================================================"
echo -e "  RESULTS: ${GREEN}$PASS passed${NC}, ${RED}$FAIL failed${NC}, $TOTAL total"
echo "============================================================"
echo ""

if [ $FAIL -gt 0 ]; then
    exit 1
fi
exit 0
