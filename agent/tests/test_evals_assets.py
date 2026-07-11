"""Credential-free guards for the eval assets under evals/.

Real-model execution happens only via
`uv run --native-tls --isolated --frozen --group eval adk eval ...`;
these tests only verify the assets stay loadable and within the agreed
budget of one integrated LLM-judge rubric per agent.
"""

import ast
import importlib
import json
import sys
from pathlib import Path
from typing import cast

from knowledge_drill_agent.schemas import FailureAnalysisOutput

EVALS_DIR = Path(__file__).resolve().parent.parent / "evals"
RUNNER_PATH = Path(__file__).resolve().parent.parent / "scripts" / "run_adk_evals.py"
AGENT_EVAL_DIRS = ["drill_generator", "grading", "failure_analysis", "document_patch"]
GEMMA_JUDGE_MODEL = "openai/google/gemma-4-26b-a4b-it-maas"


def _load_eval_entry_module(name: str) -> object:
    sys.path.insert(0, str(EVALS_DIR))
    try:
        module = importlib.import_module(f"{name}.agent")
        return importlib.reload(module)
    finally:
        sys.path.remove(str(EVALS_DIR))


def _load_quick_eval_cases() -> dict[str, tuple[str, ...]]:
    module = ast.parse(RUNNER_PATH.read_text("utf-8"))
    for node in module.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "QUICK_EVAL_CASES"
            and node.value is not None
        ):
            return cast(dict[str, tuple[str, ...]], ast.literal_eval(node.value))
    raise AssertionError("QUICK_EVAL_CASES is not defined in scripts/run_adk_evals.py")


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


def test_failure_analysis_eval_expected_outputs_include_review_notes() -> None:
    payload = json.loads(
        (EVALS_DIR / "failure_analysis" / "failure_analysis.evalset.json").read_text("utf-8")
    )
    for case in payload["eval_cases"]:
        for invocation in case["conversation"]:
            text = invocation["final_response"]["parts"][0]["text"]
            output = FailureAnalysisOutput.model_validate_json(text)
            assert output.review_notes, case["eval_id"]
            assert {
                note.timeline_step
                for note in output.review_notes
            } <= {
                "match_course_evidence",
                "decide_patch_strategy",
            }


def test_configs_use_one_integrated_rubric_per_agent() -> None:
    for name in AGENT_EVAL_DIRS:
        config = json.loads((EVALS_DIR / name / "test_config.json").read_text("utf-8"))
        criteria = config["criteria"]
        assert list(criteria) == ["rubric_based_final_response_quality_v1"]
        rubrics = criteria["rubric_based_final_response_quality_v1"]["rubrics"]
        assert len(rubrics) == 1, f"{name}: LLM judge rubric は統合して1つにする"


def test_configs_use_gemma_4_judge() -> None:
    for name in AGENT_EVAL_DIRS:
        config = json.loads((EVALS_DIR / name / "test_config.json").read_text("utf-8"))
        criterion = config["criteria"]["rubric_based_final_response_quality_v1"]
        assert criterion["judge_model_options"]["judge_model"] == GEMMA_JUDGE_MODEL


def test_failure_analysis_eval_uses_bounded_judge_sampling() -> None:
    config = json.loads(
        (EVALS_DIR / "failure_analysis" / "test_config.json").read_text("utf-8")
    )
    criterion = config["criteria"]["rubric_based_final_response_quality_v1"]
    judge_options = criterion["judge_model_options"]

    assert judge_options["judge_model"] == GEMMA_JUDGE_MODEL
    assert judge_options["num_samples"] == 3


def test_quick_eval_cases_exist() -> None:
    quick_eval_cases = _load_quick_eval_cases()
    assert set(quick_eval_cases) == set(AGENT_EVAL_DIRS)
    for name, eval_case_ids in quick_eval_cases.items():
        payload = json.loads((EVALS_DIR / name / f"{name}.evalset.json").read_text("utf-8"))
        available_case_ids = {case["eval_id"] for case in payload["eval_cases"]}
        assert set(eval_case_ids) <= available_case_ids
