"""T040 — Async purity: no time.sleep or requests imports under app/api or app/services.

Constitution Principle IV §Operational Constraints — Async-only request path.
"""
import ast
from pathlib import Path

APP = Path(__file__).parent.parent.parent / "app"

_BANNED = {"time", "requests"}


def _banned_imports_in_file(path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in _BANNED:
                    found.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in _BANNED:
                    found.append(node.module)
    return found


def _collect_violations(directory: Path) -> list[str]:
    violations: list[str] = []
    for filepath in directory.rglob("*.py"):
        bad = _banned_imports_in_file(filepath)
        for imp in bad:
            violations.append(f"{filepath.relative_to(APP.parent)}: import {imp}")
    return violations


def test_no_sync_imports_in_api() -> None:
    violations = _collect_violations(APP / "api")
    assert not violations, (
        "app/api must not import 'time' or 'requests'.\n" + "\n".join(violations)
    )


def test_no_sync_imports_in_services() -> None:
    violations = _collect_violations(APP / "services")
    assert not violations, (
        "app/services must not import 'time' or 'requests'.\n"
        + "\n".join(violations)
    )
