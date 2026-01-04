# 项目简介

主要功能包括：

- 从 `cases/` 目录读取 Markdown / `.case` 用例描述。
- 调用云端 Mobile Use / Cloud Phone 能力执行用例。
- 将每条用例执行结果写入 `results/*.json`。
- 通过本地打开 `results.html`，对结果进行汇总、筛查、排序与详情查看（含结构化 JSON 展示）。

---

## 快速开始

### 1. 安装 uv 并创建虚拟环境

> 推荐 Python 3.12，项目根目录下已有 `.python-version` 指定版本。

```bash
uv venv --python 3.12
```

```bash
uv sync --dev
```

### 2. 配置环境变量（.env）

复制示例：

```bash
cp .env.example .env
```

然后根据实际环境填写：

- `VOLC_ACCESSKEY` / `VOLC_SECRETKEY`：火山引擎 AK/SK。
- `VOLC_HOST`：Universal API 访问域名（如 `open.volcengineapi.com`）。
- `PRODUCT_ID`：Mobile Use / Cloud Phone 产品 ID。
- `POD_ID_LIST`：POD ID 列表，逗号分隔；例如：`1234567890,1234567891`。
- `TOS_BUCKET` / `TOS_ENDPOINT` / `TOS_REGION`：用于截图/录屏回传的 TOS 配置。
- 运行相关：
  - `CASE_FILTER`：用例文件过滤关键字（逗号分隔，匹配相对路径）；为空时执行全部。
  - `EXEC_MODE`：执行模式：`auto`。
    - `auto`（默认）：`POD_ID_LIST<=1` 串行；`POD_ID_LIST>1` 并行。
  - `RUN_API`：`one_step` 或 `task`，对应不同的后端 API 路径。
  - `CASE_TIMEOUT_S`：单用例最大等待时间（秒），默认 `600`。
  - `POLL_INTERVAL_S`：轮询间隔（秒），默认 `2`。
  - `USE_STATUS_API`：`true`/`false`，是否通过 `ListAgentRunTask` 轮询状态。
  - `USE_BASE64_SCREENSHOT`：`true`/`false`，是否使用 base64 截图。
  - `SCREEN_RECORD`：`true`/`false`，是否开启录屏。

> `.env` 会通过 `src/env_utils.py` 在启动时自动加载（`load_env_from_root`），不会覆盖已有环境变量。

### 3. 运行用例执行器

执行所有用例：

```bash
uv run python -m src.main
```

指定执行用例：

```bash
CASE_FILTER=douyin-draft-create RUN_API=one_step uv run python -m src.main
```


运行完成后，会在 `results/` 目录生成形如 `20251230_063313.json` 的结果文件。

### 4. 查看执行结果（前端页面）

在浏览器中直接打开项目根目录下的：

- `results.html`

即可进行本地查看，无需启动服务器。

---

## 项目结构

当前项目结构（核心部分）：

- `src/`
  - `main.py`：命令行入口，负责加载环境变量、构造 `RunnerConfig`、调用 `run_suite` 并写结果文件。
  - `case_runner.py`：
    - 用例发现：`discover_cases(cases_dir: Path)`，支持 `CASE_FILTER`。
    - 执行单个用例：`run_one_case(...)`。
    - 执行用例集：`run_suite(...)`。
    - 结果组装：`_result_from_resp(...)`，将云端响应转换为统一的结果字典。
  - `mobile_use.py`：
    - `MobileUseClient`：封装底层 Universal API 调用、ListPod 等。
    - `ResultItem`：结果字段 dataclass，统一结构。
  - `system_prompt.py`：系统 Prompt 模板。
  - `env_utils.py`：`.env` 加载与布尔环境变量解析。
- `cases/`：用例库目录（Markdown 或 `.case`）。
- `results/`：执行结果 JSON 文件目录。
- `results.html`：本地结果可视化页面。
- `pyproject.toml` / `requirements.txt`：依赖管理。
- `.env` / `.env.example`：环境变量配置模版。

---

## 用例库（cases）

- 所有用例位于 `cases/` 目录下，支持：
  - Markdown（`.md`）
  - 自定义 `.case` 文本文件
- 推荐参考 `cases/template.md` 编写用例，一般结构包括：
  - `## 执行任务`
  - `## 用例通过标准`
  - `## 错误场景`（可选）

**CASE 选择：**

- 默认情况下会执行 `cases/` 下所有非隐藏、非 `template.*` 的用例。
- 可以通过环境变量 `CASE_FILTER` 控制执行子集，例如：
  - `CASE_FILTER=douyin-draft uv run python -m src.main`  
    仅执行路径中包含 `douyin-draft` 的用例。

---

## 运行结果（results/*.json）

执行一次 `src.main` 会生成一个 `results/YYYYMMDD_HHMMSS.json`，文件内容是一个 JSON 数组，每个元素为单个用例结果。

> 字段含义与后端任务结果结构相关，可参考（可选）：https://www.volcengine.com/docs/6394/1953054?lang=zh

### 字段说明

以下字段由 `ResultItem` + `case_runner` 共同生成，**不一定每个字段都存在**，但结构大致如下：

必选字段：

- `case`：用例文件相对路径，例如 `cases/douyin-draft-create.md`。
- `status`：`"pass" | "fail" | "skip"`。
- `timestamp`：**北京时间**，格式为 `YYYY-MM-DD HH:MM:SS`（例如 `2025-12-30 14:03:13`）。
- `duration_ms`：用例执行耗时（毫秒）。
- `reason`：失败原因或跳过说明；通过时通常为空字符串。

截图/录屏与 Token：

- `video`：
  - 优先为云端返回的 `RecordingUrl`（录屏 URL）。
  - 若无录屏，则回退为第一张截图 URL。
- `screenshot`：截图 URL 数组（从 `ScreenShots` 字段提取，可能包含多张）。
- `original_dimensions`：原始截图分辨率 `[width, height]`（仅记录第一张截图）。
- `screenshot_dimensions`：缩放后截图分辨率 `[width, height]`（仅记录第一张截图）。
- `in_tokens`：请求 Token 数。
- `out_tokens`：响应 Token 数。

Pod / 镜像信息（通过 `ListPod` 自动补全）：

- `pod_id`：当前运行的 Pod ID。
- `AospVersion`：镜像对应的 Android/AOSP 版本。
- `ImageName`：镜像名称（例如平台公共镜像名称）。
- `ImageId`：镜像 ID。
- `run_id`：云端任务 RunId。

### 示例（精简版）

```json
[
  {
    "case": "cases/douyin-draft-create.md",
    "status": "pass",
    "timestamp": "2025-12-30 14:03:13",
    "duration_ms": 152096,
    "reason": "",
    "video": "https://.../recording.mp4",
    "screenshot": [
      "https://.../screenshot_1.png",
      "https://.../screenshot_2.png"
    ],
    "original_dimensions": [720, 1280],
    "screenshot_dimensions": [720, 1280],
    "in_tokens": 123040,
    "out_tokens": 3667,
    "pod_id": "********",
    "run_id": "********",
    "AospVersion": "10",
    "ImageName": "公共镜像-Android10",
    "ImageId": "img-xxxxxxxx",
    "content": "### A. 结论摘要\n...",
    "struct_output": {
      "status": "pass",
      "reason": "",
      "evidence": ["..."],
      "observations": { "uid": "draft-crud-e2e-001", "page": "..." }
    },
    "task_status": "completed",
    "task_status_code": 3
  }
]