"""Contract tests ensuring the OpenAPI spec matches the real Flask routes."""

from __future__ import annotations

import pytest

from app.api.openapi import OPENAPI_SPEC
from app.factory import create_app


class TestOpenAPIContract:
    """Validate that OpenAPI paths/methods are backed by real Flask routes."""

    @pytest.fixture
    def app(self):
        return create_app()

    def test_every_openapi_path_exists_in_flask(self, app):
        """Every path+method in the OpenAPI spec must be registered."""
        routes: dict[str, set[str]] = {}
        for rule in app.url_map.iter_rules():
            # Normalize Flask rule to OpenAPI path style
            path = rule.rule
            if path.endswith("/") and path != "/":
                path = path[:-1]
            methods = routes.setdefault(path, set())
            methods.update(rule.methods)

        for path, operations in OPENAPI_SPEC["paths"].items():
            assert path in routes, f"OpenAPI path {path} is not a Flask route"
            methods = routes[path]
            for method in operations:
                if method == "parameters":
                    continue
                assert method.upper() in methods, (
                    f"OpenAPI path {path} method {method.upper()} not in Flask route"
                )

    def test_openapi_json_and_docs_respond(self, app):
        """The spec and Swagger UI endpoints must be live."""
        client = app.test_client()
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["openapi"] == "3.1.0"

        resp = client.get("/docs")
        assert resp.status_code == 200
