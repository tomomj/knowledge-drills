import tomllib
from pathlib import Path
from typing import Any


def _load_pyproject() -> dict[str, Any]:
    return tomllib.loads(Path("pyproject.toml").read_text())


def test_backend_runtime_dependencies_include_required_sdks() -> None:
    dependencies = _load_pyproject()["project"]["dependencies"]

    assert any(dependency.startswith("fastapi") for dependency in dependencies)
    assert any(dependency.startswith("pydantic-settings") for dependency in dependencies)
    assert any(dependency.startswith("google-cloud-firestore") for dependency in dependencies)
    assert any(dependency.startswith("google-cloud-aiplatform") for dependency in dependencies)


def test_backend_runtime_dependencies_include_adk_runtime() -> None:
    dependencies = _load_pyproject()["project"]["dependencies"]

    adk_specs = [dependency for dependency in dependencies if dependency.startswith("google-adk")]
    assert adk_specs, "google-adk must be a backend runtime dependency"
    assert all(
        ">=2" in spec and "<3" in spec for spec in adk_specs
    ), "google-adk must be pinned to the 2.x series (same as agent/uv.lock)"

    assert any(
        dependency.startswith("knowledge-drill-agent") for dependency in dependencies
    ), "the agent package must be a backend runtime dependency"


def test_agent_package_is_editable_path_dependency() -> None:
    sources = _load_pyproject()["tool"]["uv"]["sources"]

    agent_source = sources["knowledge-drill-agent"]
    assert agent_source["path"] == "../agent"
    assert agent_source["editable"] is True
