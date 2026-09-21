# lvren-jev：面向应用与 LLM 的 Jev 决策原语库

**核心思想：以完整业务操作作为 LLM 的委派边界，将决策细节和执行过程封装在程序内部。**

## 为什么使用 lvren-jev

官方 Jev SDK 解决“如何调用 Jev API”；`lvren-jev` 将 Jev 的分类、评分和条件判断封装为可复用的决策原语，供普通程序构建业务能力，再交由 LLM 按需调用。

以“读取 Excel 工时内容、判断类型并写回文件”为例，三种接入方式的区别在于：谁组织决策，谁处理结果，以及这些工作能否复用。

| 场景 | LLM 承担什么 | 程序承担什么 | 接入与维护成本 |
| --- | --- | --- | --- |
| LLM + Jev（直接使用 SDK） | 理解 Jev 参数、构造判断指令和类别、解释响应，再协调后续读写操作 | 尚未封装完整业务流程，文件操作需另行接入 | LLM 仍参与决策细节，增加参数生成、响应解释和过程协调的开销 |
| LLM + Jev + 普通程序 | 若程序只负责读写，LLM 仍需协调判断；若程序已封装完整流程，LLM 可以只委派任务 | 自行实现 Jev 请求构造、响应解析、分类回退及业务执行 | 可以实现完整业务委派，但决策接口与复用机制需要项目自行设计和维护 |
| LLM + 集成 lvren-jev 的普通程序 | 选择业务操作，提供必要信息，根据完成状态继续任务 | 普通程序获取上下文、完成读写和状态回报；`lvren-jev` 加载决策定义、调用 Jev 并返回结构化结果 | 复用现成的决策定义、调用接口与结果类型，减少各项目重复封装的工作 |

普通程序直接使用官方 SDK 也能实现同样的职责划分。`lvren-jev` 将其中通用的决策封装做成可复用组件，使项目更容易把完整业务留在程序内部，避免每接入一种判断都重新设计参数、解析逻辑和调用约定。仅仅引入本包不会自动减少 LLM 的参与，业务入口仍应由程序封装完整。

例如，LLM 将文件路径交给“完成 Excel 工时分类”工具，程序自行读取、分类、写回并保存，完成后回报结果。上下文可由 LLM 提供，也可由程序自行获取；只有失败或需要上层决策时，才需交回必要信息。业务工具与流程由宿主程序实现。

程序通过 YAML/JSON 维护决策定义，以 `classify()` 或 `evaluate()` 执行单个判断，也可用 `DecisionRequest` 在一次请求中组合多个判断。决策定义、运行配置与业务代码彼此分离，LLM 无需参与逐条参数构造和中间结果处理。

本包仍通过官方 `typesafe-sdk` 调用 Jev，不增加额外的模型推理层、Agent 或服务部署，也不收取额外服务费用。实际 Jev 调用遵循 TypeSafe 的计费与限制，请求次数取决于调用、缓存和重试配置；成本收益需结合实际任务衡量。

## 能力概览

| 能力 | 判断方式与业务场景 | 调用入口 | 返回对象 |
| --- | --- | --- | --- |
| Choice 分类 | 从互斥类别中选一个，如工时类型、工单处理部门 | `SemanticClassifier.classify()` | `ClassificationResult` |
| Score 评分 | 按有序标准给出数值，如风险、紧急程度或质量评分 | `ScoreEvaluator.evaluate()` | `ScoreResult` |
| Noul 条件判断 | 给出条件成立的概率，如是否需要人工复核 | `NoulEvaluator.evaluate()` | `NoulResult` |
| 组合决策 | 同一上下文的一组问题在一次请求中提交，如同时判断工单部门、紧急度和人工介入需求 | `JevRuntime.execute()` | `JevResponse` |

决策可通过 YAML/JSON 文件维护；运行时统一管理客户端复用、超时、重试、缓存和响应标准化。Excel、数据库、HTTP 等数据读写及后续业务动作由应用负责。

## 阅读导航

- [为什么使用 lvren-jev](#为什么使用-lvren-jev)
- [安装](#安装)
- [运行配置](#运行配置)
- [能力详解](#能力详解)：[分类](#choice分类)、[评分](#score评分)、[条件判断](#noul条件判断)、[组合决策](#组合决策)
- [源码开发与构建](#源码开发与构建)
- [许可证](#许可证)

## 安装

需要 Python 3.11 或更高版本，安装后使用 `import lvren_jev` 导入。

### 从仓库安装

下载仓库源码后，在仓库根目录安装：

```powershell
git clone https://github.com/BlueLvRen/lvren-jev.git lvren_jev
cd lvren_jev
python -m pip install .
```

### 从 PyPI 安装

安装已发布的版本，无需下载仓库：

```powershell
python -m pip install lvren-jev
```

## 运行配置

各能力的快速上手示例共用以下运行配置。先在业务脚本的工作目录创建 `typesafe.toml` 和 `typesafe.secrets.toml`，再按所选能力准备决策文件。

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

将 API Key 保存在与 `typesafe.toml` 同目录的 `typesafe.secrets.toml` 中：

```powershell
notepad .\typesafe.secrets.toml
```

填入以下内容，并将占位文本替换为官方 API Key：

```toml
[typesafe]
api_key = "替换为你的 TypeSafe API Key"
```

如果配置了其他 Profile，为其创建对应的密钥文件，内容格式相同。

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

### 客户端复用与释放

`JevRuntime.from_config("typesafe.toml")` 会创建官方 SDK 客户端。同一批业务数据复用一个运行时；使用 `with` 在完成或异常时释放客户端。分类、评分、条件判断和组合决策共用这套配置。

## 能力详解

以下按分类、评分、条件判断和组合决策依次介绍，每种能力均包含快速上手、定义、调用和返回结果。示例结果仅用于说明数据结构，实际数值由 Jev 返回。

示例中的 `business_excel`、`business_tickets` 是业务方模块占位名，需替换为自己的实现；本包提供决策能力，业务模块负责读写及完成状态回报。

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

#### 快速上手：填写 Excel 工时类型

以填写 Excel 工时类型为例：`工时.xlsx` 的 `sheet1` 第一行是表头，A 列是工时内容，B 列用于写入工时类型。从第二行开始逐行分类，跳过空内容，完成后保存并关闭文件。

| 行 | A 列：工时内容 | B 列：工时类型（示意结果） |
| --- | --- | --- |
| 2 | 处理生产 Redis 连接异常 | 运维 |
| 3 | 开发用户导出接口 | 开发 |

先将[分类定义](#choice分类)保存为 `worklog.yaml`，也可复制仓库的 [`worklog.yaml`](examples/worklog_classifier/worklog.yaml)。

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

#### 决策定义

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

#### 调用接口

```python
from lvren_jev import JevRuntime, SemanticClassifier, load_decision_definition

definition = load_decision_definition("worklog.yaml")
with JevRuntime.from_config("typesafe.toml") as runtime:
    classifier = SemanticClassifier.from_definition(definition, runtime=runtime)
    result = classifier.classify("处理生产 Redis 连接异常")

print(result.value, result.label, result.confidence)
```

#### 返回结果与处理规则

`classify(text: str)` 接收非空文本，返回 `ClassificationResult` 对象。示意结构：

```python
ClassificationResult(
    value="operations",
    label="运维",
    confidence=0.91,
    probabilities={"operations": 0.91, "development": 0.09},
    fallback=False,
)
```

- `value`：稳定的类别 ID，用于程序判断和保存。
- `label`：展示名称，用于表格或界面。
- `confidence`：置信度，范围为 `0` 到 `1`。
- `probabilities`：各类别概率，未提供时为 `None`。
- `fallback`：低于 `policy.threshold` 时为 `True`，`value` 和 `label` 改用配置中的兜底类别；概率仍保留。

使用 `result.label` 读取属性；需要字典时调用 `result.to_dict()`：

```python
{
    "value": "operations",
    "label": "运维",
    "confidence": 0.91,
    "probabilities": {"operations": 0.91, "development": 0.09},
    "fallback": False,
}
```

字典中的 `probabilities` 在没有概率数据时为 `{}`。程序可根据 `fallback` 安排复核，或直接将 `label` 写入业务数据。

### Score：评分

适合风险程度、紧急程度、质量等级、影响范围等“从低到高有顺序”的场景。Score 的 `criteria` 必须按从低到高排列；返回的 `score` 可以是两个等级之间的小数。

#### 快速上手：记录工单风险等级

程序读取工单描述，根据评分结果记录风险值，供后续排期使用。先将[评分定义](#score评分)保存为 `risk_score.yaml`，或复制 [`risk_score.yaml`](examples/score_evaluator/risk_score.yaml)。

```python
from lvren_jev import JevRuntime, ScoreEvaluator, load_decision_definition
from business_tickets import (
    read_ticket_description,  # 读取工单描述
    save_ticket_risk,         # 保存风险评分
)

definition = load_decision_definition("risk_score.yaml")
with JevRuntime.from_config("typesafe.toml") as runtime:
    evaluator = ScoreEvaluator.from_definition(definition, runtime=runtime)
    # 输入：工单 ID str；输出：描述 str，如 "生产 Redis 连接持续失败"。
    description = read_ticket_description("T-001")
    # 输入：str；输出示意：ScoreResult(
    #     score=4.2, confidence=0.88, legend=None, probabilities=None,
    # )
    result = evaluator.evaluate(description)
    # 输入："T-001" (str)、4.2 (float)；输出：None。
    save_ticket_risk("T-001", result.score)
```

评分范围由决策标准定义。是否按某个分值升级处理，由普通程序的业务规则决定。

#### 决策定义

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

#### 调用接口

```python
from lvren_jev import JevRuntime, ScoreEvaluator, load_decision_definition

definition = load_decision_definition("risk_score.yaml")
with JevRuntime.from_config("typesafe.toml") as runtime:
    evaluator = ScoreEvaluator.from_definition(definition, runtime=runtime)
    result = evaluator.evaluate("生产 Redis 连接持续失败")

print(result.score, result.confidence)
```

#### 返回结果与处理规则

通过 `from_definition()` 创建时，`evaluate(state)` 接收非空文本，并按 `input.field` 组装状态。直接构造 `ScoreEvaluator` 且未指定 `input_field` 时，也可传入 JSON 对象。

返回 `ScoreResult` 对象，示意结构：

```python
ScoreResult(
    score=4.2,
    confidence=0.88,
    legend=None,
    probabilities=None,
)
```

- `score`：评分数值，可为小数；评分范围取决于决策标准，不固定为 `0` 到 `1`。
- `confidence`：置信度，范围为 `0` 到 `1`。
- `legend`：服务返回的评分说明映射，未提供时为 `None`。
- `probabilities`：服务返回的概率映射，未提供时为 `None`。

通过 `result.score` 使用分数，或用 `result.to_dict()` 转为字典：

```python
{"score": 4.2, "confidence": 0.88, "legend": {}, "probabilities": {}}
```

Score 不自动套用分类的低置信度回退策略。分数达到多少应升级、置信度不足如何复核，由业务程序决定。

### Noul：条件判断

适合“是否需要人工介入”“是否违反规则”“是否属于高风险”等二元条件判断。Noul 返回的是条件为真的概率，不是绝对布尔值。

#### 快速上手：将工单转入人工队列

程序判断工单是否需要人工介入，达到业务阈值后转入人工队列。先将[条件判断定义](#noul条件判断)保存为 `needs_review.yaml`，或复制 [`needs_review.yaml`](examples/noul_evaluator/needs_review.yaml)。

```python
from lvren_jev import JevRuntime, NoulEvaluator, load_decision_definition
from business_tickets import (
    read_ticket_description,  # 读取工单描述
    enqueue_human_review,     # 加入人工处理队列
)

definition = load_decision_definition("needs_review.yaml")
with JevRuntime.from_config("typesafe.toml") as runtime:
    evaluator = NoulEvaluator.from_definition(definition, runtime=runtime)
    # 输入：工单 ID str；输出：描述 str，如 "客户明确要求转人工处理"。
    description = read_ticket_description("T-002")
    # 输入：str；输出示意：NoulResult(probability=0.92)。
    result = evaluator.evaluate(description)
    # 输入：阈值 float；输出：bool，此示例为 True。
    if result.is_true(threshold=0.8):
        # 输入：工单 ID str；输出：None。
        enqueue_human_review("T-002")
```

`probability` 表示条件成立的概率；`is_true()` 在本地比较阈值，不再调用 Jev。

#### 决策定义

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

#### 调用接口

```python
from lvren_jev import JevRuntime, NoulEvaluator, load_decision_definition

definition = load_decision_definition("needs_review.yaml")
with JevRuntime.from_config("typesafe.toml") as runtime:
    evaluator = NoulEvaluator.from_definition(definition, runtime=runtime)
    result = evaluator.evaluate("客户明确要求转人工处理")

print(result.probability)
print(result.is_true())
```

#### 返回结果与处理规则

通过 `from_definition()` 创建时，`evaluate(state)` 接收非空文本，并按 `input.field` 组装状态。直接构造 `NoulEvaluator` 且未指定 `input_field` 时，也可传入 JSON 对象。

返回 `NoulResult` 对象，示意结构：

```python
NoulResult(probability=0.92)
```

`probability` 范围为 `0` 到 `1`，表示条件成立的概率，没有单独的 `confidence` 字段。`result.to_dict()` 返回：

```python
{"probability": 0.92}
```

`result.is_true()` 默认判断概率是否大于等于 `0.5`；`result.is_true(threshold=0.8)` 可指定业务阈值。该方法仅做本地比较，返回 `bool`。实际转人工或其他动作仍由普通程序执行。

### 组合决策

适合同一份上下文需要同时分类、评分和条件判断的场景，例如工单分流。问题通过 `DecisionRequest.questions` 组合，共享 `state`；这是底层请求格式，不使用单个决策文件的 `kind`，也不由 `load_decision_definition()` 加载。

#### 快速上手：一次完成工单分流判断

对同一条工单，同时判断处理部门、紧急程度和是否转人工，再由程序统一执行分派。先将[组合问题定义](#组合决策)保存为 `ticket_questions.json`。

```python
import json
from pathlib import Path
from lvren_jev import DecisionRequest, JevRuntime
from business_tickets import (
    read_ticket_description,  # 读取工单描述
    apply_ticket_decisions,   # 根据判断结果分派工单、设置优先级和人工处理标记
)

# 输入：JSON 文件；输出：dict，以 team、urgency、needs_human 为键。
questions = json.loads(Path("ticket_questions.json").read_text(encoding="utf-8"))
# 输入：工单 ID str；输出：描述 str，如 "页面加载很慢，要求今天解决并转人工"。
description = read_ticket_description("T-003")
with JevRuntime.from_config("typesafe.toml") as runtime:
    # 输入：DecisionRequest(state={"message": str}, questions=dict)。
    # 输出：JevResponse，answers 为按问题名称分组的字典。
    response = runtime.execute(DecisionRequest(
        state={"message": description},
        questions=questions,
    ))
    # 输入：工单 ID str 和答案 dict，结构示意：
    # {
    #     "team": {"choice": "technical", "confidence": 0.94},
    #     "urgency": {"score": 2.0, "confidence": 0.9},
    #     "needs_human": {"noul": 0.97},
    # }
    # 输出：None；字段含义和处理规则见组合决策详解。
    apply_ticket_decisions("T-003", response.answers)
```

三个问题在同一个请求中提交。组合响应保留各原语的答案字段，程序按业务规则处理；不会自动转换为三个包装结果对象。

#### 问题定义

将以下内容保存为 `ticket_questions.json`，供快速上手及下方调用示例读取：

```json
{
  "team": {
    "type": "choice",
    "instructions": "Which team should handle this request?",
    "criteria": {
      "billing": "Charges and payments",
      "technical": "Software failures",
      "other": "None of these"
    }
  },
  "urgency": {
    "type": "score",
    "instructions": "How urgent is this request?",
    "criteria": ["Can wait", "This week", "Today"]
  },
  "needs_human": {
    "type": "noul",
    "instructions": "Does the user want to talk to a human?",
    "criteria": {
      "true": "The user explicitly asks for a person.",
      "false": "The user does not ask for a person."
    }
  }
}
```

外层键是问题名称，也用于读取返回答案。每个问题分别描述自己的 `type`、`instructions` 和 `criteria`。

#### 调用接口

```python
import json
from pathlib import Path
from lvren_jev import DecisionRequest, JevRuntime

questions = json.loads(Path("ticket_questions.json").read_text(encoding="utf-8"))
request = DecisionRequest(
    state={"message": "页面加载很慢，用户要求今天解决，并希望转人工。"},
    questions=questions,
)
with JevRuntime.from_config("typesafe.toml") as runtime:
    response = runtime.execute(request)

print(response.answers["team"])
print(response.answers["urgency"])
print(response.answers["needs_human"])
```

`execute(request: DecisionRequest)` 返回 `JevResponse`；连续调用 `classify()` 或 `evaluate()` 不会自动合并为这个请求。

#### 返回结果与处理规则

响应对象示意（这里的可选字段为空）：

```python
JevResponse(
    answers={
        "team": {
            "choice": "technical",
            "confidence": 0.94,
            "probabilities": {"billing": 0.02, "technical": 0.94, "other": 0.04},
        },
        "urgency": {"score": 2.0, "confidence": 0.9},
        "needs_human": {"noul": 0.97},
    },
    usage=None,
    model=None,
    raw=None,
)
```

- `answers`：按问题名组织的字典。Choice 答案使用 `choice`，Score 使用 `score`，Noul 使用 `noul`；Score 还可能包含 `legend` 和 `probabilities`。
- `usage`、`model`：服务返回的用量和模型信息，未提供时为 `None`。
- `raw`：保留原始响应，便于需要时检查。

组合接口不自动生成 `ClassificationResult`、`ScoreResult` 或 `NoulResult`，也不应用分类定义中的 `label` 映射和回退策略。程序应读取各答案，处理置信度、部门映射、优先级和人工判断阈值，再完成业务操作。

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

## 本地发布程序

仓库提供独立的 `lvren-jev-release` 业务入口。它把一次完整发布作为委派边界：程序锁定目标 commit，找到可达的上一个 SemVer 发布 tag，读取全部提交正文和未截断的实际 diff，再通过两层 Jev 判断决定“是否适合发布”和最高 SemVer 级别。决策定义位于 `src/lvren_jev/release/definitions/`，运行配置仍由 `JevRuntime` 管理，发布流程不改变通用决策原语。

先安装构建与上传工具，并准备一个只在真正上传步骤读取的 PyPI token 文件：

```powershell
python -m pip install build twine
```

只预览，不修改版本、提交、构建、上传或创建 tag：

```powershell
lvren-jev-release preview `
  --repo . `
  --runtime-config .\typesafe.toml `
  --target HEAD
```

真正执行完整发布时，显式使用 `publish` 并提供 token 文件路径。程序不会把 token 放进命令行，也不会打印或写入日志；用户名通过 `TWINE_USERNAME=__token__` 传给 Twine：

```powershell
lvren-jev-release publish `
  --repo . `
  --runtime-config .\typesafe.toml `
  --token-file 'C:\path\to\pypi-token' `
  --target HEAD
```

发布流程依次执行版本源修改、完整测试、独立 release 提交、wheel/sdist 构建、`twine check`、wheel 安装导入验证、分支推送、仅上传本版本两个产物、tag 创建与推送、PyPI SHA256 核对及从 PyPI 安装导入验证。任何步骤失败都会停止后续动作，并在 JSON 结果中返回 `failed_step`、`completed_actions` 和 `remote_state`；例如 PyPI 已上传但 tag 推送失败时不会假装成功，也不会自动递增版本重试。

安全边界：工作区不干净、没有可识别发布 tag、没有变更、diff 超过证据上限、Jev 低置信度/模糊、版本已存在于 Git 或 PyPI，都会结构化拒绝并保持发布零副作用。离线验收应使用临时 Git 仓库、假 Jev runtime 和假发布动作；本项目实现验收不读取真实 token，不上传 PyPI，不创建或推送真实发布 tag。

## 许可证

本项目采用 [MIT License](LICENSE)。你可以自由使用、复制、修改和分发本项目，包括用于商业项目；使用时请保留版权和许可证声明。项目按现状提供，不附带任何担保。
