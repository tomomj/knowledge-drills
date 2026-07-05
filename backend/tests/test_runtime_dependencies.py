import tomllib
from pathlib import Path


def test_backend_runtime_dependencies_include_required_sdks() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    dependencies = pyproject["project"]["dependencies"]

    assert any(dependency.startswith("fastapi") for dependency in dependencies)
    assert any(dependency.startswith("pydantic-settings") for dependency in dependencies)
    assert any(dependency.startswith("google-cloud-firestore") for dependency in dependencies)
    assert any(dependency.startswith("google-cloud-aiplatform") for dependency in dependencies)
