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


def _error_resp(*, action: str, message: str, service: str, version: str, err_type: str = "RuntimeError") -> Dict[str, Any]:
    return {
        "Result": None,
        "Error": {
            "Type": str(err_type or "RuntimeError"),
            "Message": str(message),
            "Action": str(action or ""),
            "Service": str(service or ""),
            "Version": str(version or ""),
        },
    }


def _coerce_is_success_code(val: Any) -> Optional[int]:
    if val is None:
        return None
    if isinstance(val, bool):
        return 1 if val else 0
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        s = val.strip()
        if s.isdigit():
            try:
                return int(s)
            except Exception:
                return None
    return None


@dataclass
class ResultItem:
    case: str
    status: str
    timestamp: str
    duration_ms: int
    reason: str

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
        resolved_service = service or self.service_name
        resolved_version = version or self.api_version

        if not sdk or not api:
            return _error_resp(
                action=action,
                message="volcenginesdkcore 不可用/未安装或 AKSK 未配置",
                service=resolved_service,
                version=resolved_version,
                err_type="RuntimeError",
            )

        try:
            request_body = sdk.Flatten(body).flat()
            info = sdk.UniversalInfo(
                method=method,
                action=action,
                service=resolved_service,
                version=resolved_version,
                content_type="application/json",
            )
            resp = api.do_call(info, request_body)
            if isinstance(resp, dict):
                return resp
            return {"Result": resp}
        except ApiException as e:
            return _error_resp(
                action=action,
                message=str(e),
                service=resolved_service,
                version=resolved_version,
                err_type=type(e).__name__,
            )
        except Exception as e:
            return _error_resp(
                action=action,
                message=str(e),
                service=resolved_service,
                version=resolved_version,
                err_type=type(e).__name__,
            )

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
        if isinstance(resp, dict) and resp.get("Error"):
            return ""

        payload: Any = None
        if isinstance(resp, dict):
            payload = resp.get("Result") if isinstance(resp.get("Result"), dict) else resp

        if isinstance(payload, dict):
            return str(payload.get("RunId") or "")

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
        if isinstance(resp, dict) and resp.get("Error"):
            return ""

        payload: Any = None
        if isinstance(resp, dict):
            payload = resp.get("Result") if isinstance(resp.get("Result"), dict) else resp

        if isinstance(payload, dict):
            return str(payload.get("RunId") or "")

        return ""

    def get_agent_result_raw(self, run_id: str, is_detail: bool = True) -> Dict[str, Any]:
        if not run_id:
            return _error_resp(
                action="GetAgentResult",
                message="RunId 为空",
                service=self.service_name,
                version=self.api_version,
                err_type="ValueError",
            )
        return self._do_call_universal(
            method="GET",
            action="GetAgentResult",
            body={"RunId": run_id, "IsDetail": is_detail},
        )

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

    def list_agent_run_current_step_raw(
        self,
        *,
        run_id: str,
        thread_id: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not run_id:
            return _error_resp(
                action="ListAgentRunCurrentStep",
                message="RunId 为空",
                service=self.service_name,
                version=self.api_version,
                err_type="ValueError",
            )

        params: Dict[str, Any] = {"RunId": run_id}
        if thread_id:
            params["ThreadId"] = thread_id
        if limit is not None:
            params["Limit"] = limit
        if offset is not None:
            params["Offset"] = offset

        return self._do_call_universal(method="GET", action="ListAgentRunCurrentStep", body=params)

    def cancel_task_raw(self, run_id: str) -> Dict[str, Any]:
        if not run_id:
            return _error_resp(
                action="CancelTask",
                message="RunId 为空",
                service=self.service_name,
                version=self.api_version,
                err_type="ValueError",
            )
        return self._do_call_universal(method="POST", action="CancelTask", body={"RunId": run_id})
    
    def _get_pod_image_info(self, pod_id: Optional[str]) -> Dict[str, Optional[str]]:
        """Pod 信息查询：仅使用 DetailPod（按你的要求）。"""
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
            resp = self.detail_pod_raw(product_id=self.product_id or None, pod_id=pod_id)

            if not isinstance(resp, dict) or resp.get("Error"):
                self._pod_info_cache[pod_id] = info
                return info

            payload: Any = None
            if isinstance(resp.get("Result"), dict):
                payload = resp.get("Result")
            elif any(k in resp for k in ("pod_id", "product_id", "image_id", "aosp_version")):
                payload = resp

            if isinstance(payload, dict):
                info = {
                    "aosp_version": _as_str(payload.get("aosp_version") or payload.get("AospVersion")),
                    "image_name": _as_str(payload.get("image_name") or payload.get("ImageName")),
                    "image_id": _as_str(payload.get("image_id") or payload.get("ImageId")),
                }
        except Exception:
            pass

        self._pod_info_cache[pod_id] = info
        return info

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

        result: Any = None
        if isinstance(resp, dict):
            err = resp.get("Error")
            if err:
                status = "fail"
                if isinstance(err, dict):
                    reason = str(err.get("Message") or err)
                else:
                    reason = str(err)

            # 兼容两种结构：{"Result": {...}} 或 顶层 payload
            if "Result" in resp:
                result = resp.get("Result")
            elif any(k in resp for k in ("IsSuccess", "Content", "StructOutput", "ScreenShots", "Usage")):
                result = resp

            if result is None:
                if status == "pass":
                    status = "fail"
                    if not reason:
                        reason = "GetAgentResult 返回为空"
            elif isinstance(result, dict):
                code = _coerce_is_success_code(result.get("IsSuccess"))
                content = result.get("Content")
                content_msg = str(content) if isinstance(content, str) else ""

                # IsSuccess 枚举：
                # 0 NOT_COMPLETED
                # 1 SUCCESS
                # 2 EXEC_FAILED
                # 3 COMPLETED_BUT_NO_MESSAGE
                # 4 USER_INTERRUPT
                # 5 USER_CANCELLED
                # 6 UNKNOWN_ERROR
                if code is None:
                    if status == "pass":
                        status = "fail"
                    if not reason:
                        reason = "GetAgentResult IsSuccess 缺失/类型异常"
                elif code == 0:
                    if status == "pass":
                        status = "fail"
                    if not reason:
                        reason = "任务未完成（NOT_COMPLETED）"
                elif code in (1, 3):
                    pass
                elif code == 5:
                    status = "skip"
                    if not reason:
                        reason = content_msg or "用户取消（USER_CANCELLED）"
                else:
                    status = "fail"
                    if not reason:
                        reason = content_msg or f"任务失败（IsSuccess={code}）"
            else:
                if status == "pass":
                    status = "fail"
                    if not reason:
                        reason = "GetAgentResult Result 类型异常"

        if isinstance(result, dict):
            screenshots = result.get("ScreenShots")
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

        effective_pod_id = pod_id or self.pod_id or None
        pod_info = self._get_pod_image_info(effective_pod_id)

        item = ResultItem(
            case=case,
            status=status,
            timestamp=ts,
            duration_ms=duration,
            reason=reason,
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

    def detail_pod_raw(
        self,
        *,
        product_id: Optional[str] = None,
        pod_id: str,
        version: str = "2022-08-01",
    ) -> Dict[str, Any]:
        """DetailPod: 查询指定实例的详细信息。"""
        pid = (product_id or self.product_id or "").strip()
        if not pid:
            return _error_resp(
                action="DetailPod",
                message="ProductId 为空",
                service="ACEP",
                version=version,
                err_type="ValueError",
            )

        pod = str(pod_id or "").strip()
        if not pod:
            return _error_resp(
                action="DetailPod",
                message="PodId 为空",
                service="ACEP",
                version=version,
                err_type="ValueError",
            )

        # 按你给的请求示例：product_id / pod_id 使用小写
        params: Dict[str, Any] = {
            "product_id": pid,
            "pod_id": pod,
        }

        return self._do_call_universal(
            method="GET",
            action="DetailPod",
            body=params,
            service="ACEP",
            version=version,
        )