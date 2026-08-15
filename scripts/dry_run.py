#!/usr/bin/env python3
"""Logical dry-run diagnostics for the custom-rate-limiter codebase.

This script is intentionally non-invasive. It does not mutate app state, deploy
infrastructure, or require external services.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


REQUIRED_NON_EMPTY_FILES = [
    ".github/workflows/ci-cd.yml",
    "infra/azure/main.bicep",
    "infra/azure/parameters.json",
    "infra/azure/deploy.sh",
    "infra/azure/quickstart.sh",
    "infra/azure/README.md",
]

OPTIONAL_DEPENDENCIES = [
    "flask",
    "pydantic",
    "pydantic_settings",
    "pytest",
]


def _check_python_version() -> dict[str, Any]:
    major, minor = sys.version_info.major, sys.version_info.minor
    ok = (major, minor) >= (3, 12)
    return {
        "check": "python_version",
        "status": "pass" if ok else "warn",
        "details": {
            "required": "3.12+",
            "current": f"{major}.{minor}",
        },
    }


def _check_non_empty_files(root: Path) -> dict[str, Any]:
    missing: list[str] = []
    empty: list[str] = []

    for rel in REQUIRED_NON_EMPTY_FILES:
        path = root / rel
        if not path.exists():
            missing.append(rel)
            continue
        if path.stat().st_size == 0:
            empty.append(rel)

    ok = not missing and not empty
    return {
        "check": "required_files_populated",
        "status": "pass" if ok else "fail",
        "details": {
            "missing": missing,
            "empty": empty,
        },
    }


def _check_compile(root: Path) -> dict[str, Any]:
    cmd = [
        sys.executable,
        "-m",
        "compileall",
        "-q",
        "app",
        "tests",
        "scripts",
        "run.py",
    ]
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    ok = proc.returncode == 0
    return {
        "check": "python_compile",
        "status": "pass" if ok else "fail",
        "details": {
            "return_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        },
    }


def _check_dependencies() -> dict[str, Any]:
    missing: list[str] = []
    for module_name in OPTIONAL_DEPENDENCIES:
        try:
            __import__(module_name)
        except Exception:
            missing.append(module_name)

    return {
        "check": "optional_python_dependencies",
        "status": "pass" if not missing else "warn",
        "details": {
            "missing": missing,
            "hint": "Install dependencies to run full pytest/app smoke checks.",
        },
    }


def _check_tooling() -> dict[str, Any]:
    tools = {
        "python": shutil.which("python3") is not None,
        "pytest": shutil.which("pytest") is not None,
        "az": shutil.which("az") is not None,
        "docker": shutil.which("docker") is not None,
    }

    return {
        "check": "cli_tooling",
        "status": "pass" if tools["python"] else "fail",
        "details": tools,
    }


def _run_pytest_smoke(root: Path) -> dict[str, Any]:
    cmd = [sys.executable, "-m", "pytest", "tests/unit/test_api.py::TestHealthEndpoint::test_health_response", "-q"]
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    ok = proc.returncode == 0
    return {
        "check": "pytest_smoke_health_endpoint",
        "status": "pass" if ok else "fail",
        "details": {
            "return_code": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip(),
        },
    }


def run(root: Path, run_tests: bool) -> dict[str, Any]:
    checks: list[dict[str, Any]] = [
        _check_python_version(),
        _check_non_empty_files(root),
        _check_compile(root),
        _check_dependencies(),
        _check_tooling(),
    ]

    if run_tests:
        checks.append(_run_pytest_smoke(root))

    has_failures = any(item["status"] == "fail" for item in checks)
    overall_status = "fail" if has_failures else "pass"

    return {
        "overall_status": overall_status,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run logical dry-run diagnostics.")
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run a minimal pytest smoke test if dependencies are installed.",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    report = run(root=root, run_tests=args.run_tests)
    print(json.dumps(report, indent=2))

    return 1 if report["overall_status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
