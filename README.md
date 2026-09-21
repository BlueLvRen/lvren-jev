# lvren-jev：基于 Jev 的文本分类库

## 通用决策库

`lvren-jev` 将一段文本交给 TypeSafe Jev，根据你定义的类别返回分类结果、置信度和各类别概率。例如，将“处理生产 Redis 连接异常”归为“运维”，用于自动填写 Excel 工时类型、分派工单或分类邮件。

你通过 YAML/JSON 文件描述类别及其含义，通过 Python API 执行分类；Excel、数据库或 HTTP 的读写由业务代码负责。仓库还提供用于调试请求的浏览器 Playground 和 CLI。

### 安装

PyPI 包名和 Python 导入名不同：

- 安装包名：`lvren-jev`
- 导入名：`lvren_jev`

需要 Python 3.11 或更高版本，以及可用的 TypeSafe API Key 和网络连接。以下命令以 Windows PowerShell 为例。

从 PyPI 安装（无需下载仓库）：

```powershell
python -m pip install lvren-jev
```

如果要从源码构建 wheel，先[获取项目](#1-获取项目)，然后在仓库根目录执行：

```powershell
python -m pip install build
python -m build --wheel
# dist 下会生成 lvren_jev-<版本号>-py3-none-any.whl，使用实际生成的文件路径安装。
python -m pip install .\dist\lvren_jev-0.2.0-py3-none-any.whl
```

### 最小使用教程

以填写 Excel 工时类型为例：`工时.xlsx` 的 `sheet1` 第一行是表头，A 列是工时内容，B 列用于写入工时类型。从第二行开始逐行分类，跳过空内容，完成后保存并关闭文件。

| 行 | A 列：工时内容 | B 列：工时类型（示意结果） |
| --- | --- | --- |
| 2 | 处理生产 Redis 连接异常 | 运维 |
| 3 | 开发用户导出接口 | 开发 |

先在业务脚本的工作目录准备三个文件：

- `worklog.yaml`：告诉 Jev 有哪些工时类型、每个类型的含义，以及低置信度时如何处理。将[下文的 YAML](#worklogyaml业务决策定义)保存为此文件，或复制仓库的 [`worklog.yaml`](examples/worklog_classifier/worklog.yaml) 示例。
- `typesafe.toml`：告诉运行时使用哪个服务、模型及请求参数。
- `typesafe.secrets.toml`：保存你的 API Key。

`typesafe.toml` 内容：

```toml
[typesafe]
api_key_file = "typesafe.secrets.toml"
base_url = "https://api.typesafe.ai"
model = "jev-1.13.0"

[runtime]
timeout = 30
retry = 1
cache = false
```

在同目录创建 `typesafe.secrets.toml`：

```toml
[typesafe]
api_key = "替换为你的 API Key"
```

下面展示完整的业务调用流程。`business_excel` 是你自己的 Excel 适配模块占位名，**不由本包提供**；示例省略其实现，只约定各方法的输入输出。接入已有 Excel 读写代码后即可运行。示例会覆盖非空 A 列所在行的 B 列，并在全部分类成功后保存原文件；任一行失败则不执行保存，但仍关闭文件。

```python
from lvren_jev import (
    ClassificationResult,
    JevRuntime,
    SemanticClassifier,
    load_decision_definition,
)

# 业务方提供的 Excel 操作，输入输出见下方调用处注释。
from business_excel import (
    open_workbook,
    iter_work_descriptions,
    write_work_type,
    save_workbook,
    close_workbook,
)


def get_work_type_name(result: ClassificationResult) -> str:
    # 输入：ClassificationResult 对象，完整结构见下方 classify() 调用处。
    # 输出：写入 B 列的名称，例如 "运维"；低置信度时为 "待确认"。
    return result.label


# 加载类别及策略，返回 DecisionDefinition；该文件不是 Excel 数据文件。
definition = load_decision_definition("worklog.yaml")

# JevRuntime 读取连接配置并管理客户端；退出 with 时关闭客户端。
# 整个文件复用一个运行时和分类器，无需每行重新创建。
with JevRuntime.from_config("typesafe.toml") as runtime:
    # SemanticClassifier 将类别定义和运行时组合成可调用的文本分类器。
    classifier = SemanticClassifier.from_definition(definition, runtime=runtime)

    # 输入：文件路径；输出：业务方 Excel 库的工作簿对象。
    workbook = open_workbook("工时.xlsx")
    try:
        # 输入：工作簿、工作表名和起始行；读取 A 列，跳过空内容。
        # 输出：逐个 (行号, 文本)，例如 (2, "处理生产 Redis 连接异常")。
        for row_number, description in iter_work_descriptions(
            workbook, sheet_name="sheet1", start_row=2
        ):
            # 输入：单条工时文本 str；内部调用 Jev，返回 ClassificationResult 对象。
            # 返回对象示意（实际内容由 Jev 返回，并经过分类策略处理）：
            # ClassificationResult(
            #     value="operations",       # 稳定的类别 ID，用于程序判断和保存
            #     label="运维",             # 展示名称，用于填写 Excel 的 B 列
            #     confidence=0.91,          # 置信度，范围为 0 到 1
            #     probabilities={          # 各类别的概率；未提供时为 None
            #         "operations": 0.91,
            #         "development": 0.09,
            #     },
            #     fallback=False,          # True 表示已按低置信度策略回退
            # )
            result = classifier.classify(description)
            work_type = get_work_type_name(result)

            # 输入：工作簿、工作表、行号和类型名称；将名称写入该行 B 列。
            # 例如第 2 行写入 "运维"；无返回值。
            write_work_type(workbook, "sheet1", row_number, work_type)

        # 输入：工作簿；保存到原文件，无返回值。
        save_workbook(workbook)
    finally:
        # 输入：工作簿；释放文件资源，不隐式保存，无返回值。
        close_workbook(workbook)
```

`classify()` 已经将 Jev 选中的类别转换为结果中的 `value` 和 `label`，并应用配置中的置信度阈值。业务方法 `get_work_type_name()` 只提取最终名称，不再发起请求或重新计算概率。置信度低于 `policy.threshold` 时，结果会改为配置的“待确认”；`probabilities` 保留各类别概率，便于业务方复核。这里的结果和概率均为示意，实际由 Jev 返回。

不建议把真实 API Key 提交到 Git。更安全的做法是使用 `api_key_file`，详见[配置](#配置)。

通用层公开对象的关系是：

```text
YAML/JSON
  -> DecisionDefinition
  -> SemanticClassifier
  -> JevRuntime
  -> ClassificationResult
```

`JevRuntime` 提供可复用的客户端调用、超时、重试、缓存、响应标准化和基础 telemetry；配置错误、调用错误和低置信度回退分别有独立行为。邮件、工时、工单等业务只需替换决策文件和业务适配器，不需要修改通用分类器。

正式使用时不需要手动创建或替换 `TypeSafeClient`。下面这行会读取配置，并自动创建真实的官方 SDK 客户端：

```python
runtime = JevRuntime.from_config("typesafe.toml")
```

调用链是：

```text
typesafe.toml
  -> JevRuntime.from_config()
  -> typesafe_sdk.TypeSafeClient
  -> TypeSafeClient.system_one()
  -> JevResponse
```

## 配置和数据格式

### `worklog.yaml`：业务决策定义

`worklog.yaml` 描述“要分什么类别”以及每个类别的含义。它属于业务层，由业务方维护；通用包只负责加载和执行，不关心数据来自 Excel、数据库还是 HTTP。

最小结构：

```yaml
version: 1
kind: classifier
name: worklog_classifier

input:
  type: text
  field: description
  instructions: Classify the work description into the category that best matches it.

categories:
  operations:
    label: 运维
    description: 生产维护、故障处理、监控和基础设施问题
  development:
    label: 开发
    description: 功能开发、代码修改和缺陷修复

policy:
  threshold: 0.65
  fallback:
    value: pending_review
    label: 待确认
```

字段含义：

- `name`：问题名称，也是返回答案中的问题标识。
- `input.field`：输入文本在 `state` 中使用的字段名。
- `categories`：程序值、展示名称和分类说明。程序值如 `operations` 应保持稳定。
- `policy.threshold`：低于此置信度时使用 `fallback`。

### `typesafe.toml`：通用运行时配置

通用包最简单的配置形式如下：

```toml
[typesafe]
api_key_file = "typesafe.secrets.toml"
base_url = "https://api.typesafe.ai"
model = "jev-1.13.0"

[runtime]
timeout = 30
retry = 1
cache = false
```

配置含义：

- `[typesafe]`：API 地址和模型配置。
- `api_key_file`：相对于 `typesafe.toml` 的密钥文件路径。
- `base_url`：TypeSafe API 地址。
- `model`：使用的 Jev 模型。
- `[runtime].timeout`：单次请求超时时间，单位为秒。
- `[runtime].retry`：运行时对可重试连接错误的重试次数。
- `[runtime].cache`：是否启用相同请求的进程内缓存。

`typesafe.toml` 中也可以使用 `default_profile` 和 `typesafe.profiles.<name>` 管理多个 API 来源，详见[配置](#配置)。

注意：`max_questions` 是 Playground/CLI 的本地问题数量保护配置，不是通用 `JevRuntime` 的运行时字段；通用包使用上面的 `timeout`、`retry` 和 `cache`。

### 分层输入和输出

```text
业务输入文本: str
  -> SemanticClassifier.classify(text)
  -> DecisionRequest(state, questions)
  -> JevRuntime.execute(request)
  -> JevResponse(answers, usage, model)
  -> ClassificationResult
```

各层接口如下：

| 层 | 输入 | 输出 |
| --- | --- | --- |
| 业务层 | Excel、数据库或 HTTP 等来源的文本 | 传给分类器的 `str`，以及对分类结果的后续业务处理 |
| `SemanticClassifier` | `classify(text: str)` | `ClassificationResult` |
| `JevRuntime` | `DecisionRequest`，包含 `state` 和 `questions` | `JevResponse`，包含 `answers`、`usage`、`model` |

`classify()` 返回的是 `ClassificationResult` 对象，使用 `result.label` 等属性读取字段；调用 `result.to_dict()` 才会转换为字典，使用 `result.to_dict()["label"]` 等方式读取。转换示例：

```python
result = classifier.classify("处理生产 Redis 连接异常")
print(result.to_dict())
```

```python
{
    "value": "operations",
    "label": "运维",
    "confidence": 0.91,
    "probabilities": {
        "operations": 0.91,
        "development": 0.09,
    },
    "fallback": False,
}
```

其中：

- `value`：稳定的程序值，用于分支判断和保存。
- `label`：面向用户的展示名称。
- `confidence`：整体置信度，范围为 `0` 到 `1`。
- `probabilities`：各分类的概率。
- `fallback`：是否因置信度低于阈值进入待确认状态。

## Playground 与 CLI

除 Python 包外，源码仓库还提供两个调试入口，以下命令均在仓库根目录执行：

- `typesafe_playground.py`：启动明亮主题的浏览器 Playground。
- `typesafe_cli.py`：供 Codex 或其他本地脚本调用，输出 JSON。

两者都通过官方 `typesafe-sdk` 调用 TypeSafe Jev，并在一个进程内复用同一个 `TypeSafeClient`。

本项目采用 [MIT License](LICENSE)。`typesafe-sdk`、TypeSafe API 和 Jev 模型属于第三方服务或依赖，分别遵循其自身的许可证、服务条款和使用限制。

## 环境准备

以下命令以 Windows PowerShell 为例。项目要求 Python 3.11 或更高版本，因为代码使用了内置 `tomllib` 和现代类型语法；运行 Playground 还需要可用的浏览器和网络连接。

### 1. 获取项目

如果尚未下载项目：

```powershell
git clone https://github.com/BlueLvRen/lvren-jev.git lvren_jev
cd lvren_jev
```

如果项目已经存在，进入你本地的仓库根目录即可。

### 2. 创建虚拟环境并安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

验证 SDK 可以导入：

```powershell
python -c "from typesafe_sdk import TypeSafeClient; print('typesafe-sdk ready')"
```

如果 PowerShell 阻止激活脚本，可以只对当前窗口放行后重新激活：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 3. 创建本地 API Key 文件

仓库中的 `typesafe.toml` 只保存地址、模型和 Profile，不保存 API Key。首次使用时，在项目目录创建 `typesafe.secrets.toml`：

```powershell
notepad .\typesafe.secrets.toml
```

填入以下内容，并将占位文本替换为官方 API Key：

```toml
[typesafe]
api_key = "替换为你的 TypeSafe API Key"
```

如果配置了其他 Profile，为其创建对应的密钥文件，内容格式相同。仓库已忽略 `typesafe.secrets.toml` 和 `typesafe.secrets.*.toml`；请勿提交真实密钥。

### 4. 检查配置

```powershell
python -c "from typesafe_client import load_config; c=load_config(); print({'profile': c.profile, 'base_url': c.base_url, 'max_questions': c.max_questions})"
```

正常情况下会显示当前 Profile、服务地址和 `max_questions = 0`，不会输出 API Key。配置异常时，先检查 `typesafe.toml` 和对应的 `typesafe.secrets*.toml` 是否存在、格式是否正确。

### 5. 运行测试

```powershell
python -m unittest discover -s . -p "test_*.py" -v
```

## 配置

主配置文件是 `typesafe.toml`，通过 Profile 区分不同来源：

```toml
[typesafe]
default_profile = "official"

[typesafe.profiles.official]
api_key_file = "typesafe.secrets.toml"
base_url = "https://api.typesafe.ai"
model = "jev-1.13.0"

```

本地问题数量保护在 `[runtime]` 中配置：

```toml
[runtime]
max_questions = 0
```

`0` 表示不启用本地数量限制；设置为正整数时，超过该数量的问题会在调用 Jev 前被拒绝。该配置只是本地保护，不代表 Jev 官方服务端限制。

每个 Profile 的 API Key 位于同级独立密钥文件。例如官方 Profile：

```toml
[typesafe]
api_key = "替换为你的 API Key"
```

`typesafe.secrets.toml` 和 `typesafe.secrets.*.toml` 已加入仓库的 `.gitignore`。在自己的项目中使用时，也应将密钥文件加入忽略规则。要增加其他来源，可新增 `[typesafe.profiles.<名称>]`，填写对应地址、模型和密钥文件路径，再通过 `--profile <名称>` 选择。

## 启动 Playground

在仓库根目录执行：

```powershell
python .\typesafe_playground.py
```

显式选择已配置的来源启动：

```powershell
python .\typesafe_playground.py --profile official
```

浏览器打开：

```text
http://127.0.0.1:8765
```

页面一次请求覆盖 `Choice`、`Score`、`Noul`，并显示：

- 浏览器总耗时
- 服务端总耗时
- Jev 请求耗时
- 配置、客户端准备、问题构造和响应序列化耗时

返回的原始答案不会被本地业务策略改写，因此 Choice/Score 的 `confidence`、`probabilities` 和 Noul 的 `noul` 都会保留。

## CLI 调用

直接传 JSON：

```powershell
python .\typesafe_cli.py `
  --state '{"message":"页面加载要 8 秒，用户希望今天解决。","channel":"web"}' `
  --questions '{"team":{"type":"choice","instructions":"Which team should handle this request?","criteria":{"billing":"Charges and payments","technical":"Software failures","other":"None of these"}},"urgency":{"type":"score","instructions":"How urgent is this request?","criteria":["Can wait","This week","Today"]},"urgent":{"type":"noul","instructions":"Does the sender request help today?"}}' `
  --pretty
```

也可以从文件读取：

```powershell
python .\typesafe_cli.py `
  --state-file state.json `
  --questions-file questions.json `
  --profile official `
  --pretty
```

可选参数：

```text
--config PATH     指定主 TOML 配置文件
--profile NAME    选择配置来源；省略时使用 default_profile
--model MODEL     临时覆盖配置中的模型
--pretty          美化 JSON 输出
```

成功时退出码为 `0`，标准输出为 JSON。

错误时仍输出 JSON，并使用非零退出码：

```json
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "..."
  }
}
```

目前使用的错误码包括：

```text
INVALID_REQUEST
CONFIG_ERROR
TYPESAFE_AUTHENTICATION_ERROR
TYPESAFE_TIMEOUT
TYPESAFE_RATE_LIMIT
TYPESAFE_API_ERROR
INTERNAL_ERROR
```

## 请求校验

当前代码会校验：

- State 必须是字符串、数组或 JSON 对象。
- Questions 必须是非空对象。
- `[runtime].max_questions` 默认为 `0`；大于 `0` 时限制单次本地请求的问题数量。
- 每个问题必须有非空 Instructions。
- Choice Criteria 必须有非空标签，标签不能重复。
- Score 至少有两个等级，等级必须非空且不能重复。
- Noul Criteria 只能使用 `true` 和 `false`。
- Criteria 和 State 必须是 JSON 可表达的数据。

## 测试

```powershell
python -m unittest discover -s . -p "test_*.py" -v
```
