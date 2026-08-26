import ast
from pathlib import Path


def test_phase3_code_does_not_import_phase1_persistence_models() -> None:
    phase2_root = Path("src/job_search_cockpit/phase2")
    forbidden_module = "job_search_cockpit.storage.models"
    violations: list[str] = []

    for source_path in sorted(phase2_root.glob("*.py")):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            imported_modules: tuple[str, ...] = ()
            if isinstance(node, ast.ImportFrom) and node.module:
                imported_modules = (node.module,)
            elif isinstance(node, ast.Import):
                imported_modules = tuple(alias.name for alias in node.names)
            if any(
                module == forbidden_module or module.startswith(f"{forbidden_module}.")
                for module in imported_modules
            ):
                violations.append(f"{source_path}:{node.lineno}")

    assert violations == []
