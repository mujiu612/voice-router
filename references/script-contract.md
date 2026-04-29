# Script Contract for voice-router (v1)

这份文件定义 `voice-router` 相关脚本的职责边界、输入参数、输出 JSON 约定、错误返回约定，以及它们与 `voice_router.json` 的字段契约。

目标：避免出现“文档写一套、脚本读一套、配置又是另一套”的漂移。

---

## 1. General Rules

所有脚本默认遵守以下约束：

### 1.1 Output Contract

- 成功时：输出 **JSON 到 stdout**
- 失败时：输出 **JSON 到 stderr**
- 不要把人类说明性日志混进 stdout 的 JSON 结构里
- 返回码：
  - `0` = 成功
  - `1` = 执行失败
  - `2` = 输入参数或前置条件错误

### 1.2 Path Contract

- 路径应从 skill 当前目录动态解析，不写死 Linux 专用路径
- `voice_router.json` 默认路径：`voice_router.json`
- 输出目录优先从 delivery profile 读取

### 1.3 Config Contract

脚本只能依赖以下来源：

1. CLI 参数
2. `voice_router.json`
3. 环境变量 / `~/.openclaw/.env`

不要：
- 临时发明隐式字段
- 在脚本内部写死和配置冲突的路由规则
- 绕过配置直接改默认行为

---

## 2. route_voice.py

### Responsibility

只负责：
- 读取配置
- 解析 `explicit_slot / explicit_model / task_binding / agent_binding / task_default`
- 输出结构化 route plan

不负责：
- 调 provider
- 生成音频
- 转码
- 发送消息

### Inputs

CLI 参数：
- `--config`
- `--slot`
- `--model`
- `--task`
- `--agent`
- `--channel`

### Reads From Config

- `routing.default_selection_order`
- `bindings.task_bindings`
- `bindings.agent_bindings`
- `slots`
- `models`
- `delivery.fallback_channel`
- `delivery.profiles`

### Success Output Shape

```json
{
  "source": "task_binding",
  "chosen_slot": "slot_morning",
  "chosen_model": "model_minimax_formal",
  "fallback_models": ["model_xai_default", "model_noiz_default"],
  "provider": "minimax",
  "provider_model": "speech-2.8-hd",
  "voice": "presenter_female",
  "reference_mode": null,
  "model_display_name": "MiniMax 正式播报女声",
  "delivery_channel": "feishu",
  "delivery_profile": {}
}
```

### Required Success Fields

- `source`
- `chosen_slot` or `chosen_model`
- `fallback_models`
- `provider`
- `delivery_channel`
- `delivery_profile`

### Failure Conditions

- slot 不存在
- model 不存在
- slot / model / delivery profile 被禁用
- 没有任何 route 命中

### Failure Output Shape

```json
{
  "error": "slot not found: slot_xxx"
}
```

---

## 3. run_voice_pipeline.py

### Responsibility

负责串联：
- 路由解析
- model fallback 尝试
- provider 生成
- opus 转码
- Feishu delivery plan 准备

不负责：
- 最终平台消息发送

### Inputs

CLI 参数：
- `--config`
- `--text`
- `--task`
- `--agent`
- `--channel`
- `--slot`
- `--model`
- `--filename-suffix`

### Reads From Config

- `models.*`
- `slots.*`
- `delivery.profiles.*`
- route output 中的 `chosen_model` / `fallback_models`

### Required Behavior

- 必须尊重 `enabled`
- 必须把 `timeout_sec` 传给下游生成脚本
- 必须尊重 `retry`
- disabled model 必须跳过，不得当正常主模型继续尝试
- 如果所有尝试失败，必须返回完整 attempts 信息

### Success Output Shape

```json
{
  "status": "ok",
  "route": {},
  "selected_attempt": {},
  "attempts": [],
  "generation": {},
  "transcode": {},
  "delivery": {}
}
```

### Required Success Fields

- `status`
- `route`
- `selected_attempt`
- `attempts`
- `generation`
- `transcode`
- `delivery`

### Failure Output Shape

```json
{
  "status": "error",
  "error": "all model attempts failed"
}
```

### Attempts Contract

每个 attempt 至少应包含：
- `model_id`
- `provider`
- `status`

推荐附带：
- `retry_attempts_used`
- `error`
- `generation`

---

## 4. generate_noizai.py

### Responsibility

只负责：
- 调 NoizAI 生成音频
- 保存到本地文件
- 对输出做最基础的存在 / 非空 / 非 JSON 校验
- 输出结果 JSON

### Inputs

CLI 参数：
- `--text`
- `--voice`
- `--output`
- `--format`
- `--lang`
- `--speed`
- `--timeout-sec`
- `--reference-audio`

### Credential Contract

按以下顺序找凭据：
1. `NOIZ_API_KEY`
2. `~/.openclaw/.env`
3. `~/.noiz_api_key`

### Success Output Required Fields

- `provider`
- `output`
- `format`
- `size_bytes`
- `status`

---

## 5. generate_minimax.py

### Responsibility

只负责 MiniMax TTS 调用与本地文件产出。

### Inputs

CLI 参数：
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

### Credential Contract

按以下顺序找凭据：
1. `MINIMAX_API_KEY`
2. `~/.openclaw/.env`

### Success Output Required Fields

- `provider`
- `voice`
- `model`
- `output`
- `format`
- `size_bytes`
- `status`

---

## 6. generate_xai.py

### Responsibility

只负责 xAI TTS 调用与本地文件产出。

### Inputs

CLI 参数：
- `--text`
- `--voice`
- `--output`
- `--format`
- `--language`
- `--sample-rate`
- `--bit-rate`
- `--timeout-sec`

### Credential Contract

按以下顺序找凭据：
1. `XAI_API_KEY`
2. `~/.openclaw/.env`

### Success Output Required Fields

- `provider`
- `voice`
- `output`
- `format`
- `size_bytes`
- `status`

---

## 7. transcode_to_opus.sh

### Responsibility

只负责：
- 将输入音频转为 opus
- 对输出做最基础校验
- 返回转码结果 JSON

### Inputs

位置参数：
- `<input-audio>`
- `<output-opus>`

### Required Behavior

- 输入不存在时失败
- 输入为空时失败
- 输入如果是 JSON / 文本伪装音频时失败
- ffmpeg 转码失败时返回结构化错误
- ffprobe 探测失败时返回结构化错误

### Success Output Required Fields

- `status`
- `input`
- `output`
- `codec`
- `duration_sec`
- `size_bytes`

---

## 8. deliver_feishu.py

### Responsibility

只负责：
- 检查最终音频文件
- 探测 duration
- 生成 Feishu delivery plan

不负责：
- 直接发飞书消息
- 调 HTTP API 绕过运行时

### Inputs

CLI 参数：
- `--input`
- `--target-mode`
- `--filename-prefix`

### Required Behavior

- 文件不存在时失败
- 文件为空时失败
- duration probe 失败时失败
- 成功时必须输出 `send_via=openclaw_message_tool`

### Success Output Required Fields

- `status`
- `channel`
- `target_mode`
- `path`
- `filename`
- `duration_sec`
- `send_via`
- `send_mode`

---

## 9. validate_config.py

### Responsibility

只负责配置一致性校验。

不负责：
- 修改配置
- 自动修复
- 调 provider
- 调发送链路

### Inputs

CLI 参数：
- `--config`

### Required Checks

- 顶层 key 是否缺失
- `models / slots / bindings / delivery` 基础结构是否合法
- slot / binding / fallback 是否引用了不存在的对象
- disabled model / slot 是否仍被默认引用
- routing selection order 是否含非法 step
- Feishu 关键约束是否偏离推荐值

### Success Output Shape

```json
{
  "status": "ok",
  "error_count": 0,
  "warning_count": 0,
  "issues": []
}
```

### Failure Output Shape

```json
{
  "status": "error",
  "error_count": 1,
  "warning_count": 2,
  "issues": [
    {
      "level": "error",
      "path": "slots.slot_x.primary_model",
      "message": "references unknown model: model_x"
    }
  ]
}
```

---

## 10. Drift Prevention Rules

为避免漂移，后续新增脚本或修改脚本时，默认遵守：

1. 如果脚本新增读取了配置字段，必须同步更新：
   - `references/config-schema.md`
   - 本文件 `script-contract.md`

2. 如果脚本修改了输出 JSON 结构，必须同步更新本文件的 output contract。

3. 如果某个字段只是“预留”，但执行层还未真正消费，必须在文档里明确标注，不要假装它已完全生效。

4. 如果平台链路规则变化，必须同步更新：
   - `references/platform-feishu.md`
   - `deliver_feishu.py` 的 contract

---

## 11. Smoke Tests

当前已补：

- `scripts/smoke_tests.py`

运行方式：

```bash
python3 scripts/smoke_tests.py
```

当前 smoke tests 已覆盖：

- `validate_config.py` 对当前配置返回 ok
- `task_binding` 优先于 `agent_binding`
- 无 task binding 时走 `agent_binding`
- 无 task / agent 时走 `task_default`
- disabled slot 会被拒绝
- slot primary_model 指向 disabled model 时 validator 发 warning
- transcode 输入为空时返回结构化错误

## 12. Provider Integration Smoke Contract

当前已补：

- `scripts/provider_integration_smoke.py`

运行方式示例：

```bash
python3 scripts/provider_integration_smoke.py \
  --config voice_router.json \
  --providers noizai minimax \
  --models model_noiz_default model_minimax_formal
```

### Responsibility

它负责：
- 真调用 provider 生成短文本音频
- 真检查生成结果
- 真跑 opus 转码
- 输出结构化测试结果

它不负责：
- 最终平台发送
- 把外部套餐/权限限制误判成 skill 设计失败

### Result Classification

当前结果分三类：

- `pass`: 真生成成功，且能成功转 opus
- `external_constraint`: provider 可达，但因套餐 / model capability / 外部权限限制导致失败
- `hard_fail`: 可以合理归因到当前 skill / 脚本 / 本地执行链路的失败

### Rule

- `external_constraint` 不应直接算作 skill 设计缺陷
- `hard_fail` 才应优先视为当前实现需要修的问题
- 如果分类规则扩展，必须同步更新本文件与 provider references

## 13. Recommended Future Tests

后续建议继续补这些最小回归测试：

- disabled model 在 pipeline 中被 skip 后，attempts 结构仍正确
- Feishu profile 缺少 `preferred_format` 时 validator 报错
- deliver_feishu 输入不可 probe 时返回结构化错误
- route output 和 script-contract 定义字段完全一致
- pipeline 在所有 attempts 失败时返回完整结构化错误
- provider integration smoke 对更多 provider / model 组合给出稳定分类

这些测试不用多，但必须覆盖最容易漂的边界。
