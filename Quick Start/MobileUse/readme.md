# 火山引擎 Mobile Use / Cloud Phone Python 示例

本仓库包含两类示例：

- `openapi_sample/`：最小化的 OpenAPI 调用示例（适合快速验证 AK/SK、网络与接口连通性）
- `ui_test_demo/`：用例驱动的 UI 自动化执行器（读取 `cases/*.md`，调用云端能力执行并生成报告）

---

## 目录结构

```text
mobile-use-demo/
├── openapi_sample/
│   └── python_openapi_sample.py    # OpenAPI 调用示例
├── ui_test_demo/                   # UI 自动化示例（含 CLI、用例与报告页面）
│   ├── README.md
│   ├── cases/
│   ├── results/
│   └── src/
├── requirements.txt                # 根目录示例依赖（openapi_sample 使用）
└── readme.md                       # 本说明
```

---

## 环境要求

- Python 3.12+（`ui_test_demo/` 推荐 Python 3.12）
- 能访问火山引擎 OpenAPI 域名（例如 `open.volcengineapi.com`）
- 具备 Mobile Use / Cloud Phone 相关权限（AK/SK 已开通对应服务）

---

## 快速开始

### A) 跑通 OpenAPI 调用示例（`openapi_sample/`）

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 配置环境变量（至少需要 AK/SK）

```bash
export VOLC_ACCESSKEY="YOUR_AK"
```

```bash
export VOLC_SECRETKEY="YOUR_SK"
```

3. 运行示例

```bash
python openapi_sample/python_openapi_sample.py
```

> 该示例展示了如何使用 `volcenginesdkcore.UniversalApi` 完成签名、发起请求与基础错误处理。

### B) 跑通 UI 自动化示例（`ui_test_demo/`）

`ui_test_demo/README.md` 包含更完整的说明，这里给最短路径：

1. 进入目录并安装依赖（推荐 `uv`）

```bash
cd ui_test_demo
```

```bash
uv sync --dev
```

2. 配置 `.env`

```bash
cp .env.example .env
```

需要必填的关键字段：

- `VOLC_ACCESSKEY` / `VOLC_SECRETKEY`
- `VOLC_HOST`（例如 `open.volcengineapi.com`）
- `PRODUCT_ID`
- `POD_ID_LIST`（逗号分隔）
- `TOS_BUCKET` / `TOS_ENDPOINT` / `TOS_REGION`

3. 校验环境并执行用例

```bash
uv run python -m src.main validate-env --pretty
```

```bash
uv run python -m src.main run
```

4. 查看结果

- 增量结果：`ui_test_demo/results/*.jsonl`
- 汇总结果：`ui_test_demo/results/*.json`
- 页面报告：打开 `ui_test_demo/results.html`

---

## 常见问题

- **接口返回鉴权失败**：确认 `VOLC_ACCESSKEY/VOLC_SECRETKEY` 正确且账号具备对应服务权限。
- **UI 自动化环境校验失败**：先运行 `ui_test_demo` 的 `validate-env`，它会用 `DetailPod` 对 `PRODUCT_ID/POD_ID_LIST` 做强校验并输出原始返回用于定位。
- **浏览器无法加载 `results/sample.json`**：可在 `ui_test_demo/` 下启动静态服务：`python -m http.server 8000`，再访问 `http://localhost:8000/results.html`。

---

## 参考链接

- 火山引擎文档：https://www.volcengine.com/docs
- SDK 文档：https://www.volcengine.com/docs/sdk/