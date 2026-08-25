from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_DIR = PROJECT_ROOT / "api"
API_INIT = API_DIR / "__init__.py"
API_APP = API_DIR / "app.py"
REQUIREMENTS = PROJECT_ROOT / "requirements.txt"

EXPECTED_GET_ROUTES = {
    "/health",
    "/api/v1/sales/daily",
    "/api/v1/products/sales",
    "/api/v1/pipelines/runs",
    "/api/v1/quality/issues",
    "/api/v1/alerts",
}

MUTATING_METHODS = {"post", "put", "patch", "delete"}


def _route_decorators(source: str) -> list[tuple[str, str]]:
    tree = ast.parse(source)
    routes: list[tuple[str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name):
                continue
            if decorator.func.value.id != "app":
                continue
            if not decorator.args:
                continue
            if not isinstance(decorator.args[0], ast.Constant):
                continue
            if not isinstance(decorator.args[0].value, str):
                continue

            routes.append(
                (
                    decorator.func.attr.lower(),
                    decorator.args[0].value,
                )
            )

    return routes


class RestApiContractTestCase(unittest.TestCase):
    def test_api_package_and_app_exist(self) -> None:
        self.assertTrue(
            API_INIT.is_file(),
            "REST API package is missing: api/__init__.py",
        )
        self.assertTrue(
            API_APP.is_file(),
            "REST API application is missing: api/app.py",
        )

    def test_requirements_declare_fastapi_runtime(self) -> None:
        requirements_text = REQUIREMENTS.read_text(encoding="utf-8").lower()

        self.assertRegex(
            requirements_text,
            r"(?m)^\s*fastapi(?:\s*[=<>!~].*)?$",
            "requirements.txt must declare FastAPI.",
        )
        self.assertRegex(
            requirements_text,
            r"(?m)^\s*uvicorn(?:\[[^\]]+\])?(?:\s*[=<>!~].*)?$",
            "requirements.txt must declare Uvicorn.",
        )

    def test_api_exposes_read_only_v1_serving_routes(self) -> None:
        if not API_APP.is_file():
            self.skipTest("api/app.py not implemented yet.")

        source = API_APP.read_text(encoding="utf-8")
        routes = _route_decorators(source)

        get_routes = {
            path
            for method, path in routes
            if method == "get"
        }
        missing = EXPECTED_GET_ROUTES - get_routes

        self.assertFalse(
            missing,
            f"Missing required GET routes: {sorted(missing)}",
        )

        mutating = [
            (method, path)
            for method, path in routes
            if method in MUTATING_METHODS
        ]
        self.assertEqual(
            mutating,
            [],
            "Project 01 REST API must remain read-only; "
            f"mutating routes found: {mutating}",
        )

    def test_sqlite_connection_is_explicitly_read_only(self) -> None:
        if not API_APP.is_file():
            self.skipTest("api/app.py not implemented yet.")

        source = API_APP.read_text(encoding="utf-8")

        self.assertRegex(
            source,
            r"mode=ro",
            "SQLite serving connections must use URI read-only mode (mode=ro).",
        )
        self.assertRegex(
            source,
            r"uri\s*=\s*True",
            "SQLite read-only URI mode requires sqlite3.connect(..., uri=True).",
        )

    def test_private_raw_source_path_is_not_exposed(self) -> None:
        if not API_APP.is_file():
            self.skipTest("api/app.py not implemented yet.")

        source = API_APP.read_text(encoding="utf-8").lower()

        forbidden_patterns = [
            r"data[\\/]+raw[\\/]+pawchoice",
            r"pawchoice_influencer",
            r"pawchoice_payments",
            r"latest_raw_error_message",
        ]

        for pattern in forbidden_patterns:
            self.assertIsNone(
                re.search(pattern, source),
                f"REST API must not expose private/raw source detail: {pattern}",
            )


if __name__ == "__main__":
    unittest.main()
