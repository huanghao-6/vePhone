from pathlib import Path
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, Optional, List
import argparse
import json
import logging
import os
import time

from .case_runner import RunnerConfig, discover_cases, run_suite
from .env_utils import env_bool, load_env_from_root
from .mobile_use import MobileUseClient
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
        poll_interval_s=float(os.environ.get("POLL_INTERVAL_S") or "2")
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


def _print_json(data: Any, *, pretty: bool) -> None:
    if pretty:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(data, ensure_ascii=False))


def _validate_env_via_detail_pod(*, pod_id: str) -> tuple[bool, Dict[str, Any], str]:
    """通过调用 DetailPod 校验环境变量是否有效（不依赖 ResponseMetadata）。

    规则：
    - PRODUCT_ID 必须存在
    - 对 pod_id_list 中的每个 PodId 调用一次 DetailPod
    - 若任一响应包含顶层 Error -> 失败
    - 结果 payload 支持两种结构：
      1) {"Result": {...}}
      2) {...}（payload 直接在顶层）
    - payload 中若包含 product_id/pod_id（或 ProductId/PodId）则必须与期望一致
    - 若 payload 中包含 image_id（或 ImageId）字段，则不允许为空（更严格）
    """
    client = MobileUseClient(pod_id=pod_id or None)

    expected_product_id = (getattr(client, "product_id", "") or "").strip()
    if not expected_product_id:
        return False, {}, "PRODUCT_ID 为空，无法校验 DetailPod"

    if pod_id:
        pod_id_list = [pod_id]
    else:
        pod_id_list = list(getattr(client, "pod_id_list", []) or [])

    pod_id_list = [str(x).strip() for x in pod_id_list if str(x).strip()]
    if not pod_id_list:
        return False, {}, "未指定 pod_id 且 POD_ID_LIST 为空，无法调用 DetailPod"

    print(f"校验环境变量 via DetailPod, product_id={expected_product_id}, pod_id_list={pod_id_list}")

    def _as_str(v: Any) -> str:
        return str(v or "").strip()

    def _extract_payload(resp: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(resp, dict):
            return None
        r = resp.get("Result")
        if isinstance(r, dict):
            return r
        if any(k in resp for k in ("pod_id", "PodId", "product_id", "ProductId")):
            return resp
        return None

    detail_map: Dict[str, Any] = {}
    for pid in pod_id_list:
        try:
            resp = client.detail_pod_raw(product_id=expected_product_id, pod_id=pid)
        except Exception as e:
            return False, {"DetailPod": detail_map}, f"DetailPod 调用异常 pod_id={pid}: {type(e).__name__}: {e}"

        detail_map[pid] = resp

        if not isinstance(resp, dict):
            return False, {"DetailPod": detail_map}, f"DetailPod 返回非 JSON 对象 pod_id={pid}"

        top_err = resp.get("Error")
        if top_err:
            if isinstance(top_err, dict):
                msg = str(top_err.get("Message") or top_err)
            else:
                msg = str(top_err)
            return False, {"DetailPod": detail_map}, f"DetailPod 返回错误 pod_id={pid}: {msg}"

        payload = _extract_payload(resp)
        if not isinstance(payload, dict):
            return False, {"DetailPod": detail_map}, f"DetailPod 响应缺少 Result/payload pod_id={pid}"

        got_pid = _as_str(payload.get("pod_id") or payload.get("PodId") or payload.get("podId"))
        if got_pid and got_pid != pid:
            return (
                False,
                {"DetailPod": detail_map},
                f"DetailPod 返回的 pod_id 与请求不一致: req={pid}, resp={got_pid}",
            )

        got_product = _as_str(payload.get("product_id") or payload.get("ProductId") or payload.get("productId"))
        if got_product and got_product != expected_product_id:
            return (
                False,
                {"DetailPod": detail_map},
                f"DetailPod 返回的 product_id 与 env PRODUCT_ID 不一致: env={expected_product_id}, resp={got_product}",
            )

        if "image_id" in payload and not _as_str(payload.get("image_id")):
            return False, {"DetailPod": detail_map}, f"DetailPod 返回 image_id 为空 pod_id={pid}"
        if "ImageId" in payload and not _as_str(payload.get("ImageId")):
            return False, {"DetailPod": detail_map}, f"DetailPod 返回 ImageId 为空 pod_id={pid}"

    return True, {"DetailPod": detail_map}, ""


def _write_jsonl_line(fp, obj: Any) -> None:
    fp.write(json.dumps(obj, ensure_ascii=False) + "\n")
    fp.flush()


def _load_results_from_jsonl(*, jsonl_path: Path) -> tuple[Dict[str, Any], list[Dict[str, Any]]]:
    meta: Dict[str, Any] = {}
    items: list[Dict[str, Any]] = []

    if not jsonl_path.exists():
        return meta, items

    with jsonl_path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if isinstance(obj, dict) and "__meta__" in obj and isinstance(obj.get("__meta__"), dict):
                meta = obj.get("__meta__") or {}
                continue
            if isinstance(obj, dict):
                items.append(obj)

    return meta, items


def _find_latest_jsonl(*, results_dir: Path) -> Optional[Path]:
    if not results_dir.exists():
        return None
    candidates = sorted(results_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _read_jsonl_meta_and_done_count(*, jsonl_path: Path) -> tuple[Dict[str, Any], int]:
    """
    进度统计：只解析 __meta__，其余行只计数（不解析结果内容）。
    - done = 非空行总数 - meta行（如果存在）
    """
    meta: Dict[str, Any] = {}
    total_non_empty_lines = 0
    meta_found = False

    if not jsonl_path.exists():
        return meta, 0

    with jsonl_path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue

            total_non_empty_lines += 1

            if not meta_found:
                try:
                    obj = json.loads(line)
                except Exception:
                    obj = None

                if isinstance(obj, dict) and "__meta__" in obj and isinstance(obj.get("__meta__"), dict):
                    meta = obj.get("__meta__") or {}
                    meta_found = True

    done = total_non_empty_lines - (1 if meta_found else 0)
    if done < 0:
        done = 0
    return meta, done


def run_suite_with_timing(
    *,
    root: Path,
    cases_dir: Path,
    cfg: RunnerConfig,
    on_result: Any = None,
) -> tuple[list[dict[str, Any]], int]:
    started_ms = int(time.time() * 1000)
    results = run_suite(root=root, cases_dir=cases_dir, system_prompt=SYSTEM_PROMPT, cfg=cfg, on_result=on_result)
    duration_ms = int(time.time() * 1000) - started_ms
    return results, max(0, duration_ms)

# 执行测试用例
def _cmd_run(*, root: Path) -> None:
    dirs = prepare_dirs(root)
    if not dirs:
        return

    cases_dir, results_dir = dirs
    cfg = build_runner_config_from_env()

    ok, resp, err_msg = _validate_env_via_detail_pod(pod_id="")
    if not ok:
        logging.error(f"环境变量异常：{err_msg}")
        logging.error("DetailPod 校验返回（用于排查）：")
        logging.error(json.dumps(resp, ensure_ascii=False, indent=2))
        raise SystemExit(2)
    logging.info("环境变量校验 via DetailPod 成功")
    out_base = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    jsonl_path = results_dir / f"{out_base}.jsonl"
    json_path = results_dir / f"{out_base}.json"

    cases = discover_cases(cases_dir)
    case_order: Dict[str, int] = {str(c.path.relative_to(root)): c.index for c in cases}

    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    meta_obj = {
        "__meta__": {
            "created_at": started_at,
            "total_cases": len(cases),
            "cases_dir": str(cases_dir),
        }
    }

    logging.info(f"增量落盘: {jsonl_path}")

    jsonl_fp = jsonl_path.open("w", encoding="utf-8")
    try:
        _write_jsonl_line(jsonl_fp, meta_obj)

        jsonl_lock = Lock()

        def _on_result(res: Dict[str, Any]) -> None:
            with jsonl_lock:
                _write_jsonl_line(jsonl_fp, res)

        _, duration_ms = run_suite_with_timing(root=root, cases_dir=cases_dir, cfg=cfg, on_result=_on_result)
    finally:
        try:
            jsonl_fp.close()
        except Exception:
            pass

    _, items = _load_results_from_jsonl(jsonl_path=jsonl_path)
    items.sort(key=lambda it: case_order.get(str(it.get("case") or ""), 10**9))
    json_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")

    logging.info(f"写入结果: {json_path}（{len(items)} 条，用时 {format_duration_ms(duration_ms)}）")


def _cmd_validate_env(*, root: Path, pod_id: str, pretty: bool) -> None:
    ok, resp, err_msg = _validate_env_via_detail_pod(pod_id=pod_id)

    detail_payload: Any = resp
    if isinstance(resp, dict) and "DetailPod" in resp:
        detail_payload = resp.get("DetailPod")

    out: Dict[str, Any] = {
        "ok": ok,
        "error_message": err_msg if not ok else "",
        "DetailPod": detail_payload,
    }
    _print_json(out, pretty=pretty)
    if not ok:
        logging.error("环境变量校验 via DetailPod 失败")
        raise SystemExit(2)
    else:
        logging.info("环境变量校验 via DetailPod 成功\n")


def _cmd_query_run_id(
    *,
    root: Path,
    run_id: str,
    is_detail: bool,
    pretty: bool,
    result_only: bool,
    step_only: bool,
) -> None:
    if step_only and result_only:
        raise ValueError("--step-only 与 --result-only 不能同时使用")

    client = MobileUseClient()

    out: Dict[str, Any] = {"RunId": run_id}

    if not result_only:
        out["ListAgentRunCurrentStep"] = client.list_agent_run_current_step_raw(run_id=run_id)

    if not step_only:
        out["GetAgentResult"] = client.get_agent_result_raw(run_id=run_id, is_detail=is_detail)

    _print_json(out, pretty=pretty)


def _cmd_cancel_run_id(*, root: Path, run_id: str, pretty: bool) -> None:
    client = MobileUseClient()
    out = client.cancel_task_raw(run_id)
    _print_json(out, pretty=pretty)


def _cmd_progress(*, root: Path, jsonl: str, pretty: bool, watch: bool, interval_s: float) -> None:
    results_dir = root / "results"
    jsonl_path = Path(jsonl) if jsonl else _find_latest_jsonl(results_dir=results_dir)

    if not jsonl_path or not jsonl_path.exists():
        raise SystemExit("未找到 results/*.jsonl，请先运行一次 run（开启增量落盘）")

    while True:
        meta, done = _read_jsonl_meta_and_done_count(jsonl_path=jsonl_path)

        total_raw = meta.get("total_cases") if isinstance(meta, dict) else None
        try:
            total = int(total_raw) if total_raw is not None else None
        except Exception:
            total = None

        percent = None
        if total and total > 0:
            percent = round(done / total * 100.0, 2)

        out: Dict[str, Any] = {
            "jsonl": str(jsonl_path),
            "meta": meta,
            "done": done,
            "total": total,
            "percent": percent,
        }
        _print_json(out, pretty=pretty)

        if not watch:
            return

        time.sleep(max(0.2, float(interval_s)))


def run_cli() -> None:
    """任务执行入口（供 src.main 调用）。

    支持：
    - run：执行用例（默认，会先校验环境变量；增量写 JSONL，结束生成 JSON 数组）
    - validate-env：校验环境变量是否有效（调用 DetailPod）
    - query：查询指定 RunId 的状态/结果
    - cancel：取消指定 RunId
    - progress：查询 JSONL 当前进度（done/total）
    """
    init_logging()

    root = get_project_root()
    load_env_from_root(root)

    parser = argparse.ArgumentParser(prog="ui_test_demo", add_help=True)
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("run", help="执行用例套件（默认）：先校验环境变量；增量写 JSONL；结束生成 results/*.json")

    p_validate = sub.add_parser("validate-env", help="校验环境变量是否有效（调用一次 DetailPod）")
    p_validate.add_argument("--pod-id", default="", help="可选：PodId（用于指定要校验的单个 PodId）")
    p_validate.add_argument("--pretty", action="store_true", help="以缩进 JSON 输出")

    p_query = sub.add_parser("query", help="query：查询指定 RunId 的当前步骤/结果")
    p_query.add_argument("run_id", help="要查询的 RunId")
    p_query.add_argument("--no-detail", action="store_true", help="GetAgentResult: IsDetail=false")
    p_query.add_argument("--pretty", action="store_true", help="以缩进 JSON 输出")
    p_query.add_argument("--result-only", action="store_true", help="只调用 GetAgentResult")
    p_query.add_argument("--step-only", action="store_true", help="只调用 ListAgentRunCurrentStep")
    
    p_cancel = sub.add_parser("cancel", help="取消指定 RunId")
    p_cancel.add_argument("run_id", help="要取消的 RunId")
    p_cancel.add_argument("--pretty", action="store_true", help="以缩进 JSON 输出")

    p_progress = sub.add_parser("progress", help="查询增量落盘 JSONL 的当前进度（done/total）")
    p_progress.add_argument("--jsonl", default="", help="可选：指定 results/*.jsonl 路径；默认取最新的一个")
    p_progress.add_argument("--pretty", action="store_true", help="以缩进 JSON 输出")
    p_progress.add_argument("--watch", action="store_true", help="持续刷新输出")
    p_progress.add_argument("--interval", default="1", help="watch 模式刷新间隔（秒），默认 1")

    args = parser.parse_args()
    cmd = args.cmd or "run"

    if cmd == "run":
        _cmd_run(root=root)
        return

    if cmd == "validate-env":
        _cmd_validate_env(
            root=root,
            pod_id=str(getattr(args, "pod_id", "") or ""),
            pretty=bool(getattr(args, "pretty", False)),
        )
        return

    if cmd == "query":
        _cmd_query_run_id(
            root=root,
            run_id=str(args.run_id),
            is_detail=not bool(getattr(args, "no_detail", False)),
            pretty=bool(getattr(args, "pretty", False)),
            step_only=bool(getattr(args, "step_only", False)),
            result_only=bool(getattr(args, "result_only", False)),
        )
        return

    if cmd == "cancel":
        _cmd_cancel_run_id(root=root, run_id=str(args.run_id), pretty=bool(getattr(args, "pretty", False)))
        return

    if cmd == "progress":
        interval_raw = getattr(args, "interval", "1") or "1"
        try:
            interval_s = float(interval_raw)
        except Exception:
            interval_s = 1.0

        _cmd_progress(
            root=root,
            jsonl=str(getattr(args, "jsonl", "") or ""),
            pretty=bool(getattr(args, "pretty", False)),
            watch=bool(getattr(args, "watch", False)),
            interval_s=interval_s,
        )
        return

    raise ValueError(f"未知命令: {cmd}")
