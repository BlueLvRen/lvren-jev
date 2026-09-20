# Jev 本地 Playground 与 CLI

这个目录提供两个入口：

- `typesafe_playground.py`：启动明亮主题的浏览器 Playground。
- `typesafe_cli.py`：供 Codex 或其他本地脚本调用，输出 JSON。

两者都通过官方 `typesafe-sdk` 调用 TypeSafe Jev，并在一个进程内复用同一个 `TypeSafeClient`。

本项目采用 [MIT License](LICENSE)。`typesafe-sdk`、TypeSafe API 和 Jev 模型属于第三方服务或依赖，分别遵循其自身的许可证、服务条款和使用限制。

## 环境准备

以下命令以 Windows PowerShell 为例。项目要求 Python 3.11 或更高版本，因为代码使用了内置 `tomllib` 和现代类型语法；运行 Playground 还需要可用的浏览器和网络连接。

### 1. 获取项目

如果尚未下载项目：

```powershell
cd C:\Project\4-Python
git clone git@github.com:BlueLvRen/typedafe-jve.git typesafe_jev
cd typesafe_jev
```

如果项目已经存在，只需进入目录：

```powershell
cd C:\Project\4-Python\typesafe_jev
```

### 2. 创建虚拟环境并安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install typesafe-sdk
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

如果要使用 `omnilabs` Profile，再创建 `typesafe.secrets.omnilabs.toml`，内容格式相同。两个密钥文件已被 `.gitignore` 忽略，禁止提交到 Git 或写入命令行参数、环境变量。

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

[typesafe.profiles.omnilabs]
api_key_file = "typesafe.secrets.omnilabs.toml"
base_url = "https://omnilabs.vibeadmin.cn"
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

`typesafe.secrets.toml` 和 `typesafe.secrets.*.toml` 已加入 `.gitignore`。两组旧配置已分别迁移到 `official` 和 `omnilabs` Profile。由于旧 Key 曾以明文保存，建议登录 TypeSafe Console 后分别撤销旧 Key 并创建新 Key，再只替换对应密钥文件中的值。

## 启动 Playground

在 `C:\Project\4-Python` 下执行：

```powershell
python typesafe_jev\typesafe_playground.py
```

切换来源启动：

```powershell
python typesafe_jev\typesafe_playground.py --profile omnilabs
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
python typesafe_jev\typesafe_cli.py `
  --state '{"message":"页面加载要 8 秒，用户希望今天解决。","channel":"web"}' `
  --questions '{"team":{"type":"choice","instructions":"Which team should handle this request?","criteria":{"billing":"Charges and payments","technical":"Software failures","other":"None of these"}},"urgency":{"type":"score","instructions":"How urgent is this request?","criteria":["Can wait","This week","Today"]},"urgent":{"type":"noul","instructions":"Does the sender request help today?"}}' `
  --pretty
```

也可以从文件读取：

```powershell
python typesafe_jev\typesafe_cli.py `
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
python -m unittest discover -s typesafe_jev -p "test_*.py" -v
```
