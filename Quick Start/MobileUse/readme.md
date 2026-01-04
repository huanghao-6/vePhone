# Mobile Use / Cloud Phone OpenAPI 调用示例（Python）

本目录提供两类示例：

- `openapi_sample/`：最小可运行的 Universal OpenAPI 调用示例（Python 脚本）。
- `ui_test_demo/`：基于用例库（`cases/`）的批量执行与结果可视化 Demo（带 `results.html`）。

---

## 目录结构

```text
Quick Start/MobileUse/
├── openapi_sample/
│   └── python_openapi_sample.py   # 最小 OpenAPI 调用示例
├── ui_test_demo/                  # UI 测试 / 用例执行与结果可视化 Demo（详见其 README）
├── requirements.txt               # openapi_sample 依赖（volcengine-python-sdk）
└── readme.md                      # 本说明文档
```

---

## 一、openapi_sample：快速开始

这是一个**单文件 Python 示例**，演示如何通过火山引擎 Python SDK 调用 Mobile Use / Cloud Phone 的 Universal OpenAPI，包括：

- 使用 `volcenginesdkcore` 进行 API 鉴权与请求；
- 调用 `CreateAgentRunConfig` 创建配置；
- 调用 `RunAgentTask` 发起任务；
- 调用 `ListAgentRunCurrentStep` 查询当前步骤。

### 1. 准备 Python 环境

建议使用 **Python 3.8+**。

在仓库根目录下，进入本示例目录（注意路径中有空格，需要加引号）：

```bash
cd "Quick Start/MobileUse"
```

安装依赖：

```bash
pip install -r requirements.txt
```

说明：

- `requirements.txt` 中依赖为 `volcengine-python-sdk`；
- 示例脚本中导入的是 `volcenginesdkcore` 模块，它来自该 SDK 包。

### 2. 配置 AK/SK 环境变量

示例脚本会从环境变量中读取 AK/SK，请先配置：

```bash
export VOLC_ACCESSKEY="YOUR_AK"
export VOLC_SECRETKEY="YOUR_SK"
```

> 建议不要将 AK/SK 写死在代码中或提交到版本库。

### 3. 填写脚本中的业务参数

打开并编辑：

- `openapi_sample/python_openapi_sample.py`

在文件中找到如下参数，并替换为你实际环境中的值：

- `product_id`：云手机产品 ID。
- `pod_id`：云手机实例（POD）ID。
- `tos_bucket`：TOS Bucket 名称。
- `tos_endpoint`：TOS Endpoint，例如：`https://tos-cn-beijing.volces.com`。
- `tos_region`：TOS 所在地域，例如：`cn-beijing`。
- `callback_url`：状态回调 URL（如不需要回调，请根据服务要求决定是否可为空）。

示例中 SDK 配置片段如下（仅供参考，无需手工复制）：

```python
import os
import volcenginesdkcore

ak = os.environ.get("VOLC_ACCESSKEY")
sk = os.environ.get("VOLC_SECRETKEY")

configuration = volcenginesdkcore.Configuration()
configuration.ak = ak
configuration.sk = sk
configuration.region = "cn-north-1"  # 如有需要，请改为你的地域

api_instance = volcenginesdkcore.UniversalApi(
    volcenginesdkcore.ApiClient(configuration)
)
```

如你的资源不在 `cn-north-1`，请根据实际地域调整：

```python
configuration.region = "<your-region-id>"
```

### 4. 运行示例脚本

在 `Quick Start/MobileUse` 目录下执行：

```bash
python openapi_sample/python_openapi_sample.py
```

脚本内部主要流程：

1. 调用 `CreateAgentRunConfig` 创建运行配置，返回 `ConfigId`；
2. 调用 `RunAgentTask` 发起一次 Agent 运行，返回 `RunId`；
3. `time.sleep(5)` 等待数秒后，调用 `ListAgentRunCurrentStep` 查询当前步骤并打印结果。

如调用成功，你会在控制台看到三个步骤对应的响应内容。

---

## 二、参数与注意事项

- **服务名**：示例中 `service="ipaas"`，为 Mobile Use / Cloud Phone 能力所在服务名，请不要修改。
- **权限**：请确保 AK/SK 所属账号具备调用相关 OpenAPI 的权限。
- **地域**：
  - SDK 中 `configuration.region` 需要与你使用的地域一致；
  - `tos_endpoint`、`tos_region` 也必须与实际 TOS Bucket 配置一致。
- **常见错误排查**：
  - 401 / 403：优先检查 AK/SK 是否正确、权限策略是否包含对应操作、region 是否匹配；
  - 网络错误：检查本地网络与防火墙设置；
  - 参数错误：确认 `product_id`、`pod_id`、TOS 配置等均为真实可用值。

---

## 三、ui_test_demo：用例执行与结果可视化

如果你需要：

- 从 `cases/` 目录批量读取用例（Markdown / `.case`）；
- 基于 Mobile Use / Cloud Phone 云端能力批量执行；
- 将每条用例执行结果写入 `results/*.json`；
- 通过本地打开 `results.html` 查看、筛选与分析结果；

可以使用同目录下的：

- `ui_test_demo/`

该子项目已经包含：

- `README.md`：详细的使用说明（包含 `uv` 虚拟环境、`.env` 配置、运行命令等）；
- `cases/`：用例库；
- `results/` 与 `results.html`：结果与可视化页面；
- `src/`：核心执行逻辑与 API 封装。

> `ui_test_demo` 是一个相对完整的运行框架，和本 `openapi_sample` 的最小示例互不影响，你可以根据需要选择其一或同时参考。

---

## 四、相关文档

如需了解更多参数与 API 说明，请参考：

- 火山引擎文档中心：<https://www.volcengine.com/docs>
- Mobile Use / Cloud Phone 相关文档与 OpenAPI 文档：可在文档中心搜索对应产品名称。