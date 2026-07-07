"""Credential-free guards for the eval assets under evals/.

Real-model execution happens only via `uv run --group eval adk eval ...`;
these tests only verify the assets stay loadable and within the agreed
budget of at most two eval criteria per agent.
"""

import importlib
import json
import sys
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent.parent / "evals"
AGENT_EVAL_DIRS = ["drill_generator", "grading", "failure_analysis", "document_patch"]


def _load_eval_entry_module(name: str) -> object:
    sys.path.insert(0, str(EVALS_DIR))
    try:
        module = importlib.import_module(f"{name}.agent")
        return importlib.reload(module)
    finally:
        sys.path.remove(str(EVALS_DIR))


def test_eval_entry_modules_expose_parentless_root_agent() -> None:
    for name in AGENT_EVAL_DIRS:
        module = _load_eval_entry_module(name)
        root_agent = module.root_agent  # type: ignore[attr-defined]
        assert root_agent.name == f"{name}_agent"
        assert root_agent.parent_agent is None


def test_evalset_files_are_wellformed() -> None:
    for name in AGENT_EVAL_DIRS:
        payload = json.loads((EVALS_DIR / name / f"{name}.evalset.json").read_text("utf-8"))
        assert payload["eval_set_id"]
        assert len(payload["eval_cases"]) >= 1
        for case in payload["eval_cases"]:
            for invocation in case["conversation"]:
                text = invocation["user_content"]["parts"][0]["text"]
                json.loads(text)  # input must be a JSON string (input_schema enforcement)


def test_configs_stay_within_two_criteria_per_agent() -> None:
    for name in AGENT_EVAL_DIRS:
        config = json.loads((EVALS_DIR / name / "test_config.json").read_text("utf-8"))
        criteria = config["criteria"]
        assert 1 <= len(criteria) <= 2, f"{name}: 評価項目は各エージェント最大2つ"
        rubric_criterion = criteria.get("rubric_based_final_response_quality_v1")
        if rubric_criterion is not None:
            assert rubric_criterion["rubrics"], f"{name}: rubric メトリクスには rubrics が必須"
