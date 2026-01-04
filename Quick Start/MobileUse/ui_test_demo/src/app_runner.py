from pathlib import Path
from datetime import datetime, timezone
from typing import Any
import json
import logging
import os
import time

from .case_runner import RunnerConfig, run_suite
from .env_utils import env_bool, load_env_from_root
from .system_prompt import SYSTEM_PROMPT


def init_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def prepare_dirs(root: Path) -> tuple[Path, Path] | None:
    cases_dir = root / "cases"
    results_dir = root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    if not cases_dir.exists():
        logging.warning(f"未找到用例目录: {cases_dir}")
        return None

    return cases_dir, results_dir


def build_runner_config_from_env() -> RunnerConfig:
    return RunnerConfig(
        timeout_s=int(float(os.environ.get("CASE_TIMEOUT_S") or "600")),
        poll_interval_s=float(os.environ.get("POLL_INTERVAL_S") or "2"),
        run_api=os.environ.get("RUN_API") or "one_step",
        use_status_api=env_bool("USE_STATUS_API", True),
        use_base64_screenshot=env_bool("USE_BASE64_SCREENSHOT", True),
        screen_record=env_bool("SCREEN_RECORD", False),
        exec_mode=(os.environ.get("EXEC_MODE") or "auto").strip().lower(),
    )


def format_duration_ms(duration_ms: int) -> str:
    duration_ms = max(0, int(duration_ms))
    total_seconds = duration_ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60

    if minutes <= 0:
        return f"{seconds}s"
    if seconds == 0:
        return f"{minutes}m"
    return f"{minutes}m{seconds}s"


def write_results(*, results_dir: Path, results: list[dict[str, Any]], duration_str: str) -> None:
    if not results:
        logging.info("无可写入的结果")
        return

    out_name = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + ".json"
    out_path = results_dir / out_name
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info(f"写入结果: {out_path}（{len(results)} 条，用时 {duration_str}）")


def run_suite_with_timing(*, root: Path, cases_dir: Path, cfg: RunnerConfig) -> tuple[list[dict[str, Any]], int]:
    started_ms = int(time.time() * 1000)
    results = run_suite(root=root, cases_dir=cases_dir, system_prompt=SYSTEM_PROMPT, cfg=cfg)
    duration_ms = int(time.time() * 1000) - started_ms
    return results, max(0, duration_ms)


def run_cli() -> None:
    """更简洁的任务执行入口（供 src.main 调用）。"""
    init_logging()

    root = get_project_root()
    load_env_from_root(root)

    dirs = prepare_dirs(root)
    if not dirs:
        return

    cases_dir, results_dir = dirs
    cfg = build_runner_config_from_env()

    results, duration_ms = run_suite_with_timing(root=root, cases_dir=cases_dir, cfg=cfg)
    write_results(results_dir=results_dir, results=results, duration_str=format_duration_ms(duration_ms))
