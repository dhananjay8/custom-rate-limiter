"""OpenAPI specification for the rate limiter API.

Provides auto-generated Swagger/OpenAPI documentation accessible
at /docs (Swagger UI) and /openapi.json (raw spec).
"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, render_template_string


OPENAPI_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {
        "title": "Custom Rate Limiter API",
        "version": "2.0.0",
        "description": (
            "Production-grade rate limiting framework with 6 algorithms, "
            "3 storage backends, adaptive limiting, circuit breaker, "
            "weighted operations, request coalescing, and quota sharing."
        ),
        "contact": {"name": "Dhaval Patil"},
        "license": {"name": "MIT"},
    },
    "servers": [
        {"url": "http://localhost:5000", "description": "Local development"},
        {"url": "http://localhost:5050", "description": "Container (memory)"},
        {"url": "http://localhost:5051", "description": "Container (SQLite)"},
    ],
    "paths": {
        "/foo": {
            "get": {
                "summary": "Rate-limited endpoint (foo)",
                "description": "Returns success if rate limit is not exceeded.",
                "operationId": "getFoo",
                "tags": ["Rate Limited Endpoints"],
                "security": [{"BearerAuth": []}],
                "parameters": [
                    {
                        "name": "X-Request-Weight",
                        "in": "header",
                        "required": False,
                        "schema": {"type": "integer", "default": 1},
                        "description": "Custom weight for this request (defaults to endpoint config)",
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Request allowed",
                        "headers": {
                            "X-RateLimit-Limit": {
                                "schema": {"type": "integer"},
                                "description": "Maximum requests allowed in window",
                            },
                            "X-RateLimit-Remaining": {
                                "schema": {"type": "integer"},
                                "description": "Remaining requests in current window",
                            },
                            "X-RateLimit-Reset": {
                                "schema": {"type": "integer"},
                                "description": "Unix timestamp when window resets",
                            },
                            "X-Request-ID": {
                                "schema": {"type": "string"},
                                "description": "Unique request identifier",
                            },
                        },
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean", "example": True}
                                    },
                                }
                            }
                        },
                    },
                    "401": {
                        "description": "Missing or invalid authorization",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"},
                                "examples": {
                                    "missing": {"value": {"error": "Authorization header is required"}},
                                    "invalid": {"value": {"error": "Invalid authorization format. Use: Bearer <client-id>"}},
                                },
                            }
                        },
                    },
                    "403": {
                        "description": "Unknown client",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"},
                                "example": {"error": "Unknown client"},
                            }
                        },
                    },
                    "429": {
                        "description": "Rate limit exceeded",
                        "headers": {
                            "Retry-After": {
                                "schema": {"type": "integer"},
                                "description": "Seconds to wait before retrying",
                            },
                            "X-RateLimit-Limit": {"schema": {"type": "integer"}},
                            "X-RateLimit-Remaining": {"schema": {"type": "integer"}},
                            "X-RateLimit-Reset": {"schema": {"type": "integer"}},
                        },
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Error"},
                                "example": {"error": "rate limit exceeded"},
                            }
                        },
                    },
                },
            }
        },
        "/bar": {
            "get": {
                "summary": "Rate-limited endpoint (bar)",
                "description": "Returns success if rate limit is not exceeded. Uses a different algorithm than /foo.",
                "operationId": "getBar",
                "tags": ["Rate Limited Endpoints"],
                "security": [{"BearerAuth": []}],
                "responses": {
                    "200": {
                        "description": "Request allowed",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "success": {"type": "boolean", "example": True}
                                    },
                                }
                            }
                        },
                    },
                    "401": {"$ref": "#/paths/~1foo/get/responses/401"},
                    "403": {"$ref": "#/paths/~1foo/get/responses/403"},
                    "429": {"$ref": "#/paths/~1foo/get/responses/429"},
                },
            }
        },
        "/health": {
            "get": {
                "summary": "Health check",
                "description": "Returns application health including storage backend status.",
                "operationId": "getHealth",
                "tags": ["Monitoring"],
                "responses": {
                    "200": {
                        "description": "Application is healthy",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/HealthResponse"}
                            }
                        },
                    },
                    "503": {"description": "Application is degraded"},
                },
            }
        },
        "/metrics": {
            "get": {
                "summary": "Request metrics",
                "description": "Returns rate limiting metrics per client and endpoint.",
                "operationId": "getMetrics",
                "tags": ["Monitoring"],
                "responses": {
                    "200": {
                        "description": "Metrics data",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/MetricsResponse"}
                            }
                        },
                    }
                },
            }
        },
        "/admin/config": {
            "get": {
                "summary": "Current configuration",
                "description": "Returns current rate limiter configuration including algorithms and client limits.",
                "operationId": "getAdminConfig",
                "tags": ["Admin"],
                "responses": {
                    "200": {
                        "description": "Configuration data",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                },
            }
        },
        "/admin/reset": {
            "post": {
                "summary": "Reset all state",
                "description": "Resets all rate limit counters and metrics.",
                "operationId": "postAdminReset",
                "tags": ["Admin"],
                "responses": {
                    "200": {
                        "description": "Reset successful",
                        "content": {
                            "application/json": {
                                "example": {"status": "reset_complete"}
                            }
                        },
                    }
                },
            }
        },
        "/admin/adaptive": {
            "get": {
                "summary": "Adaptive rate limiter status",
                "description": "Returns current system load metrics and adaptive multiplier.",
                "operationId": "getAdaptiveStatus",
                "tags": ["Admin"],
                "responses": {
                    "200": {
                        "description": "Adaptive status",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                },
            }
        },
        "/admin/circuit-breaker": {
            "get": {
                "summary": "Circuit breaker status",
                "description": "Returns circuit breaker state and failure counts.",
                "operationId": "getCircuitBreakerStatus",
                "tags": ["Admin"],
                "responses": {
                    "200": {
                        "description": "Circuit breaker status",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                },
            }
        },
        "/admin/quotas": {
            "get": {
                "summary": "Quota pool status",
                "description": "Returns all shared quota pool usage.",
                "operationId": "getQuotaPoolStatus",
                "tags": ["Admin"],
                "responses": {
                    "200": {
                        "description": "Quota pool data",
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    }
                },
            }
        },
        "/openapi.json": {
            "get": {
                "summary": "OpenAPI specification",
                "operationId": "getOpenApiSpec",
                "tags": ["Documentation"],
                "responses": {
                    "200": {"description": "OpenAPI 3.1 JSON specification"}
                },
            }
        },
    },
    "components": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "description": "Client ID passed as Bearer token: `Authorization: Bearer <client-id>`",
            }
        },
        "schemas": {
            "Error": {
                "type": "object",
                "properties": {
                    "error": {"type": "string", "description": "Error message"}
                },
                "required": ["error"],
            },
            "HealthResponse": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["healthy", "degraded"]},
                    "storage": {
                        "type": "object",
                        "properties": {
                            "backend": {"type": "string"},
                            "healthy": {"type": "boolean"},
                        },
                    },
                    "algorithms": {"type": "object"},
                    "circuit_breaker": {"type": "object"},
                    "adaptive": {"type": "object"},
                },
            },
            "MetricsResponse": {
                "type": "object",
                "properties": {
                    "total_requests": {"type": "integer"},
                    "allowed_requests": {"type": "integer"},
                    "rejected_requests": {"type": "integer"},
                    "per_client": {"type": "object"},
                    "per_endpoint": {"type": "object"},
                },
            },
        },
    },
}

# Swagger UI HTML template
_SWAGGER_UI_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Rate Limiter API - Swagger UI</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({
            url: '/openapi.json',
            dom_id: '#swagger-ui',
            presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
            layout: "BaseLayout",
            deepLinking: true,
        });
    </script>
</body>
</html>
"""


def register_openapi_routes(app: Flask) -> None:
    """Register OpenAPI spec and Swagger UI routes.

    Args:
        app: Flask application instance.
    """

    @app.route("/openapi.json", methods=["GET"])
    def openapi_spec() -> tuple[Any, int]:
        """Serve the OpenAPI specification as JSON."""
        return jsonify(OPENAPI_SPEC), 200

    @app.route("/docs", methods=["GET"])
    def swagger_ui() -> str:
        """Serve Swagger UI for interactive API documentation."""
        return render_template_string(_SWAGGER_UI_HTML)
