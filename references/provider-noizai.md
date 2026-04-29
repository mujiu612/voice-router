# NoizAI Provider Notes for voice-router

这份文件只管 `voice-router` 中 NoizAI 这一层的接入约束、已知行为、常见坑和排查建议。

它不负责：
- route 选择逻辑
- Feishu 平台发送细节
- 其他 provider（MiniMax / xAI）

---

## 1. Responsibility in voice-router

NoizAI 在当前 voice-router 里属于 **底层 TTS provider**，负责把文本生成成本地音频文件。

典型位置：
- `models.model_noiz_default`
- `models.model_noiz_warm`
- `scripts/generate_noizai.py`

它只负责“生成音频”，不负责：
- route 决策
- opus 转码
- Feishu 实际消息发送

---

## 2. Current Implementation Path

当前 wrapper：
- `scripts/generate_noizai.py`

它现在直接调用 NoizAI HTTP 接口，而不是把 API key 通过子进程命令行再转交给外部脚本。

### Why

这样做的好处：
- 避免凭据出现在进程命令行参数里
- 降低对 workspace 外部实现路径的隐式依赖
- voice-router 自己就能定义更明确的安全边界（下载限制、输出校验、超时）

---

## 3. Credential Contract

`generate_noizai.py` 按以下顺序找凭据：

1. 环境变量 `NOIZ_API_KEY`
2. `~/.openclaw/.env`
3. `~/.noiz_api_key`

### Rule

- 如果 1 和 2 已可用，尽量不要依赖 `~/.noiz_api_key`
- 长期推荐把凭据放在 `~/.openclaw/.env`
- 不要把 key 写入 `voice_router.json`
- 不要把 key 写进 skill 文档或 reference 文件

---

## 4. Input Parameters Used by Wrapper

当前 `generate_noizai.py` 支持的主要输入：

- `--text`
- `--voice`
- `--output`
- `--format`
- `--lang`
- `--speed`
- `--timeout-sec`
- `--reference-audio`

### Current Voice Modes

NoizAI 在当前链路里有两种主要模式：

#### Mode A: voice id 模式

当配置提供：
- `voice`

会优先使用：
- `--voice-id <voice>`

典型例子：
- `model_noiz_default`

#### Mode B: reference audio 模式

当没有显式 `voice`，但有：
- `reference_mode`
- 或默认参考音频策略

wrapper 会选择参考音频路径，交给底层实现。

典型例子：
- `model_noiz_warm`

---

## 5. Language Behavior

如果没有显式传 `--lang`，wrapper 会做一个非常轻量的语言判定：

- 文本中含中文字符 → `cmn`
- 否则 → `en`

### Rule

- 这是实用兜底，不是严肃语言检测
- 对中英混合、特殊语言、方言场景不要过度信任自动判定
- 如果任务已知语言明确，优先在 model 配置里写清 `lang`

---

## 6. Default Reference Audio Behavior

当：
- 没显式 `voice`
- 也没显式传 `reference-audio`

wrapper 会根据语言选择默认参考音频 URL。

### Current Defaults

- 中文：`DEFAULT_REF_AUDIO_URL_CN`
- 英文：`DEFAULT_REF_AUDIO_URL_EN`

### Security Guardrails

- 仅允许 `https://` URL
- 仅允许少量 allowlist host（当前内置默认资源域名）
- 有下载大小上限
- 会做基础 content-type / 扩展名校验

### Risk

这意味着 reference-audio 模式仍然依赖：
- 外部 URL 可访问
- 下载成功
- 远端资源未失效

### Recommendation

如果某个参考音频是长期核心资产，后续更稳的做法是：
- 不依赖公网临时 URL
- 改为本地受控文件路径
- 关键链路优先使用固定 voice id

---

## 7. Output Contract

成功时，`generate_noizai.py` 至少返回：

```json
{
  "provider": "noizai",
  "voice": "b4775100",
  "lang": "cmn",
  "output": "/path/to/file.mp3",
  "format": "mp3",
  "size_bytes": 12345,
  "status": "ok"
}
```

失败时，返回结构化错误 JSON 到 stderr。

### Post-generation Probe

成功并不只看子进程退出码，还会检查：

- 文件是否存在
- 文件是否非空
- 输出是否其实是 JSON 错误体

这一步非常关键，能避免空文件或错误文本继续进入转码层。

---

## 8. Known Failure Modes

### 1) 凭据缺失

#### Symptom
- NoizAI 调用直接失败
- stderr 提示 API key 未配置

#### Root Cause
- `NOIZ_API_KEY` 缺失
- `~/.openclaw/.env` 未配置
- `~/.noiz_api_key` 不存在

#### Fix
- 优先在 `~/.openclaw/.env` 设置 `NOIZ_API_KEY`

---

### 2) 输出文件为空

#### Symptom
- wrapper 返回失败
- 或后续 probe 发现输出为空

#### Root Cause
- 底层实现异常
- provider 调用返回不完整
- 输出路径写入异常

#### Fix
- 检查底层 noiz_tts.py stderr
- 保持生成后 probe，不要跳过

---

### 3) 输出其实是 JSON 错误体

#### Symptom
- 文件存在
- 但后续转码失败
- probe 发现文件开头像 `{` 或 `[` 

#### Root Cause
- provider 返回了错误 JSON
- 底层实现把错误体落盘成了“假音频文件”

#### Fix
- 生成层直接判失败
- 不要把这种文件继续交给 ffmpeg

---

### 4) reference audio 下载失败

#### Symptom
- 没设置 voice id 时，参考音频模式失败
- 可能报网络错误、URL 失效、下载超时

#### Root Cause
- 参考音频依赖公网 URL
- 远端资源不可用

#### Fix
- 核心链路尽量改成稳定本地参考音频
- 或给 model 明确配置 voice id，减少对参考音频下载的依赖

---

## 9. Recommended Config Patterns

### Pattern A: 稳定默认声线

适用于：
- 高频日常使用
- 希望行为稳定
- 不依赖外部参考音频下载

推荐：
- 配 `voice`
- 配 `lang`
- 配 `timeout_sec`
- 配 `retry`

### Pattern B: 风格化参考音频模式

适用于：
- 特殊角色
- 声线更强调气质差异

注意：
- 稳定性通常弱于固定 voice id 模式
- 更依赖参考音频本身可用

---

## 10. Operational Recommendations

### Recommendation 1

如果一个 NoizAI model 是主路径，优先用固定 `voice id`，不要长期把公网 reference audio 模式当主链路。

### Recommendation 2

如果 reference-audio 模式只适合实验，不要把它挂成关键 slot 的 primary model。

### Recommendation 3

只要 NoizAI 输出失败、为空、或看起来像 JSON，就应在生成层立即失败，不要继续转码。

### Recommendation 4

对高频任务，建议在 smoke / integration tests 中至少保留一个 NoizAI 路径用例。

---

## 11. Contract With Other Layers

### With `voice_router.json`

NoizAI model 典型字段：

- `provider = noizai`
- `voice`
- `reference_mode`
- `lang`
- `timeout_sec`
- `retry`

### With `run_voice_pipeline.py`

pipeline 必须：
- 传入 `timeout_sec`
- 尊重 `retry`
- 对失败 attempt 做结构化记录

### With `transcode_to_opus.sh`

NoizAI 输出通常先作为中间音频，再由转码层统一变为 `opus`。

### With Feishu delivery

NoizAI 不直接对接 Feishu。Feishu 是否成功，取决于后续：
- 转码
- 校验
- delivery plan
- 运行时最终发送

---

## 12. Future Hardening

如果后续要把 NoizAI 链路补得更硬，优先建议：

1. 为 reference-audio 模式引入本地受控样本
2. 增加一条真实 NoizAI 生成 integration smoke test
3. 对底层 noiz_tts.py 的返回结构建立更明确的契约
4. 区分“provider API 失败”和“本地输出落盘失败”两类错误

---

## 13. Non-goals

这份文件不负责：

- 定义 route 选择优先级
- 定义 Feishu 平台发送规则
- 规定 slots / bindings 的业务命名
- 讨论 MiniMax / xAI 的实现细节

它只负责回答：

- NoizAI 在 voice-router 里怎么被接入
- 它的主要输入输出约束是什么
- 它最容易出哪些错
- 应该怎么排和怎么防
