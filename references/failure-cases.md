# Failure Cases for voice-router

这份文件记录 voice-router 相关的真实高频故障模式。

目标不是抱怨“出过什么错”，而是把这些问题变成可复用的排障经验，避免以后重复踩坑。

---

## Case 1. Feishu 看似发了，用户侧实际不可播放

### Symptom

- 发送流程表面返回成功
- 助手容易误以为“已发送完成”
- 但用户在飞书侧点不开，或者收到的不是预期体验

### Root Cause

把“平台返回成功”误当成最终成功，没有把“用户侧可播放”当成闭环标准。

### Failure Layer

发送层

### Correct Diagnosis

应判断为：
- Level 2（delivery invocation）可能成功
- 但 Level 3（user-side playback）未闭环

### Correct Fix

- 不直接宣布“已完成”
- 明确说明发送层未完成体验闭环
- 优先检查最终格式、Feishu 支持方式和用户侧播放结果

### Prevention

- 在 Feishu 场景默认把“用户侧可播放”视为最终闭环
- 发送反馈必须区分“已发送”与“已确认可播放”

---

## Case 2. 直接拿 mp3 发飞书，图省事但链路不稳

### Symptom

- 本地已经有 mp3
- 助手倾向于直接把 mp3 当最终产物发出去
- 看似少一步，但实际兼容性和体验不稳定

### Root Cause

把“已有文件”误当成“符合平台稳定链路”，没有遵守 Feishu 推荐输出格式。

### Failure Layer

发送层 / 平台适配层

### Correct Diagnosis

这不是 provider 问题，而是平台链路策略选错。

### Correct Fix

- 对 Feishu 优先走 `opus + audio_file`
- 显式禁止 `allow_direct_mp3_send=true` 的偷懒路径
- 把 mp3 视为中间产物，不视为当前稳定最终产物

### Prevention

- `delivery.profiles.feishu.allow_direct_mp3_send = false`
- `platform-feishu.md` 明确写入反模式

---

## Case 3. TTS 生成出空文件或错误 JSON，被误当音频继续往下走

### Symptom

- provider 调用后有输出文件
- 但文件为空，或内容其实是错误 JSON
- 后续转码或发送阶段才炸

### Root Cause

没有在生成后立刻做“文件存在 / 非空 / 非 JSON”校验，导致错误被延后暴露。

### Failure Layer

生成层，随后蔓延到校验层

### Correct Diagnosis

根因在生成层，不是转码工具本身坏了。

### Correct Fix

- 生成脚本成功后立刻 probe 文件
- 遇到空文件或 JSON 错误体，直接在生成层失败
- 不要把坏文件继续交给 ffmpeg / ffprobe

### Prevention

- 所有 provider wrapper 保持统一输出探测逻辑
- `validate_config.py` 虽然不检查运行结果，但执行层必须保留 probe 约束

---

## Case 4. route 顺序看起来对，代码实际没真按顺序走

### Symptom

- 文档写了 `task_binding > agent_binding > task_default`
- 但脚本内部把几种 binding 混在一个函数里解析
- 结果 source 名义上不同，实际命中逻辑却揉在一起

### Root Cause

实现偷懒，把多个 step 合并成一个通用解析函数，导致 selection order 失真。

### Failure Layer

路由层

### Correct Diagnosis

这是实现和设计约定不一致，不是配置写错。

### Correct Fix

- 把 `task_binding`、`agent_binding`、`task_default` 分开解析
- 保证 selection order 在代码里真实逐步执行

### Prevention

- `script-contract.md` 钉死 `route_voice.py` 的 route contract
- 以后改 route 脚本时，必须同步检查 selection order 是否仍真实生效

---

## Case 5. disabled model 仍被当主模型硬上

### Symptom

- 某个 model 在配置里 `enabled=false`
- 但 slot 仍把它设为 `primary_model`
- 执行层还先拿它尝试，失败后才 fallback

### Root Cause

配置层表达了“禁用”，执行层却没有真正消费 `enabled`。

### Failure Layer

路由层 / 生成层

### Correct Diagnosis

这不是 provider 恰好失败，而是执行层没有尊重配置状态。

### Correct Fix

- 路由层对 disabled slot / model 直接拒绝
- pipeline 对 disabled model 直接 skip
- validator 对“slot primary_model 指向 disabled model”至少给 warning

### Prevention

- 每次改配置后跑 `validate_config.py`
- 避免让 disabled model 继续挂在 primary 上当“假默认”

---

## Case 6. timeout / retry 写进配置了，但执行层根本没吃到

### Symptom

- 配置中有 `timeout_sec`、`retry`
- 文档也写了它们会影响执行
- 但脚本实际没把它们传给下游生成器，也没做重试

### Root Cause

字段存在于配置层，但没有接进执行层，形成“假生效字段”。

### Failure Layer

生成层 / 实现契约层

### Correct Diagnosis

这类问题本质上是配置漂移，不是单次 provider 偶发失败。

### Correct Fix

- pipeline 显式把 `timeout_sec` 传给 provider wrapper
- pipeline 实现基于 `retry` 的最小重试循环
- 在 `script-contract.md` 里把它写成必须行为

### Prevention

- 新增配置字段时，不要先写文档再忘了接实现
- 把“字段已实现 / 字段仅预留”明确区分

---

## Case 7. 改配置时改错层，结果影响范围失控

### Symptom

用户本来只是说：
- “以后 daily_news 默认用正式一点的女声”

但执行时如果直接去改 model 或全局默认，可能会造成：
- 影响范围过大
- 别的 slot / task 也一起被改掉

### Root Cause

没有先判断用户是在改：
- binding
- slot
- model
- delivery

### Failure Layer

配置修改层 / 交互理解层

### Correct Diagnosis

这是修改层级判断错误，不是 JSON 语法错误。

### Correct Fix

- 先问清影响范围
- 默认按最小影响面优先：
  - 任务默认 → `bindings.task_bindings`
  - agent 默认 → `bindings.agent_bindings`
  - 声音角色位映射 → `slots`
  - provider/voice/timeout → `models`

### Prevention

- `config-schema.md` 固定“该改哪层”规则
- `SKILL.md` 固定 quick decision table

---

## Case 8. 准备好了 delivery plan，就误说“已经发给你了”

### Symptom

- pipeline 已成功生成 route / audio / transcode / delivery plan
- 助手容易直接把这当成最终完成

### Root Cause

把“准备发送成功”与“最终实际发送成功”混为一谈。

### Failure Layer

发送层 / 交付语义层

### Correct Diagnosis

delivery plan 只是运行时发送前的最后准备，不等于消息已经投递。

### Correct Fix

- 只有运行时实际完成发送，才能说“已发送”
- 如果只到了 delivery plan，应该说“已准备好发送链路”或“发送计划已就绪”

### Prevention

- `deliver_feishu.py` contract 明确：只负责 delivery plan，不负责 actual send
- `platform-feishu.md` 明确禁止把 plan 当 success

---

## 9. Recommended Use of This File

每次遇到新的稳定性问题，按下面结构追加：

- Symptom
- Root Cause
- Failure Layer
- Correct Diagnosis
- Correct Fix
- Prevention

不要只记“怎么临时修好”，一定把：
- 当时卡在哪层
- 为什么误判
- 以后怎么提前拦住

也一并写进去。

---

## 10. Priority of Existing Risks

按当前经验，最值得长期盯住的风险顺序：

1. Feishu 假成功 / 用户侧不可播放
2. route 实现与文档优先级漂移
3. disabled model / 假默认继续挂着
4. timeout / retry / allow_direct_mp3_send 这类字段再次变成“假生效”
5. 配置修改时改错层，导致影响范围扩大

这些不是一次性修完就永远没事的点，要长期防漂。
