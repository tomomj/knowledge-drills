from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1]

EVALS: dict[str, tuple[str, str, str]] = {
    "grading": (
        "evals/grading",
        "evals/grading/grading.evalset.json",
        "evals/grading/test_config.json",
    ),
    "drill_generator": (
        "evals/drill_generator",
        "evals/drill_generator/drill_generator.evalset.json",
        "evals/drill_generator/test_config.json",
    ),
    "failure_analysis": (
        "evals/failure_analysis",
        "evals/failure_analysis/failure_analysis.evalset.json",
        "evals/failure_analysis/test_config.json",
    ),
    "document_patch": (
        "evals/document_patch",
        "evals/document_patch/document_patch.evalset.json",
        "evals/document_patch/test_config.json",
    ),
}

PASS_STATUS = 1
VERTEX_TRUE_VALUES = {"1", "true", "yes"}


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _missing_auth_environment() -> list[str]:
    use_vertex = (
        os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower()
        in VERTEX_TRUE_VALUES
    )
    if use_vertex:
        return [
            name
            for name in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")
            if not os.environ.get(name, "").strip()
        ]
    if not os.environ.get("GOOGLE_API_KEY", "").strip():
        return ["GOOGLE_API_KEY"]
    return []


def _latest_result(history_dir: Path, before: set[Path]) -> Path:
    after = set(history_dir.glob("*.evalset_result.json"))
    candidates = sorted(after - before, key=lambda path: path.stat().st_mtime)
    if candidates:
        return candidates[-1]
    all_results = sorted(after, key=lambda path: path.stat().st_mtime)
    if not all_results:
        raise RuntimeError(f"adk eval did not write a result file under {history_dir}")
    return all_results[-1]


def _summarize_result(eval_name: str, result_path: Path) -> bool:
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    case_results = payload.get("eval_case_results", [])
    failed_cases = [
        case
        for case in case_results
        if case.get("final_eval_status") != PASS_STATUS
    ]
    passed = len(case_results) - len(failed_cases)
    failed = len(failed_cases)
    print(f"{eval_name}: {passed}/{len(case_results)} passed ({result_path.name})")
    for case in failed_cases:
        print(f"  failed: {case.get('eval_id')} status={case.get('final_eval_status')}")
    return failed == 0


def _run_eval(eval_name: str) -> bool:
    eval_dir, evalset, config = EVALS[eval_name]
    history_dir = AGENT_DIR / eval_dir / ".adk" / "eval_history"
    history_dir.mkdir(parents=True, exist_ok=True)
    before = set(history_dir.glob("*.evalset_result.json"))

    env = os.environ.copy()
    env["PYTHONPATH"] = str(AGENT_DIR)
    command = [
        "uv",
        "run",
        "--isolated",
        "--frozen",
        "--group",
        "eval",
        "adk",
        "eval",
        eval_dir,
        evalset,
        "--config_file_path",
        config,
        "--print_detailed_results",
    ]
    completed = subprocess.run(command, cwd=AGENT_DIR, env=env, check=False)
    result_path = _latest_result(history_dir, before)
    result_ok = _summarize_result(eval_name, result_path)
    return completed.returncode == 0 and result_ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ADK evals and fail on eval failures.")
    parser.add_argument(
        "evals",
        nargs="*",
        choices=tuple(EVALS),
        help="Eval names to run. Defaults to all evals.",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=AGENT_DIR / ".env",
        help="Optional .env file to load before running evals.",
    )
    args = parser.parse_args()

    _load_env_file(args.env_file)
    missing = _missing_auth_environment()
    if missing:
        print(
            "missing ADK authentication environment variables: "
            + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    requested_evals = args.evals or list(EVALS)
    all_ok = True
    for eval_name in requested_evals:
        print(f"running {eval_name}...")
        all_ok = _run_eval(eval_name) and all_ok

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
