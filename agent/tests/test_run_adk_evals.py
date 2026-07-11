import json
import subprocess
from pathlib import Path

import pytest

from scripts import run_adk_evals


def _write_config(path: Path, judge_model: str) -> None:
    path.write_text(
        json.dumps(
            {
                "criteria": {
                    "rubric_based_final_response_quality_v1": {
                        "judge_model_options": {"judge_model": judge_model}
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_prepare_vertex_maas_openai_environment_preserves_provided_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "test_config.json"
    _write_config(config_path, "openai/google/gemma-4-26b-a4b-it-maas")
    env = {"GOOGLE_CLOUD_PROJECT": "test-project", "OPENAI_API_KEY": "provided-token"}

    def unexpected_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("gcloud must not run when OPENAI_API_KEY is provided")

    monkeypatch.setattr(subprocess, "run", unexpected_run)

    run_adk_evals._prepare_vertex_maas_openai_environment(env, config_path)

    assert env["OPENAI_API_KEY"] == "provided-token"
    assert env["OPENAI_BASE_URL"] == (
        "https://aiplatform.googleapis.com/v1/"
        "projects/test-project/locations/global/endpoints/openapi"
    )


def test_prepare_vertex_maas_openai_environment_gets_local_adc_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "test_config.json"
    _write_config(config_path, "openai/google/gemma-4-26b-a4b-it-maas")
    env = {"GOOGLE_CLOUD_PROJECT": "test-project"}

    def fake_run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["gcloud"], returncode=0, stdout="adc-token\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    run_adk_evals._prepare_vertex_maas_openai_environment(env, config_path)

    assert env["OPENAI_API_KEY"] == "adc-token"


def test_prepare_vertex_maas_openai_environment_skips_other_judges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "test_config.json"
    _write_config(config_path, "gemini-3.1-flash-lite")
    env = {"GOOGLE_CLOUD_PROJECT": "test-project"}

    def unexpected_run(*args: object, **kwargs: object) -> None:
        raise AssertionError("gcloud must not run for a native Gemini judge")

    monkeypatch.setattr(subprocess, "run", unexpected_run)

    run_adk_evals._prepare_vertex_maas_openai_environment(env, config_path)

    assert "OPENAI_API_KEY" not in env
    assert "OPENAI_BASE_URL" not in env
