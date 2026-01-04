from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from queue import Queue
from threading import Lock, Thread
from typing import Any, Dict, List, Optional, Tuple
import json
import logging
import os
import re
import time
import uuid

from .env_utils import load_env_from_root
from .mobile_use import MobileUseClient, ResultItem


@dataclass(frozen=True)
class CaseFile:
    index: int
    path: Path
    content: str


# 测试用例执行配置
@dataclass(frozen=True)
class RunnerConfig:
    timeout_s: int = 600
    poll_interval_s: float = 2.0
    run_api: str = "one_step"  # one_step | task
    use_status_api: bool = True
    use_base64_screenshot: bool = True
    screen_record: bool = False
    exec_mode: str = "auto"  # serial | parallel | auto


_STATUS_MAP: Dict[int, str] = {
    1: "created",  # 已创建
    2: "running",  # 运行中
    3: "completed",  # 已完成
    4: "cancelling",  # 取消中
    5: "cancelled",  # 已取消
    6: "failed",  # 已失败
    7: "interrupted",  # 已中断
}

_TERMINAL_STATUS: set[int] = {3, 5, 6, 7} # 已完成/已取消/已失败/已中断


def parse_pod_id_list(value: str) -> List[str]:
    return [s.strip() for s in (value or "").split(",") if s.strip()]


# 获取测试 case 文件列表（支持通过环境变量 CASE_FILTER 选择子集）
def discover_cases(cases_dir: Path) -> List[CaseFile]:
    patterns = ("*.md", "*.case")
    files: List[Path] = []
    for p in patterns:
        files.extend(cases_dir.rglob(p))

    files = sorted(f for f in files if f.is_file())

    raw_filter = os.environ.get("CASE_FILTER", "").strip()
    filters: List[str] = [s.strip() for s in raw_filter.split(",") if s.strip()] if raw_filter else []

    filtered: List[Path] = []
    for f in files:
        if f.name.startswith("."):
            continue
        if f.stem.lower() == "template":
            continue
        if filters:
            rel = str(f.relative_to(cases_dir))
            if not any(token in rel for token in filters):
                continue
        filtered.append(f)

    cases: List[CaseFile] = []
    for idx, path in enumerate(filtered):
        cases.append(CaseFile(index=idx, path=path, content=path.read_text(encoding="utf-8")))
    return cases


def _iso_now() -> str:
    bj_tz = timezone(timedelta(hours=8))
    return datetime.now(bj_tz).strftime("%Y-%m-%d %H:%M:%S")

def _is_done_by_get_result(resp: Dict[str, Any]) -> bool:
    if not isinstance(resp, dict) or not resp:
        return False

    meta = resp.get("ResponseMetadata") or {}
    if isinstance(meta, dict) and meta.get("Error"):
        return True

    result = resp.get("Result")
    if not isinstance(result, dict):
        return False

    if result.get("IsSuccess") in (0, 1, "0", "1"):
        return True

    return False


# 提取出回调结果中的截图URL（结果页会展示在 video 字段）
def _extract_screenshot_url(resp: Dict[str, Any]) -> str:
    result = (resp or {}).get("Result")
    if not isinstance(result, dict):
        return ""
    screenshots = result.get("ScreenShots")
    if not isinstance(screenshots, dict) or not screenshots:
        return ""
    first = next(iter(screenshots.values()))
    if not isinstance(first, dict):
        return ""
    url = first.get("screenshot") or first.get("original_screenshot")
    return url.strip() if isinstance(url, str) else ""

def _extract_status_from_list_agent_run_task(resp: Dict[str, Any], run_id: str) -> Optional[int]:
    if not isinstance(resp, dict) or not run_id:
        return None
    result = resp.get("Result")
    if not isinstance(result, dict):
        return None
    items = result.get("List")
    if not isinstance(items, list) or not items:
        return None

    for it in items:
        if not isinstance(it, dict):
            continue
        if str(it.get("RunId") or "") == str(run_id):
            status = it.get("Status")
            if isinstance(status, int):
                return status
            if isinstance(status, str) and status.isdigit():
                return int(status)

    first = items[0]
    if isinstance(first, dict):
        status = first.get("Status")
        if isinstance(status, int):
            return status
        if isinstance(status, str) and status.isdigit():
            return int(status)

    return None


def _coerce_case_status(val: Any) -> Optional[str]:
    if not isinstance(val, str):
        return None
    v = val.strip().lower()
    if v in {"pass", "fail", "skip"}:
        return v
    return None


def _extract_json_object(text: str, start_idx: int) -> Optional[str]:
    if not isinstance(text, str):
        return None
    if start_idx < 0 or start_idx >= len(text) or text[start_idx] != "{":
        return None

    depth = 0
    in_string = False
    escaped = False

    for i in range(start_idx, len(text)):
        ch = text[i]

        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return text[start_idx : i + 1]
            continue

    return None


def _try_parse_json_obj(text: str) -> Optional[Dict[str, Any]]:
    if not isinstance(text, str) or not text.strip():
        return None

    s = text.strip()

    # 1) 尝试直接 JSON 解析
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    # 2) 处理 content 中常见的转义形式：{\"status\":\"fail\"...}
    if '\\"' in s or "\\n" in s:
        s2 = s.replace('\\"', '"').replace("\\\\", "\\")
        try:
            obj = json.loads(s2)
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None

def _infer_case_status_reason_from_struct_output(struct_output: Any) -> Tuple[Optional[str], Optional[str]]:
    if isinstance(struct_output, dict):
        st = _coerce_case_status(struct_output.get("status") or struct_output.get("Status"))
        rs = struct_output.get("reason") or struct_output.get("Reason")
        reason = rs.strip() if isinstance(rs, str) and rs.strip() else None
        return st, reason

    if isinstance(struct_output, str) and struct_output.strip():
        obj = _try_parse_json_obj(struct_output)
        if isinstance(obj, dict):
            st = _coerce_case_status(obj.get("status") or obj.get("Status"))
            rs = obj.get("reason") or obj.get("Reason")
            reason = rs.strip() if isinstance(rs, str) and rs.strip() else None
            return st, reason

    return None, None


def _infer_case_status_reason_from_content(content: Any) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(content, str) or not content.strip():
        return None, None

    text = content.strip()

    # 1) 优先识别“最终状态：fail”这一类文本
    m = re.search(r"最终状态\s*[:：]\s*(pass|fail|skip)\b", text, flags=re.IGNORECASE)
    if m:
        return _coerce_case_status(m.group(1)), None

    # 2) 尝试解析 content 内嵌的结构化 JSON（通常包含 "status"/"reason"）
    start = text.rfind('{"status"')
    if start < 0:
        start = text.rfind('{\\"status\\"')

    if start >= 0:
        json_blob = _extract_json_object(text, start)
        if isinstance(json_blob, str) and json_blob.strip():
            obj = _try_parse_json_obj(json_blob)
            if isinstance(obj, dict):
                st = _coerce_case_status(obj.get("status") or obj.get("Status"))
                rs = obj.get("reason") or obj.get("Reason")
                reason = rs.strip() if isinstance(rs, str) and rs.strip() else None
                return st, reason

    # 3) 兜底：解析“失败原因：...”这一行，推断为 fail
    m2 = re.search(r"失败原因\s*[:：]\s*(.+)", text)
    if m2:
        return "fail", m2.group(1).strip() or None

    return None, None


def _infer_case_status_reason_from_result_payload(result_payload: Any) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(result_payload, dict):
        return None, None

    st, reason = _infer_case_status_reason_from_struct_output(result_payload.get("StructOutput"))
    if st:
        return st, reason

    return _infer_case_status_reason_from_content(result_payload.get("Content"))


def _result_from_resp(
    *,
    client: MobileUseClient,
    case_name: str,
    run_id: str,
    pod_id: Optional[str],
    started_at_ms: int,
    resp: Dict[str, Any],
    timeout: bool,
) -> Dict[str, Any]:
    finished_at_ms = int(time.time() * 1000)
    duration_ms = max(0, finished_at_ms - started_at_ms)

    status = "pass"
    reason = ""
    video = ""

    if timeout:
        status = "fail"
        reason = "等待任务完成超时"
    else:
        meta = (resp or {}).get("ResponseMetadata") or {}
        err = meta.get("Error") if isinstance(meta, dict) else None
        if err:
            status = "fail"
            reason = str(err.get("Message") or err)

        result = (resp or {}).get("Result") or {}
        if isinstance(result, dict):
            if result.get("IsSuccess") in (0, "0"):
                status = "fail"
                if not reason:
                    reason = str(result.get("Content") or "任务失败")

            video = _extract_screenshot_url(resp)

    in_tokens: Optional[int] = None
    out_tokens: Optional[int] = None

    screenshot_urls: List[str] = []

    result_payload = (resp or {}).get("Result")

    # 先从 Result.StructOutput / Result.Content 推断用例状态/原因
    inferred_status, inferred_reason = _infer_case_status_reason_from_result_payload(result_payload)
    if status == "pass" and inferred_status in {"fail", "skip"}:
        # SDK 认为成功，但用例结构化结果认为失败/跳过，以用例为准
        status = inferred_status
        if not reason and inferred_reason:
            reason = inferred_reason
    elif status == "fail" and not reason and inferred_reason:
        # 已经 fail 但没有具体原因，用结构化结果补充 reason
        reason = inferred_reason

    if isinstance(result_payload, dict):
        usage = result_payload.get("Usage")
        if isinstance(usage, dict):
            it = usage.get("in_tokens")
            ot = usage.get("out_tokens")
            if isinstance(it, int):
                in_tokens = it
            elif isinstance(it, str) and it.isdigit():
                in_tokens = int(it)
            if isinstance(ot, int):
                out_tokens = ot
            elif isinstance(ot, str) and ot.isdigit():
                out_tokens = int(ot)

    original_dimensions: Optional[List[int]] = None
    screenshot_dimensions: Optional[List[int]] = None

    def _dims_to_list(val: Any) -> Optional[List[int]]:
        if isinstance(val, (list, tuple)) and len(val) == 2:
            a, b = val
            try:
                return [int(a), int(b)]
            except Exception:
                return None
        return None

    if isinstance(result_payload, dict):
        screenshots = result_payload.get("ScreenShots")
        if isinstance(screenshots, dict) and screenshots:
            first_item: Optional[Dict[str, Any]] = None
            seen: set[str] = set()

            for _k, it in screenshots.items():
                if not isinstance(it, dict):
                    continue

                if first_item is None:
                    first_item = it

                v = it.get("screenshot") or it.get("original_screenshot")
                if isinstance(v, str) and v.strip():
                    url = v.strip()
                    if url not in seen:
                        seen.add(url)
                        screenshot_urls.append(url)

            # dimensions 只取第一个截图条目
            if first_item is not None:
                tmp = _dims_to_list(first_item.get("original_dimensions"))
                if tmp is not None:
                    original_dimensions = tmp

                tmp = _dims_to_list(first_item.get("screenshot_dimensions"))
                if tmp is not None:
                    screenshot_dimensions = tmp

    # video 优先取 RecordingUrl，其次回退到第一个 screenshot
    video_url = ""
    ru = (resp or {}).get("RecordingUrl")
    if not (isinstance(ru, str) and ru.strip()) and isinstance(result_payload, dict):
        ru = result_payload.get("RecordingUrl")

    if isinstance(ru, str) and ru.strip():
        v = ru.strip()
        if v.startswith("http://") or v.startswith("https://"):
            video_url = v
        else:
            video_url = "https://" + v.lstrip("/")
    else:
        video_url = screenshot_urls[0] if screenshot_urls else ""

    # Pod / 镜像信息保持不变
    aosp_version: Optional[str] = None
    image_name: Optional[str] = None
    image_id: Optional[str] = None
    try:
        helper = getattr(client, "_get_pod_image_info", None)
        effective_pod_id = pod_id or getattr(client, "pod_id", None)
        if callable(helper):
            pod_info = helper(effective_pod_id)
            if isinstance(pod_info, dict):
                aosp_version = pod_info.get("aosp_version")
                image_name = pod_info.get("image_name")
                image_id = pod_info.get("image_id")
    except Exception:
        pass

    item = ResultItem(
        case=case_name,
        status=status,
        timestamp=_iso_now(),
        duration_ms=duration_ms,
        reason=reason,
        video=video_url,
        screenshot=screenshot_urls,
        in_tokens=in_tokens,
        out_tokens=out_tokens,
        original_dimensions=original_dimensions,
        screenshot_dimensions=screenshot_dimensions,
        aosp_version=aosp_version,
        image_name=image_name,
        image_id=image_id,
        pod_id=pod_id,
        run_id=run_id,
    )
    data = item.to_dict()

    result_payload = (resp or {}).get("Result")
    if isinstance(result_payload, dict):
        content = result_payload.get("Content")
        if isinstance(content, str) and content.strip():
            data["content"] = content
        struct_output = result_payload.get("StructOutput")
        if struct_output not in (None, {}, []):
            data["struct_output"] = struct_output

    return data


# 运行单个测试用例
def run_one_case(
    *,
    client: MobileUseClient,
    case: CaseFile,
    root: Path,
    system_prompt: str,
    pod_id: str,
    product_id: str,
    cfg: RunnerConfig,
) -> Dict[str, Any]:
    started_at_ms = int(time.time() * 1000)
    case_name = str(case.path.relative_to(root))

    user_prompt = case.content.strip()
    if not user_prompt:
        aosp_version = None
        image_name = None
        image_id = None
        try:
            helper = getattr(client, "_get_pod_image_info", None)
            if callable(helper):
                pod_info = helper(pod_id)
                if isinstance(pod_info, dict):
                    aosp_version = pod_info.get("aosp_version")
                    image_name = pod_info.get("image_name")
                    image_id = pod_info.get("image_id")
        except Exception:
            pass

        return ResultItem(
            case=case_name,
            status="skip",
            timestamp=_iso_now(),
            duration_ms=0,
            reason="用例内容为空",
            video="",
            aosp_version=aosp_version,
            image_name=image_name,
            image_id=image_id,
            pod_id=pod_id,
            run_id=None,
        ).to_dict()

    params: Dict[str, Any] = {
        "RunName": case.path.stem,
        "PodId": pod_id,
        "ProductId": product_id,
        "UserPrompt": user_prompt,
        "SystemPrompt": system_prompt,
        "TosBucket": client.tos_bucket,
        "TosEndpoint": client.tos_endpoint,
        "TosRegion": client.tos_region,
        "UseBase64Screenshot": cfg.use_base64_screenshot,
        "IsScreenRecord": cfg.screen_record,
        "Timeout": cfg.timeout_s,
    }

    if cfg.run_api == "task":
        run_id = client.run_agent_task(params)
    else:
        run_id = client.run_agent_task_one_step(params)

    if not run_id:
        aosp_version = None
        image_name = None
        image_id = None
        try:
            helper = getattr(client, "_get_pod_image_info", None)
            if callable(helper):
                pod_info = helper(pod_id)
                if isinstance(pod_info, dict):
                    aosp_version = pod_info.get("aosp_version")
                    image_name = pod_info.get("image_name")
                    image_id = pod_info.get("image_id")
        except Exception:
            pass

        return ResultItem(
            case=case_name,
            status="fail",
            timestamp=_iso_now(),
            duration_ms=max(0, int(time.time() * 1000) - started_at_ms),
            reason="未获取到 RunId（RunAgentTask 调用失败）",
            video="",
            aosp_version=aosp_version,
            image_name=image_name,
            image_id=image_id,
            pod_id=pod_id,
            run_id=None,
        ).to_dict()

    deadline = time.monotonic() + max(1, int(cfg.timeout_s))
    poll_interval = max(0.5, float(cfg.poll_interval_s))

    last_resp: Dict[str, Any] = {}
    last_status: Optional[str] = None
    last_status_code: Optional[int] = None
    missing_status_polls = 0

    while True:
        # 1) 优先用 ListAgentRunTask 轮询任务状态；终态后再 GetAgentResult 获取最终结果
        if cfg.use_status_api:
            status_resp = client.list_agent_run_task_raw(run_id=run_id, pod_id=pod_id)
            status_code = _extract_status_from_list_agent_run_task(status_resp, run_id=run_id)

            if status_code is None:
                missing_status_polls += 1
            else:
                last_status_code = status_code
                last_status = _STATUS_MAP.get(status_code) or str(status_code)

                if status_code in _TERMINAL_STATUS:
                    final_resp = client.get_agent_result_raw(run_id)
                    if final_resp:
                        last_resp = final_resp

                    out = _result_from_resp(
                        client=client,
                        case_name=case_name,
                        run_id=run_id,
                        pod_id=pod_id,
                        started_at_ms=started_at_ms,
                        resp=final_resp or last_resp,
                        timeout=False,
                    )
                    out["task_status"] = last_status
                    out["task_status_code"] = status_code

                    # 终态兜底：状态接口明确失败/取消/中断时，强制覆盖为 fail/skip
                    if status_code == 5:
                        out["status"] = "skip"
                        if not out.get("reason"):
                            out["reason"] = "任务已取消"
                    elif status_code == 6:
                        out["status"] = "fail"
                        if not out.get("reason"):
                            out["reason"] = "任务已失败"
                    elif status_code == 7:
                        out["status"] = "fail"
                        if not out.get("reason"):
                            out["reason"] = "任务已中断"
                    else:
                        if not (final_resp or last_resp):
                            out["status"] = "fail"
                            out["reason"] = "任务已完成，但 GetAgentResult 返回为空"

                    return out

            # 兜底：状态接口长期拿不到数据时，偶尔探测一次 GetAgentResult，避免卡死
            if missing_status_polls > 0 and missing_status_polls % 5 == 0:
                probe = client.get_agent_result_raw(run_id)
                if probe:
                    last_resp = probe
                if _is_done_by_get_result(probe):
                    out = _result_from_resp(
                        client=client,
                        case_name=case_name,
                        run_id=run_id,
                        pod_id=pod_id,
                        started_at_ms=started_at_ms,
                        resp=probe,
                        timeout=False,
                    )
                    if last_status is not None:
                        out["task_status"] = last_status
                    if last_status_code is not None:
                        out["task_status_code"] = last_status_code
                    return out

        else:
            # 2) 未启用状态轮询时：只用 GetAgentResult 判断是否完成
            resp = client.get_agent_result_raw(run_id)
            if resp:
                last_resp = resp
            if _is_done_by_get_result(resp):
                out = _result_from_resp(
                    client=client,
                    case_name=case_name,
                    run_id=run_id,
                    pod_id=pod_id,
                    started_at_ms=started_at_ms,
                    resp=final_resp or last_resp,
                    timeout=False,
                )

        # 3) 超时退出
        if time.monotonic() >= deadline:
            out = _result_from_resp(
                client=client,
                case_name=case_name,
                run_id=run_id,
                pod_id=pod_id,
                started_at_ms=started_at_ms,
                resp=last_resp,
                timeout=True,
            )
            if last_status is not None:
                out["task_status"] = last_status
            if last_status_code is not None:
                out["task_status_code"] = last_status_code
            return out

        time.sleep(poll_interval)


# 运行测试用例
def run_suite(*, root: Path, cases_dir: Path, system_prompt: str, cfg: RunnerConfig) -> List[Dict[str, Any]]:
    load_env_from_root(root)
    pod_ids = parse_pod_id_list(os.environ.get("POD_ID_LIST", ""))
    cases = discover_cases(cases_dir)

    if not cases:
        logging.warning("未发现任何用例（*.md / *.case）")
        return []

    mode = (cfg.exec_mode or "auto").strip().lower()
    if mode not in {"auto", "serial", "parallel"}:
        logging.warning(f"EXEC_MODE={cfg.exec_mode} 不合法，回退到 auto")
        mode = "auto"

    # auto：pod<=1 串行；pod>1 并行
    if mode == "auto":
        mode = "parallel" if len(pod_ids) > 1 else "serial"

    def _run_case_safe(*, client: MobileUseClient, pod: str, c: CaseFile) -> Dict[str, Any]:
        logging.info(f"[pod={pod or 'N/A'}] 运行用例: {c.path.relative_to(root)}")
        try:
            return run_one_case(
                client=client,
                case=c,
                root=root,
                system_prompt=system_prompt,
                pod_id=pod,
                product_id=client.product_id,
                cfg=cfg,
            )
        except Exception as e:
            aosp_version = None
            image_name = None
            image_id = None
            try:
                helper = getattr(client, "_get_pod_image_info", None)
                effective_pod_id = pod or getattr(client, "pod_id", None)
                if callable(helper):
                    pod_info = helper(effective_pod_id)
                    if isinstance(pod_info, dict):
                        aosp_version = pod_info.get("aosp_version")
                        image_name = pod_info.get("image_name")
                        image_id = pod_info.get("image_id")
            except Exception:
                pass

            return ResultItem(
                case=str(c.path.relative_to(root)),
                status="fail",
                timestamp=_iso_now(),
                duration_ms=0,
                reason=f"执行异常: {type(e).__name__}: {e}",
                video="",
                screenshot=[],          # <== 改成空数组
                aosp_version=aosp_version,
                image_name=image_name,
                image_id=image_id,
                pod_id=pod or None,
                run_id=None,
            ).to_dict()

    # 串行执行：一个 pod 串行执行全部用例
    if mode == "serial":
        pod_id = pod_ids[0] if pod_ids else None
        logging.info(f"EXEC_MODE=serial，串行执行；pod={pod_id or 'N/A'}")
        client = MobileUseClient(pod_id=pod_id)

        results: List[Tuple[int, Dict[str, Any]]] = []
        for c in cases:
            results.append((c.index, _run_case_safe(client=client, pod=client.pod_id, c=c)))

        results.sort(key=lambda x: x[0])
        return [r for _, r in results]

    # 并行执行：pod_list 并发跑用例集，使用“强占队列”调度（不均分）
    if len(pod_ids) <= 1:
        logging.warning("EXEC_MODE=parallel 但 POD_ID_LIST<=1，回退到串行")
        pod_id = pod_ids[0] if pod_ids else None
        client = MobileUseClient(pod_id=pod_id)

        results: List[Tuple[int, Dict[str, Any]]] = []
        for c in cases:
            results.append((c.index, _run_case_safe(client=client, pod=client.pod_id, c=c)))

        results.sort(key=lambda x: x[0])
        return [r for _, r in results]

    logging.info(f"EXEC_MODE=parallel，POD_ID_LIST={len(pod_ids)}，并发执行；pods={pod_ids}")

    q: Queue[Optional[CaseFile]] = Queue()
    for c in cases:
        q.put(c)
    for _ in pod_ids:
        q.put(None)

    lock = Lock()
    results2: List[Tuple[int, Dict[str, Any]]] = []

    def worker(pod: str) -> None:
        client = MobileUseClient(pod_id=pod)
        while True:
            c = q.get()
            if c is None:
                return
            r = _run_case_safe(client=client, pod=client.pod_id, c=c)
            with lock:
                results2.append((c.index, r))

    threads = [Thread(target=worker, name=f"pod-worker-{pid}", args=(pid,), daemon=True) for pid in pod_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    results2.sort(key=lambda x: x[0])
    return [r for _, r in results2]