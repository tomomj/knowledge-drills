from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
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

QUICK_EVAL_CASES: dict[str, tuple[str, ...]] = {
    "grading": ("grading_partial_score",),
    "drill_generator": ("dg_expense_course",),
    "failure_analysis": ("fa_detects_planted_common_error",),
    "document_patch": ("dp_prior_approval_gap",),
}

PASS_STATUS = 1
VERTEX_TRUE_VALUES = {"1", "true", "yes"}
TRANSIENT_ERROR_MARKERS = (
    "RESOURCE_EXHAUSTED",
    "429",
    "quota",
    "rate limit",
    "temporarily unavailable",
    "UNAVAILABLE",
    "DEADLINE_EXCEEDED",
)


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


def _eval_case_ids(evalset_path: Path) -> list[str]:
    payload = json.loads(evalset_path.read_text(encoding="utf-8"))
    return [case["eval_id"] for case in payload["eval_cases"]]


def _is_transient_output(output: str) -> bool:
    normalized = output.lower()
    return any(marker.lower() in normalized for marker in TRANSIENT_ERROR_MARKERS)


def _env_int(name: str, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return max(1, int(raw_value))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        return max(0.0, float(raw_value))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


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


def _run_eval_case(
    eval_name: str,
    eval_dir: str,
    evalset: str,
    config: str,
    eval_case_id: str,
    max_attempts: int,
    retry_base_delay_seconds: float,
) -> bool:
    history_dir = AGENT_DIR / eval_dir / ".adk" / "eval_history"
    history_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(AGENT_DIR)

    for attempt in range(1, max_attempts + 1):
        print(f"running {eval_name}:{eval_case_id} (attempt {attempt}/{max_attempts})...")
        before = set(history_dir.glob("*.evalset_result.json"))
        command = [
            "uv",
            "run",
            "--native-tls",
            "--isolated",
            "--frozen",
            "--group",
            "eval",
            "adk",
            "eval",
            eval_dir,
            f"{evalset}:{eval_case_id}",
            "--config_file_path",
            config,
            "--print_detailed_results",
        ]
        completed = subprocess.run(
            command,
            cwd=AGENT_DIR,
            env=env,
            check=False,
            stderr=subprocess.STDOUT,
            stdout=subprocess.PIPE,
            text=True,
        )
        if completed.stdout:
            print(completed.stdout, end="" if completed.stdout.endswith("\n") else "\n")

        try:
            result_path = _latest_result(history_dir, before)
            result_ok = _summarize_result(eval_name, result_path)
        except RuntimeError as exc:
            print(f"{eval_name}:{eval_case_id}: {exc}", file=sys.stderr)
            result_ok = False

        if completed.returncode == 0 and result_ok:
            return True

        should_retry = _is_transient_output(completed.stdout or "")
        if not should_retry or attempt == max_attempts:
            return False

        delay_seconds = retry_base_delay_seconds * attempt
        print(
            f"{eval_name}:{eval_case_id}: transient model error detected; "
            f"retrying in {delay_seconds:g}s..."
        )
        time.sleep(delay_seconds)

    return False


def _run_eval(eval_name: str, eval_case_ids: list[str] | None = None) -> bool:
    eval_dir, evalset, config = EVALS[eval_name]
    if eval_case_ids is None:
        eval_case_ids = _eval_case_ids(AGENT_DIR / evalset)
    max_attempts = _env_int("ADK_EVAL_MAX_ATTEMPTS", 2)
    case_delay_seconds = _env_float("ADK_EVAL_CASE_DELAY_SECONDS", 1.0)
    retry_base_delay_seconds = _env_float("ADK_EVAL_RETRY_BASE_DELAY_SECONDS", 10.0)

    all_ok = True
    for index, eval_case_id in enumerate(eval_case_ids):
        all_ok = (
            _run_eval_case(
                eval_name=eval_name,
                eval_dir=eval_dir,
                evalset=evalset,
                config=config,
                eval_case_id=eval_case_id,
                max_attempts=max_attempts,
                retry_base_delay_seconds=retry_base_delay_seconds,
            )
            and all_ok
        )
        if index < len(eval_case_ids) - 1 and case_delay_seconds:
            print(f"waiting {case_delay_seconds:g}s before the next eval case...")
            time.sleep(case_delay_seconds)

    return all_ok


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
    parser.add_argument(
        "--profile",
        choices=("quick", "full"),
        default="full",
        help="Eval profile. quick runs one representative case per agent.",
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
        profile_case_ids = None
        if args.profile == "quick":
            profile_case_ids = list(QUICK_EVAL_CASES[eval_name])
        print(f"running {eval_name} ({args.profile})...")
        all_ok = _run_eval(eval_name, profile_case_ids) and all_ok

    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
