# voice-router

> 一个把语音选择、TTS 生成、音频校验、转码和平台投递拆开的结构化语音路由层。

`voice-router` 不是单一的 TTS 脚本，也不是单一的平台发送器。

它的核心目标，是把一条完整语音链路里的几个关键决策拆开管理：

- 这次该用哪个声音
- 该由哪个 provider 来生成
- 生成结果是否真的可用
- 是否需要转码
- 最终该按哪个平台规则发出去

它用配置化的方式，替代把这些规则硬编码进一个脚本里的做法。

---

## 为什么要做这个

大多数语音链路一开始都很简单：

> 生成一个音频，然后发出去。

但只要需求一复杂，问题就会立刻冒出来：

- 不同任务想用不同声音
- 不同助手想有不同默认声线
- provider 会失效，需要 fallback
- 平台之间格式要求不一样
- 返回 `ok` 不代表用户真的能播放

`voice-router` 就是为了解决这种失控增长。

它把：

- 路由逻辑
- provider 逻辑
- 转码逻辑
- 投递逻辑

明确拆开，让系统在增长之后仍然可理解、可维护、可扩展。

---

## v1 这一版聚焦什么

v1 故意不贪大。

它不是一上来就做成“全平台语音系统”，而是先把一条**稳定可用的生产链路**做实：

**文本 -> TTS provider -> 音频校验 -> opus 转码 -> Feishu 投递**

当前 v1 的重点：

- 稳定的 **Feishu** 语音链路
- 支持 **NoizAI** 和 **MiniMax**
- 支持显式 fallback
- 以配置驱动路由
- 有明确的失败边界

---

## v1 已经做到什么程度

`voice-router v1` 现在已经是一套可工作的参考工作流。

### 已实现

- 路由解析
- NoizAI 生成
- MiniMax 生成
- `mp3 -> opus` 转码
- Feishu 投递链路
- model fallback 执行
- provider 说明文档与失败案例沉淀

### 开发阶段已验证

- 在受支持的 provider 路径上可以成功生成音频
- opus 输出可被 probe 与校验
- Feishu 投递行为已在目标工作流中验证过
- 在真实部署里，仍建议以“接收端可正常播放”作为最终确认

所以这版更适合作为一个可运行的 v1 参考实现，而不是停留在设计稿层面。

---

## 核心设计

`voice-router` 采用四层结构。

### 1. Models
底层语音能力层。

负责定义：

- provider
- model 名称
- voice id / 参考音频模式
- timeout / retry
- 标签 / 状态

例如：

- `model_noiz_default`
- `model_minimax_default`

---

### 2. Slots
对外的人话层，也就是“声音角色位”。

slot 不是底层 provider 细节，而是业务层能理解的声音角色。

例如：

- 主助手声音
- 早安日报声音
- 提醒通知声音
- 艺术助手声音

每个 slot 可以定义：

- primary model
- fallback models
- persona
- display name

---

### 3. Bindings
默认绑定层。

负责把：

- task -> slot
- agent -> slot

映射起来。

例如：

- `morning_brief -> slot_morning`
- `main -> slot_main`

---

### 4. Delivery
平台投递层。

负责定义：

- 目标平台
- 输出格式
- send mode
- 输出目录
- 平台能力差异

在 v1 里，主目标平台是：

- `feishu`
- `preferred_format = opus`
- `send_mode = audio_file`

---

## 当前路由顺序

默认顺序如下：

1. `explicit_slot`
2. `explicit_model`
3. `task_binding`
4. `agent_binding`
5. 默认兜底

如果命中的是 slot，则执行逻辑为：

- 先走 `primary_model`
- 失败后按 `fallback_models` 继续尝试

这意味着 fallback 不是补丁，而是路由系统的一部分。

---

## 当前 provider 策略

### NoizAI
v1 里，NoizAI 走的是“稳优先”策略。

当前做法：

- 默认走参考音频模式
- 不假设旧的人类可读 voice 名一定等于真实 `voice_id`

原因：

- 像 `zf_xiaoni` 这样的旧值，在当前接法下可能直接报 `Voice not found`
- 有些失败返回的是 JSON 报错，不是真音频

所以在 v1 中，NoizAI 以稳定生成为第一目标，而不是先把 voice-id 管理做复杂。

### MiniMax
MiniMax 当前走的是最小 HTTP TTS 路径。

默认配置使用：

- `speech-2.8-hd`

但 provider 侧模型可用性可能会受到账号等级、权限、区域或后续 API 变化影响，因此这里更适合作为推荐默认值，而不是对所有环境都成立的保证。

这样既能保持 provider 链路简单稳定，也为不同部署环境留出了覆盖空间。

---

## 当前 Feishu 策略

Feishu 是 v1 的核心投递目标。

当前策略：

- 不默认直发 mp3
- 统一转成 `opus`
- 用 `audio_file` 模式发送
- 不把 API 返回成功当成最终成功
- 把“用户侧能正常播放”当成最终闭环

这套选择更偏向目标投递工作流里的播放稳定性，而不是仅凭 API 返回成功就乐观判断已经完成。

---

## 仓库结构

```text
voice-router/
├── README.md
├── README.zh-CN.md
├── SKILL.md
├── voice_router.json
├── references/
│   ├── config-schema.md
│   ├── failure-cases.md
│   ├── platform-feishu.md
│   ├── provider-minimax.md
│   └── provider-noizai.md
└── scripts/
    ├── route_voice.py
    ├── generate_noizai.py
    ├── generate_minimax.py
    ├── transcode_to_opus.sh
    ├── deliver_feishu.py
    └── run_voice_pipeline.py
```

---

## 关键文件说明

| 文件 | 作用 |
|---|---|
| `voice_router.json` | 单一事实来源，定义 models / slots / bindings / routing / delivery / validation |
| `SKILL.md` | 技能行为、工作流规则、设计原则 |
| `README.md` | GitHub 风格英文项目介绍 |
| `README.zh-CN.md` | GitHub 风格中文项目介绍 |
| `scripts/route_voice.py` | 只负责路由解析 |
| `scripts/generate_noizai.py` | 只负责 NoizAI 生成 |
| `scripts/generate_minimax.py` | 只负责 MiniMax 生成 |
| `scripts/transcode_to_opus.sh` | 负责转码与 ffprobe 校验 |
| `scripts/deliver_feishu.py` | 负责 Feishu 投递计划准备 |
| `scripts/run_voice_pipeline.py` | v1 的最小主流程串联器 |

---

## 能力边界

### v1 已覆盖

- 语音路由
- provider 选择
- model fallback
- 音频校验
- opus 转码
- 稳定的 Feishu 投递路径

### v1 暂不处理

- 多角色剧本拆分
- 按情绪自动选 voice
- DAW 级音频后期
- 完整多平台投递扩展
- UI 化配置管理

这是刻意为之。

v1 的目标不是功能堆满，而是：

- 稳
- 清楚
- 可解释
- 可扩展

---

## 设计原则

整个系统遵守几条硬规则：

- **配置优先**：默认规则写进 `voice_router.json`，不要散落在脚本里
- **分层明确**：路由和投递不能混写
- **fallback 要真执行**：失败后要切下一模型，不是静默结束
- **校验不能省**：一个 `ok` 不等于真的成功
- **用户可播放才算闭环**：尤其是 Feishu 场景

---

## 当前结论

`voice-router v1` 已经进入“可工作的系统”阶段。

它已经不再只是：

- 一个概念
- 一份 schema
- 一个半成品原型

而是一个：

- 有结构
- 有验证路径
- 可路由
- 可转码
- 可 fallback
- 可投递到 Feishu

的稳定 v1。

---

## Roadmap

后续如果继续迭代，建议按版本推进：

### v1.1
- 更干净的入口
- 更顺手的调用体验
- 更好的操作侧摘要输出

### v1.2
- 更多 provider
- 更细的 fallback 策略
- 更强的诊断与报错能力

### v1.3
- 多平台投递扩展
- 除 Feishu 之外的平台 profile 落地

---

## Status

**当前状态：v1 已锁定。**

主结构不应再被随手打散。
后续演进应建立在 v1 之上，而不是重新从零拼一次。
