# MiniMax Provider Notes for voice-router

这份文件只管 `voice-router` 中 MiniMax 这一层的接入约束、当前实现方式、常见故障与排查建议。

它不负责：
- route 优先级
- Feishu 平台发送细节
- NoizAI / xAI 的 provider 行为

---

## 1. Responsibility in voice-router

MiniMax 在当前 voice-router 中是底层 TTS provider 之一，负责把文本生成成本地音频文件。

典型位置：
- `models.model_minimax_default`
- `models.model_minimax_formal`
- `scripts/generate_minimax.py`

MiniMax 只负责“生成音频”，不负责：
- route 解析
- opus 转码
- Feishu 最终消息发送

---

## 2. Current Implementation Path

当前 wrapper：
- `scripts/generate_minimax.py`

特点：
- 直接走 MiniMax 的同步 HTTP TTS 路径
- 不依赖更大的 MiniMax skill runtime
- 目标是让 voice-router 对 provider 调用更可控、更轻量

### Current API Shape

当前 wrapper 使用：
- `POST {MINIMAX_API_BASE}/t2a_v2`

默认 `MINIMAX_API_BASE`：
- `https://api.minimaxi.com/v1`

---

## 3. Credential Contract

`generate_minimax.py` 按以下顺序找凭据：

1. 环境变量 `MINIMAX_API_KEY`
2. `~/.openclaw/.env`

### Rule

- 长期推荐使用 `~/.openclaw/.env`
- 不要把 key 写进 `voice_router.json`
- 不要把 key 写进 skill / reference 文档

---

## 4. Input Parameters Used by Wrapper

当前 `generate_minimax.py` 主要支持：

- `--text`
- `--voice`
- `--output`
- `--format`
- `--model`
- `--emotion`
- `--speed`
- `--volume`
- `--pitch`
- `--sample-rate`
- `--timeout-sec`

### Current Common Model Pattern

在 `voice_router.json` 里，MiniMax model 常见字段：

- `provider = minimax`
- `model = speech-2.8-hd`
- `voice = presenter_female` / `female-shaonv`
- `timeout_sec`
- `retry`

---

## 5. Output Contract

成功时，wrapper 至少返回：

```json
{
  "provider": "minimax",
  "voice": "presenter_female",
  "model": "speech-2.8-hd",
  "text_length": 25,
  "output": "/path/to/file.mp3",
  "format": "mp3",
  "size_bytes": 12345,
  "status": "ok"
}
```

失败时，返回结构化错误 JSON 到 stderr。

### Post-generation Probe

成功不只看 HTTP 200，还会继续检查：

- 输出文件是否存在
- 文件是否非空
- 文件内容是否其实是 JSON 错误体

这一步不能省，不然 provider 错误很容易被误传到转码层才爆。

---

## 6. Known Failure Modes

### 1) API key 缺失

#### Symptom
- wrapper 直接失败
- 提示 `MINIMAX_API_KEY is not set`

#### Root Cause
- 环境变量未配置
- `~/.openclaw/.env` 未配置

#### Fix
- 优先把 `MINIMAX_API_KEY` 放进 `~/.openclaw/.env`

---

### 2) 模型套餐不支持

#### Symptom
- wrapper 返回 provider 错误
- 典型报错类似：
  - `your current token plan not support model, speech-2.8-hd`

#### Root Cause
- 当前账号 / token plan 不支持请求的 model
- 这不是 route 逻辑错误，也不是脚本结构错误

#### Failure Layer

生成层（provider capability / account plan）

#### Correct Diagnosis

应判断为：
- provider 可达
- 请求发出去了
- 但账号权限 / 套餐能力不支持目标模型

#### Correct Fix

- 切换到当前套餐支持的 model
- 或恢复套餐 / 权限
- 不要误判成“脚本坏了”或“route 配错了”

#### Prevention

- 在 provider notes 中记录真实失败样本
- 如果某模型长期受套餐限制，不要把它当唯一主链路

---

### 3) 返回 JSON 错误体而不是音频

#### Symptom
- 请求有响应
- 但落盘内容不是音频，而是 JSON 错误信息

#### Root Cause
- API 返回了错误 payload
- wrapper 若不做 probe，后续转码才会炸

#### Fix
- 在生成层就识别并失败
- 不让错误 JSON 混进下游音频流程

---

### 4) 请求参数不兼容

#### Symptom
- provider 返回错误
- 可能与 format / sample_rate / voice / model 组合有关

#### Root Cause
- model、voice、audio_setting 参数组合超出 provider 支持范围

#### Fix
- 先确认 model 是否受支持
- 再确认 voice 是否匹配该 model
- 再看 sample_rate / format 是否合理

---

### 5) urllib3 / LibreSSL 警告

#### Symptom
- 日志里出现 `urllib3 v2 only supports OpenSSL 1.1.1+ ... LibreSSL ...`

#### Root Cause
- Python / SSL 环境与 urllib3 的兼容性警告

#### Diagnosis Rule

- 这类 warning 不一定是本次失败主因
- 需要区分“warning 存在”和“真正导致失败的 provider 错误”

#### Current Example

在一次真实集成烟测里，虽然日志有 LibreSSL warning，但真正失败原因是：
- `your current token plan not support model, speech-2.8-hd`

所以不能被 warning 带偏。

---

## 7. Recommended Config Patterns

### Pattern A: 正式播报主链路

适用于：
- 新闻播报
- 提醒通知
- 更正式、更清晰的语气

推荐：
- 明确写 `model`
- 明确写 `voice`
- 写 `timeout_sec`
- 写 `retry`

### Pattern B: MiniMax 作为 fallback

适用于：
- 主 provider 不稳定时作为兜底
- 想保留另一条 provider 路径

注意：
- 如果套餐限制较多，不要把受限 model 当全局唯一主链路

---

## 8. Operational Recommendations

### Recommendation 1

如果某个 MiniMax model 依赖套餐权限，最好在 notes 中明确标记，不要默认假设所有环境都能跑。

### Recommendation 2

如果新闻或提醒类任务长期依赖 MiniMax，建议保留一个已确认可用的 fallback model / fallback provider。

### Recommendation 3

出现 provider 错误时，先分辨：
- 套餐 / 权限问题
- 参数问题
- 网络 / HTTP 问题
- 输出落盘问题

不要把这些都混成“MiniMax 挂了”。

### Recommendation 4

如果做 integration smoke，MiniMax 用例要允许“外部 plan 不支持”这种失败存在，但要把它标注成外部约束，不算 skill 设计缺陷。

---

## 9. Contract With Other Layers

### With `voice_router.json`

MiniMax model 常见字段：

- `provider = minimax`
- `model`
- `voice`
- `timeout_sec`
- `retry`

### With `run_voice_pipeline.py`

pipeline 必须：
- 传 `timeout_sec`
- 尊重 `retry`
- 记录失败 attempt

### With `transcode_to_opus.sh`

MiniMax 输出一般先作为中间音频，再统一转为 opus。

### With Feishu delivery

MiniMax 不直接决定 Feishu 是否成功。
Feishu 是否闭环，仍取决于：
- 转码
- probe
- delivery plan
- 运行时最终发送

---

## 10. Future Hardening

如果后续要把 MiniMax 链路补得更硬，优先建议：

1. 增加一个“当前套餐可用模型”清单或探测逻辑
2. 把 provider capability / plan errors 单独分类
3. 增加一条在可用模型上的 MiniMax integration smoke
4. 把常见 provider 参数组合限制沉淀到 reference

---

## 11. Non-goals

这份文件不负责：

- route 选择优先级
- Feishu 平台发送策略
- NoizAI / xAI 的 provider 行为
- slots / bindings 的业务命名

它只负责回答：

- MiniMax 在 voice-router 里怎么接入
- 它最容易出什么错
- 什么叫套餐 / 权限失败
- 应该怎么排和怎么防
