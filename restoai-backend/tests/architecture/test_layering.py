"""T039 — Architecture layering enforcement.

Asserts:
  - app/api does NOT import from app/db or app/repositories directly.
  - app/repositories does NOT import from fastapi (no HTTPException).
  - app/services does NOT import fastapi Request objects.

Constitution Principle I; plan.md §Architecture decisions.
"""
import ast
from pathlib import Path

APP = Path(__file__).parent.parent.parent / "app"


def _imports_in_file(path: Path) -> list[str]:
    """Return all top-level module names imported in a Python file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


def _all_imports_under(directory: Path) -> dict[str, list[str]]:
    return {
        str(f.relative_to(APP.parent)): _imports_in_file(f)
        for f in directory.rglob("*.py")
    }


def test_api_does_not_import_db_directly() -> None:
    violations: list[str] = []
    for filepath, imports in _all_imports_under(APP / "api").items():
        for imp in imports:
            if imp.startswith("app.db") or imp.startswith("app.repositories"):
                violations.append(f"{filepath}: {imp}")
    assert not violations, (
        "app/api must not import app/db or app/repositories directly.\n"
        + "\n".join(violations)
    )


def test_repositories_do_not_import_fastapi() -> None:
    violations: list[str] = []
    for filepath, imports in _all_imports_under(APP / "repositories").items():
        for imp in imports:
            if imp.startswith("fastapi"):
                violations.append(f"{filepath}: {imp}")
    assert not violations, (
        "app/repositories must not import fastapi.\n" + "\n".join(violations)
    )


def test_services_do_not_import_fastapi_request() -> None:
    violations: list[str] = []
    for filepath, imports in _all_imports_under(APP / "services").items():
        for imp in imports:
            # Allow fastapi.BackgroundTasks if ever needed, but not Request
            if imp == "fastapi" or imp.startswith("fastapi."):
                violations.append(f"{filepath}: {imp}")
    assert not violations, (
        "app/services must not import fastapi request objects.\n"
        + "\n".join(violations)
    )
