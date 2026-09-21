# lvren-jev：面向应用与 LLM 的 Jev 决策原语库

`lvren-jev` 将 TypeSafe Jev 的分类、评分和条件判断封装为可复用的决策原语：预先定义一个判断的输入、标准和结果，之后像调用普通函数一样使用它。普通程序通过 Python 接口执行决策，并将其集成到完整业务流程中；LLM 可以调用这些程序提供的业务工具，委派任务并根据完成状态继续工作。

## 为什么使用 lvren-jev

**官方 Jev SDK 解决“如何调用 Jev API”；`lvren-jev` 解决“如何把 Jev 的能力作为应用和 LLM 可以复用的决策原语”。**

如果只是把官方 SDK 交给 LLM，LLM 仍需要理解 Jev 的参数要求、编写判断指令、构造类别或评分标准，再理解并解析原始响应。每次任务都重新承担这些工作，可能增加上下文、参数生成和结果解释的开销，也让项目多出一套需要维护的接入逻辑。引入 Jev 本身，并不自动意味着降低成本。

`lvren-jev` 将类别、判断指令、评分标准和分类回退策略保存在决策定义中，由库加载、校验并构造 Jev 请求。普通程序可以复用这些定义，接收结构化结果，并自行完成后续业务处理。LLM 则通过业务入口委派任务，无需逐步组织模型请求、解释概率或指导程序如何处理每条数据。

这种设计将重复的语义判断收敛到可维护的程序流程中，减少 LLM 在参数生成、中间结果解释和逐步协调上的参与。接入 Jev 的价值由可复用的业务能力体现，而不止于增加一个模型调用入口。

这种复用建立在四个约定上：

- **统一的决策定义**：用 YAML/JSON 描述分类、评分或条件判断，定义与运行配置、业务代码彼此分离。
- **简单的调用入口**：普通程序通过 `classify()` 或 `evaluate()` 执行单个决策，向 LLM 暴露的业务工具由宿主应用组织。
- **结构化的结果**：返回分类、评分或条件概率对象，可通过 `to_dict()` 转为字典，供普通程序继续处理，无需逐项交回 LLM 解释。
- **可组合的请求**：需要同时做多个判断时，由应用通过一个 `DecisionRequest` 组合，在一次请求中提交；连续调用多个包装方法不会自动合并请求。

本包仍通过官方 `typesafe-sdk` 调用同一个 Jev 服务。封装本身不增加额外的模型推理步骤，不运行额外的 Agent，也不要求部署新的服务；实际请求次数仍取决于调用方式、缓存和重试配置。包装库本身不收取额外服务费用，实际调用 Jev 服务仍遵循 TypeSafe 的计费和限制。

具体节省多少 token、延迟或费用，需要结合实际任务衡量。

## 核心思想：以业务操作为委派边界

**LLM 负责组织任务，普通程序负责完成业务，`lvren-jev` 负责提供程序内部的语义决策能力。**

| 角色 | 职责 | 交付给下一环节的内容 |
| --- | --- | --- |
| LLM：任务编排者 | 理解目标、选择业务操作，根据执行状态推进后续任务 | 业务入口所需的信息，如文件路径、任务标识或必要上下文 |
| 普通程序：业务执行者 | 获取数据和语义上下文、调用决策、处理结果、完成读写及其他业务动作 | 完成状态、必要的产物位置或需要上层处理的问题 |
| lvren-jev：决策组件 | 根据预定义标准构造 Jev 请求，解析响应并应用配置的决策策略 | 供普通程序使用的分类、评分或条件概率结果 |

例如，LLM 调用业务程序提供的“完成 Excel 工时分类”工具，只需给出文件路径。程序自行读取工时内容，使用 `lvren-jev` 分类，将结果写回表格并保存，最后回报完成状态和输出文件。LLM 收到成功结果后即可继续后面的业务，无需参与每行数据的判断和写入。

语义上下文可以由 LLM 提供，也可以由程序从文件、数据库或业务状态中取得。调用方只需理解业务入口的用途和必要输入，Jev 参数、决策定义及中间结果留在程序内部。正常完成时返回简洁状态；执行失败或需要上层决策时，再回报必要的信息。

这是应用集成时的职责划分：业务工具的注册、流程执行和状态回报由普通程序实现，`lvren-jev` 提供其中可复用的决策组件。

## 能力概览

| 能力 | 业务示例 | 调用入口 | 返回对象 |
| --- | --- | --- | --- |
| Choice 分类 | 判断工时类型、选择工单处理部门 | `SemanticClassifier.classify()` | `ClassificationResult` |
| Score 评分 | 评估风险、紧急程度或质量等级 | `ScoreEvaluator.evaluate()` | `ScoreResult` |
| Noul 条件判断 | 判断是否需要人工复核 | `NoulEvaluator.evaluate()` | `NoulResult` |
| 组合决策 | 一次请求同时判断类别、紧急程度和人工介入需求 | `JevRuntime.execute()` | `JevResponse` |

决策可通过 YAML/JSON 文件维护；运行时统一管理客户端复用、超时、重试、缓存和响应标准化。Excel、数据库、HTTP 等数据读写及后续业务动作由应用负责。

## 阅读导航

- [为什么使用 lvren-jev](#为什么使用-lvren-jev)
- [核心思想：以业务操作为委派边界](#核心思想以业务操作为委派边界)
- [安装](#安装)
- [快速上手：填写 Excel 工时类型](#快速上手填写-excel-工时类型)
- [运行配置](#运行配置)
- [决策定义与调用](#决策定义与调用)
- [接口与返回结果](#接口与返回结果)
- [进阶：一次请求组合多个决策](#进阶一次请求组合多个决策)
- [源码开发与构建](#源码开发与构建)
- [许可证](#许可证)

## 安装

PyPI 包名和 Python 导入名不同：

- 安装包名：`lvren-jev`
- 导入名：`lvren_jev`

需要 Python 3.11 或更高版本，以及可用的 TypeSafe API Key 和网络连接。以下命令以 Windows PowerShell 为例。

从 PyPI 安装（无需下载仓库）：

```powershell
python -m pip install lvren-jev
```

安装完成后可直接使用下面的示例；如需从源码构建 wheel，参见[源码开发与构建](#源码开发与构建)。

## 快速上手：填写 Excel 工时类型

以填写 Excel 工时类型为例：`工时.xlsx` 的 `sheet1` 第一行是表头，A 列是工时内容，B 列用于写入工时类型。从第二行开始逐行分类，跳过空内容，完成后保存并关闭文件。

| 行 | A 列：工时内容 | B 列：工时类型（示意结果） |
| --- | --- | --- |
| 2 | 处理生产 Redis 连接异常 | 运维 |
| 3 | 开发用户导出接口 | 开发 |

先在业务脚本的工作目录准备三个文件：

- `worklog.yaml`：告诉 Jev 有哪些工时类型、每个类型的含义，以及低置信度时如何处理。将[Choice 决策定义](#choice分类)保存为此文件，或复制仓库的 [`worklog.yaml`](examples/worklog_classifier/worklog.yaml) 示例。
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

# 业务方提供的 Excel 操作。
from business_excel import (
    open_workbook,           # 打开 Excel
    iter_work_descriptions,  # 逐行读取 A 列，跳过空内容
    write_work_type,         # 将工时类型写入 B 列
    save_workbook,           # 保存到原文件
    close_workbook,          # 关闭文件，不隐式保存
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

    # 输入：路径 str；输出：工作簿对象。
    workbook = open_workbook("工时.xlsx")
    try:
        # 输入：工作簿对象、工作表名 str、起始行 int。
        # 输出：迭代器，每项为 (int, str)，如 (2, "处理生产 Redis 连接异常")。
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

            # 输入：工作簿对象、"sheet1" (str)、2 (int)、"运维" (str)；输出：None。
            write_work_type(workbook, "sheet1", row_number, work_type)

        # 输入：工作簿对象；输出：None。
        save_workbook(workbook)
    finally:
        # 输入：工作簿对象；输出：None。
        close_workbook(workbook)
```

`classify()` 已经将 Jev 选中的类别转换为结果中的 `value` 和 `label`，并应用配置中的置信度阈值。业务方法 `get_work_type_name()` 只提取最终名称，不再发起请求或重新计算概率。置信度低于 `policy.threshold` 时，结果会改为配置的“待确认”；`probabilities` 保留各类别概率，便于业务方复核。这里的结果和概率均为示意，实际由 Jev 返回。

`typesafe.toml` 只保存地址、模型和运行参数；API Key 放在同目录的 `typesafe.secrets.toml` 中，并由 `api_key_file` 引用。应用启动时只需保证这两个文件路径正确。

## 运行配置

### 服务连接与请求参数

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

### API Key 文件

使用方的 `typesafe.toml` 只保存地址、模型和 Profile，不保存 API Key。首次使用时，在业务项目目录创建 `typesafe.secrets.toml`：

```powershell
notepad .\typesafe.secrets.toml
```

填入以下内容，并将占位文本替换为官方 API Key：

```toml
[typesafe]
api_key = "替换为你的 TypeSafe API Key"
```

如果配置了其他 Profile，为其创建对应的密钥文件，内容格式相同。请将 `typesafe.secrets.toml` 和 `typesafe.secrets.*.toml` 加入业务项目的 `.gitignore`；请勿提交真实密钥。

### 多来源配置（Profile）

主配置文件是 `typesafe.toml`，通过 Profile 区分不同来源：

```toml
[typesafe]
default_profile = "official"

[typesafe.profiles.official]
api_key_file = "typesafe.secrets.toml"
base_url = "https://api.typesafe.ai"
model = "jev-1.13.0"

```

每个 Profile 的 API Key 位于同级独立密钥文件。例如官方 Profile：

```toml
[typesafe]
api_key = "替换为你的 API Key"
```

可新增 `[typesafe.profiles.<名称>]` 配置其他来源，并通过 `default_profile` 选择默认来源。

## 决策定义与调用

决策定义文件描述“要判断什么”以及答案的含义。它属于业务层，由业务方维护；通用包只负责加载、构造原语请求和解析结果，不关心数据来自 Excel、数据库还是 HTTP。

目前支持三种 `kind`：

| `kind` | 对应原语 | 适合场景 | Python 包装类 | 结果类型 |
| --- | --- | --- | --- | --- |
| `classifier` | Choice | 从互斥类别中选择一个结果 | `SemanticClassifier` | `ClassificationResult` |
| `score` | Score | 对一个维度进行有序程度评分 | `ScoreEvaluator` | `ScoreResult` |
| `noul` | Noul | 判断一个条件成立的概率 | `NoulEvaluator` | `NoulResult` |

三种定义都有以下公共字段：

- `version`：决策文件格式版本，目前为 `1`。
- `kind`：决定使用哪种原语和包装类。
- `name`：问题名称，也是 Jev 返回答案中的问题标识。
- `input.type`：当前支持 `text`。
- `input.field`：输入文本在 `state` 中使用的字段名。
- `input.instructions`：告诉 Jev 如何进行判断的说明。

### Choice：分类

适合工时分类、工单路由、内容类型识别等“只能选一个类别”的场景。

示例文件：[`examples/worklog_classifier/worklog.yaml`](examples/worklog_classifier/worklog.yaml)

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

关键数据结构：

- `categories` 是“程序值 -> 类别定义”的对象。
- `categories.<value>.label` 是展示名称。
- `categories.<value>.description` 是类别含义，供 Jev 判断。
- `policy.threshold` 低于该置信度时使用 `fallback`。

调用方式：

```python
from lvren_jev import JevRuntime, SemanticClassifier, load_decision_definition

definition = load_decision_definition("worklog.yaml")
with JevRuntime.from_config("typesafe.toml") as runtime:
    classifier = SemanticClassifier.from_definition(definition, runtime=runtime)
    result = classifier.classify("处理生产 Redis 连接异常")

print(result.value, result.label, result.confidence)
```

输出 `ClassificationResult`，主要字段为 `value`、`label`、`confidence`、`probabilities` 和 `fallback`。

### Score：评分

适合风险程度、紧急程度、质量等级、影响范围等“从低到高有顺序”的场景。Score 的 `criteria` 必须按从低到高排列；返回的 `score` 可以是两个等级之间的小数。

示例文件：[`examples/score_evaluator/risk_score.yaml`](examples/score_evaluator/risk_score.yaml)

```yaml
version: 1
kind: score
name: risk_score

input:
  type: text
  field: description
  instructions: Evaluate the operational risk described in the text.

criteria:
  - 0: No meaningful operational risk
  - 1: Minor issue with a local impact
  - 2: Limited impact or workaround available
  - 3: Material impact requiring prompt action
  - 4: Major impact across an important workflow
  - 5: Critical production risk requiring immediate response
```

关键数据结构：

- `criteria` 是有序数组，位置代表从低到高的评分等级。
- 每个等级可以是字符串，也可以是包含分值和描述的对象。
- Score 不使用 `categories` 和分类 fallback 策略。

调用方式：

```python
from lvren_jev import JevRuntime, ScoreEvaluator, load_decision_definition

definition = load_decision_definition("risk_score.yaml")
with JevRuntime.from_config("typesafe.toml") as runtime:
    evaluator = ScoreEvaluator.from_definition(definition, runtime=runtime)
    result = evaluator.evaluate("生产 Redis 连接持续失败")

print(result.score, result.confidence)
```

输出 `ScoreResult`，主要字段为 `score`、`confidence`、`legend` 和 `probabilities`。

### Noul：条件判断

适合“是否需要人工介入”“是否违反规则”“是否属于高风险”等二元条件判断。Noul 返回的是条件为真的概率，不是绝对布尔值。

示例文件：[`examples/noul_evaluator/needs_review.yaml`](examples/noul_evaluator/needs_review.yaml)

```yaml
version: 1
kind: noul
name: needs_review

input:
  type: text
  field: description
  instructions: Determine whether the case requires human review.

criteria:
  "true": The case is ambiguous, sensitive, high risk, or explicitly asks for a human.
  "false": The case is clear and can be handled without human review.
```

关键数据结构：

- `criteria` 可省略，也可以用 `true`/`false` 两个键分别描述两种情况。
- YAML 中建议给 `true` 和 `false` 加引号，避免被 YAML 解析成布尔键。
- 返回的 `probability` 范围为 `0` 到 `1`，`NoulResult.is_true()` 默认使用 `0.5` 作为判断阈值。

调用方式：

```python
from lvren_jev import JevRuntime, NoulEvaluator, load_decision_definition

definition = load_decision_definition("needs_review.yaml")
with JevRuntime.from_config("typesafe.toml") as runtime:
    evaluator = NoulEvaluator.from_definition(definition, runtime=runtime)
    result = evaluator.evaluate("客户明确要求转人工处理")

print(result.probability)
print(result.is_true())
```

输出 `NoulResult`，主要字段为 `probability`。如果业务需要不同阈值，可以调用 `result.is_true(threshold=0.8)`。

## 接口与返回结果

### 调用层次

```text
业务输入: str 或 JSON 对象
  -> 对应的原语包装类
  -> DecisionRequest(state, questions)
  -> JevRuntime.execute(request)
  -> JevResponse(answers, usage, model)
  -> 对应的结果类型
```

各层接口如下：

| 层 | 输入 | 输出 |
| --- | --- | --- |
| 业务层 | Excel、数据库或 HTTP 等来源的数据 | 传给包装类的文本或 JSON 对象，以及后续业务处理 |
| `SemanticClassifier` | `classify(text: str)` | `ClassificationResult` |
| `ScoreEvaluator` | `evaluate(state)` | `ScoreResult` |
| `NoulEvaluator` | `evaluate(state)` | `NoulResult` |
| `JevRuntime` | `DecisionRequest`，包含 `state` 和 `questions` | `JevResponse`，包含 `answers`、`usage`、`model` |

### 分类结果与字典转换

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

### 运行时与客户端

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

## 进阶：一次请求组合多个决策

`JevRuntime` 使用通用的 `DecisionRequest`，可以在一次请求中组合三种原语：

```python
from lvren_jev import DecisionRequest, JevRuntime

runtime = JevRuntime.from_config("typesafe.toml")
response = runtime.execute(
    DecisionRequest(
        state={"message": "页面加载很慢，用户要求今天解决，并希望转人工。"},
        questions={
            "team": {
                "type": "choice",
                "instructions": "Which team should handle this request?",
                "criteria": {
                    "billing": "Charges and payments",
                    "technical": "Software failures",
                    "other": "None of these",
                },
            },
            "urgency": {
                "type": "score",
                "instructions": "How urgent is this request?",
                "criteria": ["Can wait", "This week", "Today"],
            },
            "needs_human": {
                "type": "noul",
                "instructions": "Does the user want to talk to a human?",
                "criteria": {
                    "true": "The user explicitly asks for a person.",
                    "false": "The user does not ask for a person.",
                },
            },
        },
    )
)

print(response.answers["team"])
print(response.answers["urgency"])
print(response.answers["needs_human"])
runtime.close()
```

三种原语的输入和返回字段分别是：

- `Choice`：`criteria` 是“程序值 -> 描述”的对象；返回 `choice`、`confidence` 和 `probabilities`。
- `Score`：`criteria` 是从低到高排列的描述数组；返回 `score`、`confidence`、`legend` 和 `probabilities`。`score` 可以是小数。
- `Noul`：`criteria` 可选，描述 `true` 和 `false`；返回 `noul`，范围为 `0` 到 `1`，表示回答为“是”的概率。Noul 没有单独的 `confidence` 字段。

每次只处理一种决策时，可使用前文的 `SemanticClassifier`、`ScoreEvaluator` 或 `NoulEvaluator`；需要组合多个问题时，直接构造 `DecisionRequest`。

## 源码开发与构建

以下步骤适用于修改源码、运行测试或构建安装包，在仓库根目录执行命令。

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

### 3. 检查安装

```powershell
python -c "import lvren_jev; print('lvren-jev', lvren_jev.__version__)"
```

正常情况下会显示已安装的 `lvren-jev` 版本。

### 4. 运行测试

```powershell
python -m unittest discover -s tests -v
```

### 5. 构建并安装 wheel

```powershell
python -m pip install build
python -m build --wheel
# dist 下会生成 lvren_jev-<版本号>-py3-none-any.whl，使用实际生成的文件路径安装。
python -m pip install .\dist\lvren_jev-0.2.0-py3-none-any.whl
```

## 许可证

本项目采用 [MIT License](LICENSE)。你可以自由使用、复制、修改和分发本项目，包括用于商业项目；使用时请保留版权和许可证声明。项目按现状提供，不附带任何担保。
