from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Dict, Any
import os
import time
import uuid

from .env_utils import load_env_from_root

try:
    from volcenginesdkcore.rest import ApiException
except Exception:  # SDK 未安装时兜底
    ApiException = Exception  # type: ignore


@dataclass
class ResultItem:
    case: str
    status: str
    timestamp: str
    duration_ms: int
    reason: str
    video: str
    screenshot: List[str] = field(default_factory=list)
    in_tokens: Optional[int] = None
    out_tokens: Optional[int] = None
    original_dimensions: Optional[List[int]] = None
    screenshot_dimensions: Optional[List[int]] = None
    aosp_version: Optional[str] = None
    image_name: Optional[str] = None
    image_id: Optional[str] = None
    pod_id: Optional[str] = None
    run_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "case": self.case,
            "status": self.status,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "reason": self.reason,
            "video": self.video,
        }
        if self.screenshot:
            data["screenshot"] = list(self.screenshot)
        if self.in_tokens is not None:
            data["in_tokens"] = self.in_tokens
        if self.out_tokens is not None:
            data["out_tokens"] = self.out_tokens
        if self.original_dimensions is not None:
            data["original_dimensions"] = self.original_dimensions
        if self.screenshot_dimensions is not None:
            data["screenshot_dimensions"] = self.screenshot_dimensions
        if self.aosp_version is not None:
            data["AospVersion"] = self.aosp_version
        if self.image_name is not None:
            data["ImageName"] = self.image_name
        if self.image_id is not None:
            data["ImageId"] = self.image_id
        if self.pod_id:
            data["pod_id"] = self.pod_id
        if self.run_id:
            data["run_id"] = self.run_id
        return data


class MobileUseClient:
    def __init__(self, pod_id: Optional[str] = None) -> None:
        self._load_env()
        self.access_key = os.environ.get("VOLC_ACCESSKEY", "")
        self.secret_key = os.environ.get("VOLC_SECRETKEY", "")
        self.host = os.environ.get("VOLC_HOST", "")

        self.service_name = "ipaas"
        self.region = "cn-north-1"
        self.api_version = "2023-08-01"

        self._sdk_cache: Optional[tuple[Any, Any, Any]] = None
        self._pod_info_cache: Dict[str, Dict[str, Optional[str]]] = {}

        self.product_id = os.environ.get("PRODUCT_ID", "")
        self.pod_id_list = [s.strip() for s in os.environ.get("POD_ID_LIST", "").split(",") if s.strip()]
        self.pod_id = pod_id or (self.pod_id_list[0] if self.pod_id_list else "")

        self.tos_bucket = os.environ.get("TOS_BUCKET", "")
        self.tos_endpoint = os.environ.get("TOS_ENDPOINT", "")
        self.tos_region = os.environ.get("TOS_REGION", "")

    def _load_env(self) -> None:
        # 统一复用 env_utils 的 .env 加载逻辑（会自动去掉外层引号，且默认不覆盖已有环境变量）
        try:
            root = Path(__file__).resolve().parent.parent
            load_env_from_root(root)
        except Exception:
            return

    def _sdk(self):
        if self._sdk_cache is not None:
            return self._sdk_cache

        try:
            import volcenginesdkcore
        except Exception:
            self._sdk_cache = (None, None, None)
            return self._sdk_cache

        configuration = volcenginesdkcore.Configuration()
        configuration.host = self.host
        configuration.ak = self.access_key
        configuration.sk = self.secret_key
        configuration.region = self.region

        api_client = volcenginesdkcore.ApiClient(configuration)

        api = volcenginesdkcore.UniversalApi(api_client)
        self._sdk_cache = (volcenginesdkcore, api, configuration)
        return self._sdk_cache

    def _wrap_ok(self, *, action: str, result: Any) -> Dict[str, Any]:
        if isinstance(result, dict):
            return {"ResponseMetadata": {"Action": action}, "Result": result}
        return {"ResponseMetadata": {"Action": action}, "Result": {"data": result}}

    def _wrap_error(self, *, action: str, err: Exception) -> Dict[str, Any]:
        return {
            "ResponseMetadata": {
                "Action": action,
                "Error": {"Message": str(err)},
            }
        }

    def _do_call_universal(
        self,
        *,
        method: str,
        action: str,
        body: Dict[str, Any],
        service: Optional[str] = None,
        version: Optional[str] = None,
    ) -> Dict[str, Any]:
        sdk, api, _ = self._sdk()
        if not sdk or not api:
            return self._wrap_error(action=action, err=RuntimeError("volcenginesdkcore 不可用/未安装或 AKSK 未配置"))

        try:
            request_body = sdk.Flatten(body).flat()
            info = sdk.UniversalInfo(
                method=method,
                action=action,
                service=service or self.service_name,
                version=version or self.api_version,
                content_type="application/json",
            )
            resp = api.do_call(info, request_body)
            return self._wrap_ok(action=action, result=resp)
        except ApiException as e:
            return self._wrap_error(action=action, err=e)
        except Exception as e:
            return self._wrap_error(action=action, err=e)

    def run_agent_task_one_step(self, params: Dict[str, Any]) -> str:
        body = params.copy()
        if "ProductId" not in body and self.product_id:
            body["ProductId"] = self.product_id
        if "PodId" not in body and self.pod_id:
            body["PodId"] = self.pod_id
        if "RunName" not in body:
            body["RunName"] = "mobile-use one-step"
        if "ThreadId" not in body:
            body["ThreadId"] = str(uuid.uuid4())

        resp = self._do_call_universal(method="POST", action="RunAgentTaskOneStep", body=body)
        result = resp.get("Result") or {}
        if isinstance(result, dict):
            return str(result.get("RunId") or "")
        return ""

    def run_agent_task(self, params: Dict[str, Any]) -> str:
        body = params.copy()
        if "ProductId" not in body and self.product_id:
            body["ProductId"] = self.product_id
        if "PodId" not in body and self.pod_id:
            body["PodId"] = self.pod_id
        if "RunName" not in body:
            body["RunName"] = "mobile-use run"
        if "ThreadId" not in body:
            body["ThreadId"] = str(uuid.uuid4())

        resp = self._do_call_universal(method="POST", action="RunAgentTask", body=body)
        result = resp.get("Result") or {}
        if isinstance(result, dict):
            return str(result.get("RunId") or "")
        return ""

    # 获取指定任务的最终运行结果（原始结构：ResponseMetadata + Result）
    def get_agent_result_raw(self, run_id: str, is_detail: bool = True) -> Dict[str, Any]:
        if not run_id:
            return {}
        return self._do_call_universal(
            method="GET",
            action="GetAgentResult",
            body={"RunId": run_id, "IsDetail": is_detail},
        )

    # 获取指定任务的当前运行状态（原始结构：ResponseMetadata + Result）
    def list_agent_run_task_raw(
        self,
        run_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        pod_id: Optional[str] = None,
        status: Optional[int] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if run_id:
            params["RunId"] = run_id
        if thread_id:
            params["ThreadId"] = thread_id
        if pod_id:
            params["PodId"] = pod_id
        if status is not None:
            params["Status"] = status
        if limit is not None:
            params["Limit"] = limit
        if offset is not None:
            params["Offset"] = offset

        return self._do_call_universal(method="GET", action="ListAgentRunTask", body=params)

    def _get_pod_image_info(self, pod_id: Optional[str]) -> Dict[str, Optional[str]]:
        if not pod_id:
            return {"aosp_version": None, "image_name": None, "image_id": None}

        cached = self._pod_info_cache.get(pod_id)
        if cached is not None:
            return cached

        def _as_str(v: Any) -> Optional[str]:
            if v is None:
                return None
            s = str(v).strip()
            return s or None

        info: Dict[str, Optional[str]] = {"aosp_version": None, "image_name": None, "image_id": None}

        try:
            resp = self.list_pod_raw(pod_id_list=[pod_id])
            result = resp.get("Result") if isinstance(resp, dict) else None
            if isinstance(result, dict):
                rows = result.get("Row")
                if isinstance(rows, list) and rows:
                    row: Optional[Dict[str, Any]] = None
                    for r in rows:
                        if isinstance(r, dict) and str(r.get("PodId") or "") == pod_id:
                            row = r
                            break
                    if row is None:
                        first = rows[0]
                        if isinstance(first, dict):
                            row = first

                    if row is not None:
                        info = {
                            "aosp_version": _as_str(row.get("AospVersion")),
                            "image_name": _as_str(row.get("ImageName")),
                            "image_id": _as_str(row.get("ImageId")),
                        }
        except Exception:
            pass

        self._pod_info_cache[pod_id] = info
        return info

    # 获取任务的最终运行结果入口（用于生成 results.json）
    def get_agent_result(
        self,
        run_id: str,
        case: str,
        started_at_ms: Optional[int] = None,
        pod_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        now = int(time.time() * 1000)
        duration = 0 if started_at_ms is None else max(0, now - started_at_ms)
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        sdk, _, _ = self._sdk()
        if not sdk:
            item = ResultItem(
                case=case,
                status="fail",
                timestamp=ts,
                duration_ms=duration,
                reason="volcenginesdkcore 不可用/未安装或 AKSK 未配置",
                video="",
                pod_id=pod_id or self.pod_id or None,
                run_id=run_id or None,
            )
            return [item.to_dict()]

        if not run_id:
            item = ResultItem(
                case=case,
                status="fail",
                timestamp=ts,
                duration_ms=duration,
                reason="RunId 为空",
                video="",
                pod_id=pod_id or self.pod_id or None,
                run_id=None,
            )
            return [item.to_dict()]

        resp = self.get_agent_result_raw(run_id)

        status = "pass"
        reason = ""
        screenshot_urls: List[str] = []
        in_tokens: Optional[int] = None
        out_tokens: Optional[int] = None
        original_dimensions: Optional[List[int]] = None
        screenshot_dimensions: Optional[List[int]] = None
        recording_url: Optional[str] = None

        if isinstance(resp, dict):
            meta = resp.get("ResponseMetadata") or {}
            err = meta.get("Error") if isinstance(meta, dict) else None
            if err:
                status = "fail"
                if isinstance(err, dict):
                    reason = str(err.get("Message") or err)
                else:
                    reason = str(err)

            # 任务顶层 RecordingUrl（示例中在 Result 外层）
            ru = resp.get("RecordingUrl")
            if isinstance(ru, str) and ru.strip():
                recording_url = ru.strip()

            result = resp.get("Result") or {}
            if isinstance(result, dict):
                is_success = result.get("IsSuccess")
                if is_success in (0, "0"):
                    status = "fail"
                    if not reason:
                        reason = str(result.get("Content") or "任务失败")

                screenshots = result.get("ScreenShots")
                if isinstance(screenshots, dict) and screenshots:
                    first_item: Optional[Dict[str, Any]] = None
                    seen: set[str] = set()

                    # 收集所有 screenshot / original_screenshot URL
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
                        od = first_item.get("original_dimensions")
                        sd = first_item.get("screenshot_dimensions")

                        def _dims_to_list(val: Any) -> Optional[List[int]]:
                            if isinstance(val, (list, tuple)) and len(val) == 2:
                                a, b = val
                                try:
                                    return [int(a), int(b)]
                                except Exception:
                                    return None
                            return None

                        tmp_od = _dims_to_list(od)
                        if tmp_od is not None:
                            original_dimensions = tmp_od

                        tmp_sd = _dims_to_list(sd)
                        if tmp_sd is not None:
                            screenshot_dimensions = tmp_sd

                usage = result.get("Usage")
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

        video = ""
        if isinstance(recording_url, str) and recording_url.strip():
            video = recording_url.strip()
        effective_pod_id = pod_id or self.pod_id or None
        pod_info = self._get_pod_image_info(effective_pod_id)

        item = ResultItem(
            case=case,
            status=status,
            timestamp=ts,
            duration_ms=duration,
            reason=reason,
            video=video,
            screenshot=screenshot_urls,
            in_tokens=in_tokens,
            out_tokens=out_tokens,
            original_dimensions=original_dimensions,
            screenshot_dimensions=screenshot_dimensions,
            aosp_version=pod_info.get("aosp_version"),
            image_name=pod_info.get("image_name"),
            image_id=pod_info.get("image_id"),
            pod_id=effective_pod_id,
            run_id=run_id or None,
        )
        return [item.to_dict()]

    def list_pod_raw(self, *, pod_id_list: List[str], product_id: Optional[str] = None) -> Dict[str, Any]:
        """ListPod: 查询多个 Pod 信息。

        - Query: Action=ListPod&Version=2025-05-01
        - Body: ProductId, PodIdList
        - Service: ACEP
        """
        if not pod_id_list:
            return self._wrap_error(action="ListPod", err=ValueError("PodIdList 为空"))

        pid = product_id or self.product_id
        if not pid:
            return self._wrap_error(action="ListPod", err=ValueError("ProductId 为空"))

        body: Dict[str, Any] = {
            "ProductId": pid,
            "PodIdList": pod_id_list,
        }

        return self._do_call_universal(
            method="POST",
            action="ListPod",
            body=body,
            service="ACEP",
            version="2025-05-01",
        )