# voice_router.json Config Schema (v1)

这不是 JSON Schema 规范文件，而是给人看的结构契约。目标是把 `voice_router.json` 的字段职责、命名规则、读取顺序和常见修改位置钉死，减少配置漂移。

---

## 1. Top-level Structure

```json
{
  "version": 1,
  "meta": {},
  "models": {},
  "slots": {},
  "bindings": {},
  "routing": {},
  "delivery": {},
  "guidance": {},
  "intent_examples": {},
  "evolution": {},
  "validation": {}
}
```

### Top-level Field Roles

- `version`: 配置版本号。当前固定为 `1`。
- `meta`: 人类可读元信息，不参与核心路由决策。
- `models`: 底层 provider / voice / timeout / retry 定义。
- `slots`: 人话层的“声音角色位”。
- `bindings`: task / agent 到 slot 的默认绑定。
- `routing`: 路由选择顺序与全局行为开关。
- `delivery`: 平台发送 profile。
- `guidance`: 对话时的术语映射与交互偏好。
- `intent_examples`: 静态意图示例，用于帮助理解，不应替代真实解析。
- `evolution`: 偏好晋升策略。
- `validation`: 音频与发送闭环校验规则。

---

## 2. models

`models` 是底层能力层。键名必须稳定，供 `slots` 引用。

### Shape

```json
"models": {
  "model_minimax_formal": {
    "enabled": true,
    "provider": "minimax",
    "display_name": "MiniMax 正式播报女声",
    "model": "speech-2.8-hd",
    "voice": "presenter_female",
    "timeout_sec": 60,
    "retry": 1,
    "tags": ["formal", "broadcast"]
  }
}
```

### Required Fields

- `enabled`: `boolean`
- `provider`: `string`

### Common Optional Fields

- `display_name`: `string`
- `model`: `string`
- `voice`: `string | null`
- `reference_mode`: `string`
- `lang`: `string`
- `codec`: `string`
- `sample_rate`: `number`
- `bit_rate`: `number`
- `timeout_sec`: `number`
- `retry`: `number`
- `tags`: `string[]`

### Rules

- `enabled=false` 的 model 允许存在，但执行层应跳过或拒绝使用。
- `timeout_sec` 和 `retry` 是执行参数，不是展示字段。
- `voice` 为空时，必须有别的可行生成方式，例如 `reference_mode`。

### Naming

推荐：
- `model_minimax_formal`
- `model_noiz_default`
- `model_xai_default`

不推荐：
- `model1`
- `new_model`
- `final_voice_v3`

---

## 3. slots

`slots` 是对用户说人话时最重要的一层。它表达“这个声音在业务上扮演什么角色”。

### Shape

```json
"slots": {
  "slot_morning": {
    "enabled": true,
    "display_name": "新闻播报女声",
    "persona": "正式、清晰、适合新闻播报",
    "primary_model": "model_minimax_formal",
    "fallback_models": ["model_xai_default", "model_noiz_default"]
  }
}
```

### Required Fields

- `enabled`: `boolean`
- `display_name`: `string`
- `primary_model`: `string`

### Common Optional Fields

- `persona`: `string`
- `fallback_models`: `string[]`

### Rules

- `primary_model` 必须引用一个存在的 model id。
- `fallback_models` 中每个值都必须引用一个存在的 model id。
- `enabled=false` 的 slot 不应被路由层选中。
- slot 命名表达角色或场景，不表达 provider 实现。

---

## 4. bindings

`bindings` 决定默认路由命中。

### Shape

```json
"bindings": {
  "task_bindings": {
    "default": "slot_main",
    "daily_news": "slot_morning"
  },
  "agent_bindings": {
    "main": "slot_main"
  }
}
```

### task_bindings

- 键：任务名，例如 `daily_news`
- 值：slot id，例如 `slot_morning`
- 特殊键：`default`

### agent_bindings

- 键：agent id，例如 `main`
- 值：slot id，例如 `slot_main`

### Priority

默认优先级：
1. `explicit_slot`
2. `explicit_model`
3. `task_binding`
4. `agent_binding`
5. `task_default`

### Rules

- `task_bindings.<task>` 与 `agent_bindings.<agent>` 的值都必须引用有效 slot。
- `task_binding` 优先于 `agent_binding`。
- `default` 只作为最终兜底，不应覆盖显式指定。

---

## 5. routing

`routing` 控制全局选择顺序与全局开关。

### Shape

```json
"routing": {
  "default_selection_order": [
    "explicit_slot",
    "explicit_model",
    "task_binding",
    "agent_binding",
    "task_default"
  ],
  "allow_model_fallback": true,
  "stop_on_empty_audio": true,
  "stop_on_probe_failure": true,
  "allow_direct_mp3_send": false
}
```

### Rules

- `default_selection_order` 里的 step 名必须和脚本实现一致。
- `allow_model_fallback=false` 时，不应继续尝试 slot 内 fallback models。
- `allow_direct_mp3_send=false` 表示不能把 mp3 当成最终平台输出偷懒发出。

---

## 6. delivery

`delivery` 定义不同平台的投递策略。

### Shape

```json
"delivery": {
  "default_target_mode": "current_channel",
  "allow_cross_platform_override": true,
  "fallback_channel": "feishu",
  "profiles": {
    "feishu": {
      "enabled": true,
      "display_name": "飞书",
      "preferred_format": "opus",
      "send_mode": "audio_file",
      "allow_direct_mp3_send": false,
      "output_dir": "/path/to/tmp",
      "filename_prefix": "feishu-voice"
    }
  }
}
```

### Profile Required Fields

- `enabled`: `boolean`
- `preferred_format`: `string`
- `send_mode`: `string`
- `output_dir`: `string`
- `filename_prefix`: `string`

### Common Optional Fields

- `display_name`: `string`
- `allow_direct_mp3_send`: `boolean`
- `supports_native_voice`: `boolean`
- `supports_duration_display`: `boolean`

### Rules

- 未启用的 profile 不应被投递层选中。
- 平台级 `allow_direct_mp3_send` 比全局 routing 更具体，冲突时优先平台级。
- `output_dir` 应为当前机器上真实可写目录。

---

## 7. guidance

`guidance` 用于对话层，不直接驱动路由，但会影响解释方式。

### Common Fields

- `show_on_first_use`
- `suggest_on_ambiguous_intent`
- `prefer_human_terms`
- `explain_before_persistent_change`
- `human_terms`

### Rules

- `human_terms` 只负责对外术语映射，不要拿来替代真实字段名。

---

## 8. intent_examples

静态示例，帮助理解常见用户表达。

### Rules

- 它不是执行规则源。
- 不要因为 `intent_examples` 写了某个例子，就绕过真实路由逻辑。

---

## 9. evolution

偏好晋升配置。

### Common Fields

- `enable_dynamic_learning`
- `promotion_threshold`
- `remind_on_related_settings`
- `max_promotion_reminders_per_session`
- `archive_after_promotion`

### Rules

- `promotion_threshold` 应大于等于 2，避免一次临时偏好就自动晋升全局默认。

---

## 10. validation

执行闭环的强约束层。

### Common Fields

- `require_nonempty_audio`
- `require_duration_probe`
- `require_final_send_ok`
- `prefer_user_confirm_for_platform_delivery_success`

### Rules

- `require_nonempty_audio=true` 时，空文件直接失败。
- `require_duration_probe=true` 时，无法探测时长直接失败。
- `require_final_send_ok=true` 时，不能把“准备发送”当成成功。

---

## 11. Recommended Read Order

### 问“当前默认声音是什么”

1. 查 `explicit_slot` / `explicit_model`
2. 查 `bindings.task_bindings.<task>`
3. 查 `bindings.agent_bindings.<agent>`
4. 查 `bindings.task_bindings.default`
5. 查命中的 `slot`
6. 查该 `slot.primary_model`
7. 查对应 `model`
8. 查目标平台 `delivery.profiles.<channel>`

### 问“该改哪层”

- 改“谁默认用哪个声音” → 改 `bindings`
- 改“这个声音角色位映射到哪个模型” → 改 `slots`
- 改“底层 provider / voice / timeout / retry” → 改 `models`
- 改“平台输出格式 / 发送方式” → 改 `delivery`

---

## 12. Validation Checklist

每次改配置后，至少检查：

- 所有 slot 引用的 model 是否存在
- 所有 binding 引用的 slot 是否存在
- disabled model 是否被某个 slot 误设为 primary model
- disabled delivery profile 是否仍可能被选中
- Feishu profile 是否仍保持 `preferred_format=opus`
- `allow_direct_mp3_send` 是否和平台策略一致

推荐在人工检查之外，再跑一次机器校验：

```bash
python3 scripts/validate_config.py \
  --config voice_router.json
```

### Current Validator Coverage

`validate_config.py` 当前会检查：

- 顶层 key 是否缺失
- models / slots / bindings / delivery profiles 的基础结构是否合法
- slot / binding / fallback 是否引用了不存在的对象
- disabled model / slot 是否仍被默认引用
- routing 的 selection order 是否包含非法 step
- Feishu profile 的关键约束是否偏离推荐值

注意：它是当前 v1 的实用校验器，不是完整 JSON Schema 替代品。

---

## 13. Non-goals

这个配置不负责：

- 文案创作
- 多角色剧本拆分
- DAW 级音频后期
- 视频时间线混音
- 非语音媒体投递

它只负责：

- 语音路由
- 默认绑定
- provider 选择
- 平台发送策略
- 校验与闭环要求
