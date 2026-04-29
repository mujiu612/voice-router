---
name: voice-router
description: 为语音生成与语音发送任务提供统一路由与配置管理。用于根据任务类型、助手身份、显式指定的声音插槽或语音模型，选择合适的 TTS provider、voice、输出格式与投递平台。适用于多平台语音发送、助手默认声音管理、任务默认声音绑定、语音模型切换、语音链路兜底与配置演进场景。用户提到“语音路由”“voice router”“默认声音”“给某个任务换声音”“不同助手用不同 voice”“TTS 路由”“语音发送配置”“Feishu/Telegram/QQ 语音适配”时使用。
---

# Voice Router

统一管理“用哪个语音模型、哪个声音、生成成什么格式、发到哪个平台”。

当前第一阶段目标：

- 先保证 Feishu 语音链路稳定
- 同时把结构设计成跨平台可扩展
- 当前优先支持 NoizAI 与 MiniMax
- 配置文件以 `voice_router.json` 为单一事实来源

## TL;DR

遇到语音请求时，默认按这条最短路径处理：

1. 先判断这是“临时覆盖”还是“持久修改”
2. 再判断用户指定的是 `slot`、`model`、任务类型还是 agent 身份
3. 按优先级解析最终路由：`explicit_slot > explicit_model > task_binding > agent_binding > 默认兜底`
4. 生成音频，不跳过校验
5. 按目标平台 profile 投递，优先遵守平台稳定链路，不图省事乱降级
6. 失败时明确说卡在：路由 / 生成 / 校验 / 发送

默认原则：

- 用户说“这次先这样”“先临时切一下” → 只做临时覆盖，不改配置
- 用户说“以后都这样”“默认改成”“今后这个任务都用” → 才进入持久化修改
- Feishu 场景默认优先稳定链路，不直接发 mp3 充数
- 平台返回成功，不等于任务真的完成，优先看最终是否可播放

## High-frequency Request Patterns

### 1. 临时换声音，不改默认

典型说法：

- 这次先换个声音
- 先临时切到 MiniMax
- 先别改配置，这次这样就行

处理原则：

- 识别为一次性覆盖
- 优先用 `explicit_slot` 或 `explicit_model`
- 不写回 `voice_router.json`
- 汇报时明确说明“本次仅临时生效”

### 2. 永久修改某类任务默认声音

典型说法：

- 以后 daily_news 默认用正式一点的女声
- 早安日报今后都改成这个声音
- 提醒通知以后统一正式一点

处理原则：

- 识别为持久化修改
- 优先改 `bindings.task_bindings` 或对应 `slot`
- 不要一上来就改底层 provider，除非用户明确要求
- 改完后说明影响范围是“某类任务默认值”

### 3. 永久修改某个 agent 默认声音

典型说法：

- main 以后默认就用这个声音
- 艺术助手固定一个更轻松的 voice

处理原则：

- 优先改 `bindings.agent_bindings`
- 若该 agent 的具体任务还有 task binding，任务绑定仍优先
- 汇报时说明“agent 默认声音已更新，但仍会被更具体的 task binding 覆盖”

### 4. Feishu 稳定链路发送

典型说法：

- 发给我听
- Feishu 里发语音
- 不要 mp3，走稳定链路

处理原则：

- 优先按 Feishu profile 走稳定格式
- 如果配置禁止直接 mp3，就不要临时降级成 mp3
- 发出前必须完成非空、时长、格式检查
- 失败时明确卡点层级，不把“准备发”说成“已发”

## Core Principle

始终把语音任务拆成四层：

1. 选择声音
2. 生成音频
3. 校验结果
4. 投递平台

不要把“声音选择逻辑”和“平台发送逻辑”混写在一起。

## Primary Config

默认配置文件：`voice_router.json`

## Minimal Config Skeleton

下面这个示意片段不是完整 schema，但足够作为第一眼定位图。用户问“现在默认声音是什么”“该改哪一层”时，优先拿这个结构去定位：

```json
{
  "models": {
    "model_minimax_formal": {
      "provider": "minimax",
      "voice": "female_formal",
      "enabled": true,
      "timeout": 60,
      "retry": 2
    },
    "model_noiz_default": {
      "provider": "noizai",
      "voice": "warm_default",
      "enabled": true,
      "timeout": 60,
      "retry": 2
    }
  },
  "slots": {
    "slot_morning": {
      "display_name": "早安日报声音",
      "persona": "正式、稳定、清晰",
      "primary_model": "model_minimax_formal",
      "fallback_models": ["model_noiz_default"],
      "enabled": true
    },
    "slot_main": {
      "display_name": "主助手声音",
      "persona": "自然、可信",
      "primary_model": "model_noiz_default",
      "fallback_models": ["model_minimax_formal"],
      "enabled": true
    }
  },
  "bindings": {
    "task_bindings": {
      "daily_news": "slot_morning",
      "morning_brief": "slot_morning"
    },
    "agent_bindings": {
      "main": "slot_main"
    }
  },
  "delivery": {
    "profiles": {
      "feishu": {
        "enabled": true,
        "preferred_format": "opus",
        "send_mode": "audio_file",
        "allow_direct_mp3_send": false
      }
    }
  }
}
```

读法：

- 问“daily_news 默认什么声音” → 先看 `bindings.task_bindings.daily_news`
- 问“main 默认声音是什么” → 看 `bindings.agent_bindings.main`
- 命中某个 slot 后 → 看 `slots.<slot>.primary_model`
- 确认底层 voice → 看 `models.<model>.provider` 和 `models.<model>.voice`
- 问 Feishu 发什么格式 → 看 `delivery.profiles.feishu`

## Credentials Rule

长期凭据统一走环境变量，不写入 `voice_router.json`、脚本源码、记忆文件或普通说明文档。

推荐变量名：

- `MINIMAX_API_KEY`
- `NOIZ_API_KEY`
- `XAI_API_KEY`

OpenClaw 场景下，长期推荐落点：

- `~/.openclaw/.env`

脚本读取顺序建议保持为：

1. 先读进程环境变量
2. 若缺失，再兜底读取 `~/.openclaw/.env`
3. 仅为兼容旧链路时，才额外读取 provider 的历史私有文件（例如 `~/.noiz_api_key`）

原因：

- cron / isolated agent / gateway service 更容易稳定继承
- 避免把 key 绑定在单个 skill 内
- 更利于迁移到新机器
- 降低误提交与泄露风险

macOS 补充：

如果 OpenClaw 以 LaunchAgent 方式运行，不要默认依赖 shell 会话里的临时环境变量。涉及长期运行任务时，优先使用 `~/.openclaw/.env`。

它负责定义：

- `models`：可用语音模型
- `slots`：人话层的声音插槽
- `bindings.task_bindings`：任务默认声音
- `bindings.agent_bindings`：助手默认声音
- `routing`：路由顺序与 fallback 规则
- `delivery`：平台发送配置
- `guidance`：面向用户的人话映射
- `evolution`：经验晋升与后续演进策略
- `validation`：生成与发送后的校验规则

如果用户要改“默认声音”“某类任务以后都用某个 voice”“某个 agent 固定一种声音”，优先改配置，不要写死在脚本里。

## Layered Architecture

voice-router 采用四层结构：

1. `models`
2. `slots`
3. `bindings`
4. `delivery`

这样拆的原因，是把“底层语音能力”“人能理解的声音角色位”“任务/助手默认规则”“平台发送规则”彻底分开，避免后续越改越乱。

## Model Layer

`models` 表示底层可用语音能力源。

这一层关心的是：

- provider 是谁
- 默认 voice 是谁
- timeout / retry 等调用参数
- 模型是否启用
- 模型标签
- 模型健康状态或适用方向

例如：

- `model_noiz_default`
- `model_minimax_default`
- `model_noiz_warm`
- `model_minimax_formal`

这一层不是给用户直接操作的第一入口。它更像“底层资源池”。

### Why Separate Models From Slots

如果 slot 直接绑定 provider + voice，短期能跑，但长期会出这些问题：

1. 同类配置重复
2. 更换 provider 成本高
3. 模型可用性无法集中管理
4. 健康检查、降级、停用都不顺手
5. 用户想调“声音角色”时，会被迫接触到底层模型细节

拆出 `model` 层后：

- model 负责底层能力
- slot 负责声音角色
- binding 负责默认命中规则

职责会清楚很多。

## Slot Layer

`slots` 是对外的人话层。

slot 不是底层模型本身，而是一个“声音角色位”。

例如：

- 主助手声音
- 早安日报声音
- 提醒通知声音
- 艺术助手声音
- 备用声音

每个 slot 至少包含：

- 是否启用
- display_name
- persona
- primary_model
- fallback_models

slot 的作用是把“这个声音在业务上扮演什么角色”表达出来，而不是暴露 provider 实现细节。

### Slot Design Rule

始终优先让 slot 对应“使用场景”或“角色身份”，不要优先对应“技术实现”。

推荐：

- `slot_main`
- `slot_morning`
- `slot_alert`
- `slot_art`
- `slot_backup`

不推荐：

- `slot_noiz_1`
- `slot_minimax_2`

因为后者会把技术实现泄漏到业务命名里，后面替换 provider 时容易混乱。

## Binding Layer

`bindings` 负责默认命中规则。

它分两类：

### 1. Task Bindings

把某类任务默认绑定到某个 slot。

例如：

- `morning_brief -> slot_morning`
- `daily_news -> slot_morning`
- `alert -> slot_alert`

这层解决的是：

“这类任务默认该用什么声音？”

### 2. Agent Bindings

把某个 agent 默认绑定到某个 slot。

例如：

- `main -> slot_main`
- `art-shrimp -> slot_art`
- `capital-shrimp -> slot_alert`

这层解决的是：

“默认听起来像谁在说话？”

### Binding Priority

当 task binding 和 agent binding 同时存在时：

- task binding 优先于 agent binding

因为任务声音通常更强约束。例如“早安日报”即使由 main 发出，也应优先走 `slot_morning`。

## Delivery Layer

`delivery` 负责平台发送规则。

这一层只处理：

- 发到哪里
- 用什么格式
- 用什么 send_mode
- 输出目录在哪里
- 各平台支持什么能力

不要把平台发送逻辑塞进 model、slot、binding。

当前第一阶段重点仍然是：

- `feishu.enabled = true`
- `preferred_format = opus`
- `send_mode = audio_file`

Telegram、QQ 等平台可以先保留 profile，但默认不启用。

## Routing Order

按以下顺序决定最终声音：

1. `explicit_slot`
2. `explicit_model`
3. `task_binding`
4. `agent_binding`
5. 默认兜底

如果命中 slot：

- 先取 `primary_model`
- 失败时再按 `fallback_models` 顺序尝试

如果命中 model：

- 直接走该 model
- 除非配置明确允许继续 fallback

不要跳过显式指定。显式指定永远优先于默认绑定。

## Recommended Resolution Flow

一次语音任务，推荐按这个顺序解析：

1. 是否显式指定 slot
2. 是否显式指定 model
3. 是否命中 task binding
4. 是否命中 agent binding
5. 是否回退到默认 slot
6. 根据 slot 解析 primary model
7. 若失败，再按 fallback models 继续尝试
8. 生成音频
9. 校验音频
10. 按 delivery profile 发送

这条链路里，前半段是决策，后半段是执行。

不要把“选谁来生成”和“怎么发出去”混成一步。

## Human-facing Language

对外优先说人话，不优先说内部键名。

例如：

- `slot_main` → 主助手声音
- `slot_morning` → 早安日报声音
- `task_binding` → 任务默认声音
- `agent_binding` → 助手默认声音
- `delivery` → 发送方式

和用户沟通时，优先说：

- “主助手声音”
- “提醒通知声音”
- “这类任务默认用这个声音”
- “先临时切到 MiniMax”

不要一上来就堆内部字段名，除非用户明确在看配置文件。

## User Interaction Rule

和用户沟通时，默认说 slot，不默认说 model。

只有在这些场景下，再展开到底层 model：

- 用户明确问用了哪个模型
- 用户要求切换 NoizAI / MiniMax
- 用户要做 provider 层排障
- 用户在改配置文件

这样做的好处是：

- 用户更容易理解
- 更利于长期稳定运营
- 后端切换时不影响对外表述

## Recommended Workflow

处理一次语音任务时，按这个顺序执行：

### 0. Quick Decision Table

| 用户意图 | 优先动作 | 应改层级 | 默认是否持久化 |
|---|---|---|---|
| 这次临时换声音 | 用 `explicit_slot` 或 `explicit_model` 临时覆盖 | 不改配置 | 否 |
| 以后某类任务默认换声音 | 调整 `bindings.task_bindings`，必要时补改对应 `slot` | task binding / slot | 是 |
| 以后某个 agent 默认换声音 | 调整 `bindings.agent_bindings` | agent binding | 是 |
| 问当前默认声音是什么 | 读取 binding → slot → model 链路并翻译成人话 | 不改配置 | 否 |
| Feishu 发语音 | 走 Feishu profile，优先稳定链路 | delivery profile | 否 |

### 1. Collect Intent

先判断用户要的是哪一种：

- 临时换声音
- 永久修改任务默认声音
- 永久修改助手默认声音
- 指定平台发送
- 只生成音频，不发送
- 只改配置，不执行生成

如果是一次性要求，优先做临时覆盖，不要默认写回配置。

如果是“以后都这样”“默认改成”“今后这个任务都用这个声音”，再进入持久化修改。

### 2. Resolve Route

从上下文中提取这些信号：

- 是否显式指定 `slot`
- 是否显式指定 `model`
- 当前任务类型
- 当前 agent 身份
- 当前投递平台
- 是否要求跨平台覆盖

然后按 `routing.default_selection_order` 解析最终路由。

输出内部结果时至少要能确定：

- 最终 slot
- 最终 model
- provider
- voice
- 输出格式
- 目标平台

### 2.5 How To Answer “默认声音是什么”

如果用户问：

- main 现在默认声音是什么
- daily_news 默认走哪个 voice
- 为什么这次不是主助手那个声音

按这条链路查，并按人话汇报：

1. 先看是否存在显式指定 `explicit_slot` 或 `explicit_model`
2. 没有显式指定时，看是否命中 `bindings.task_bindings.<task>`
3. 若未命中 task binding，再看 `bindings.agent_bindings.<agent>`
4. 确认最终命中的 `slot`
5. 再看该 `slot` 的 `primary_model`
6. 最后从对应 `model` 里读出 provider、voice 和关键生成参数

对用户汇报时不要只报内部键名，优先翻译成：

- 命中了哪个“声音角色位”
- 实际走的是哪个模型 / provider / voice
- 为什么是它优先（例如 task binding 覆盖了 agent binding）

如果配置缺项，就明确说缺在哪一层，不要假装解析成功。

### 3. Generate Audio

根据 model 对应的 provider 调用具体 TTS 生成逻辑。

当前优先 provider：

- NoizAI
- MiniMax

要求：

- 生成到平台 profile 指定的 `output_dir`
- 文件名可带前缀，例如 `feishu-voice`
- 超时、重试遵守 model 配置
- provider 失败时遵守 fallback 规则

如果后续增加 provider，保持接口层统一，不要把 provider 特例散落在主流程里。

### 4. Validate Before Send

发送前至少检查：

- 文件存在
- 文件非空
- 能探测到时长
- 编码格式符合目标平台要求

如果配置要求：

- `require_nonempty_audio = true`
- `require_duration_probe = true`

则任一失败都不要继续发送。

如果 `stop_on_empty_audio = true` 或 `stop_on_probe_failure = true`，必须立即停止并报真实原因。

### 5. Deliver

按 `delivery.profiles.<platform>` 处理。

当前阶段重点：

### Feishu

优先按 Feishu profile 处理：

- `preferred_format = opus`
- `send_mode = audio_file`
- 当前不假设 Feishu 一定支持“原生语音体验”
- 必须优先以实测链路稳定性为准

如果配置为：

- `allow_direct_mp3_send = false`

则不要图省事直接发 mp3。

如果平台发送工具返回成功，但用户实际未收到或体验不对，按“发送链路未完成闭环”处理，不要自我宣布成功。

## Persistent Changes

涉及持久化配置修改时，先说明再改。

典型场景：

- “以后早安日报都用轻快一点的声音”
- “把主助手声音换成 MiniMax”
- “提醒通知默认正式一点”

处理原则：

1. 先用人话复述将改什么
2. 明确影响范围：当前任务 / 当前 agent / 某类任务 / 全局
3. 再修改配置
4. 修改后给出结果摘要

如果只是“这次先这样”，不要默认写入 `voice_router.json`。

## Persistent Configuration Rule

持久化配置修改分三种：

1. 改 model
2. 改 slot
3. 改 binding

### 修改 model

用于：

- 改 provider
- 改 voice
- 改 timeout / retry
- 启用或停用某个模型

### 修改 slot

用于：

- 改某个声音角色位的 primary model
- 改 fallback 顺序
- 改 persona / display_name

### 修改 binding

用于：

- 改某类任务默认用哪个 slot
- 改某个 agent 默认用哪个 slot

如果用户说的是：

- “以后早安日报用轻快一点的声音”

优先改 `slot_morning` 或 `task_bindings`，不要直接跳到底层 model，除非用户明确要求。

## Which Layer To Edit

用户要改默认行为时，优先按这张表判断，不要拍脑袋改：

| 用户说法 | 优先修改位置 | 不推荐的第一反应 |
|---|---|---|
| 以后 daily_news 用更正式女声 | `bindings.task_bindings.daily_news`，必要时再改 `slot_morning` | 直接改所有 model 的默认 voice |
| main 以后就用这个声音 | `bindings.agent_bindings.main` | 直接改 task binding |
| 把“早安日报声音”换成 MiniMax | 对应 `slot` 的 `primary_model` | 直接改 agent binding |
| 这个 provider 超时太多 | 对应 `model` 的 timeout / retry / enabled | 去改 slot 名称或 binding |
| Feishu 不要 mp3，统一稳一点 | `delivery.profiles.feishu` | 在生成脚本里临时写死格式 |

判断顺序：

- 改“谁默认用哪个声音” → 先想 binding
- 改“这个声音角色位具体映射到什么模型” → 想 slot
- 改“底层 provider / voice / timeout / retry” → 想 model
- 改“发到哪个平台用什么格式” → 想 delivery

## Fallback Rule

fallback 分两级：

### Level 1: Model fallback inside a slot

例如：

- `slot_morning.primary_model = model_minimax_default`
- `slot_morning.fallback_models = [model_noiz_default]`

这表示同一个“声音角色位”内的技术兜底。

### Level 2: Slot fallback at global level

例如：

- 主 slot 全部失败后，回到 `slot_backup`

这一层是否启用，取决于后续实现复杂度。第一版允许只做 model fallback，不强求 slot fallback 很复杂。

## Evolution Strategy

允许基于重复偏好做“经验晋升”，但要克制。

推荐行为：

- 同类偏好出现 2 次以上，再考虑建议晋升为默认配置
- 每个会话最多提醒一次
- 晋升前尽量征求用户确认
- 晋升后可归档历史临时偏好

例如：

- 用户多次说“早安日报用轻快一点的声音”
- 可以提示：要不要把它设成早安日报默认声音？

不要因为一次临时偏好就自动改全局。

## Validation Rule

voice-router 不以“接口返回 ok”作为唯一成功标准。

至少要满足：

- 音频文件存在
- 文件非空
- 可探测 duration
- 格式符合目标平台要求
- 平台发送成功

如果是 Feishu 场景，优先以“用户实际可播放”作为最终体验闭环。

不要因为返回成功就草率判定整个任务成功。

## Failure Handling

失败时必须说真实卡点，不要糊弄成“已完成”。

常见失败类型：

- provider 调用失败
- 生成了空音频
- 时长探测失败
- 平台格式不兼容
- 平台返回成功但用户侧不可用
- fallback 也全部失败

反馈格式建议包含三件事：

1. 卡在哪一层：路由 / 生成 / 校验 / 发送
2. 当前尝试了哪个 model/provider
3. 下一步建议：换 voice、换 provider、换平台格式、仅导出文件等

## Config Editing Rules

修改 `voice_router.json` 时遵守这些原则：

- 最小改动
- 不顺手重排整个文件
- 非必要不改已有键名
- 保留扩展位
- 新增字段时保持命名一致

优先新增，不轻易破坏兼容性。

例如：

- 新增一个声音，优先加到 `models`
- 新增一个任务默认声音，优先改 `bindings.task_bindings`
- 新增一个平台，优先加到 `delivery.profiles`

不要把“某任务特殊逻辑”硬编码进脚本，除非配置层表达不了。

## Suggested Output Style

对用户汇报时，优先用这种结构：

- 这次命中了哪个声音插槽
- 实际用的是哪个模型 / 声线
- 是否发生了 fallback
- 最终按哪个平台格式发送
- 如果是持久化修改，再补一句“已更新默认配置”

例子：

- “这次走的是‘早安日报声音’，主模型是 MiniMax 默认播报女声，目标平台按 Feishu 的 opus 配置处理。”
- “我把‘主助手声音’默认绑定保留在 NoizAI，MiniMax 继续作为兜底。”
- “这次只是临时切到 MiniMax，没有改默认配置。”

### Output Templates

#### 模板 1：临时覆盖

- 这次命中的是：`<slot-display-name>`
- 实际使用的是：`<provider>/<model>/<voice>`
- 生效范围：仅本次
- 配置状态：未修改默认配置

#### 模板 2：持久化修改成功

- 已更新：`<task / agent / slot / model / delivery>`
- 影响范围：`<具体范围>`
- 当前默认将命中：`<slot-display-name>`
- 如无显式指定，后续会继续按这个默认执行

#### 模板 3：优先级解释

- 当前任务先命中：`<task binding 或 explicit 指定>`
- 因此覆盖了：`<agent binding 或默认兜底>`
- 最终声音是：`<slot-display-name> -> <model> -> <voice>`

#### 模板 4：失败反馈

- 失败层级：`<路由 / 生成 / 校验 / 发送>`
- 当前尝试：`<provider / model / voice / 平台>`
- 真实原因：`<错误摘要>`
- 下一步建议：`<换 slot / 换 model / 改格式 / 仅导出文件>`

## Scope Boundary

这个 skill 负责：

- 语音路由
- provider 选择
- 声音插槽映射
- 平台投递策略
- 配置修改规则

这个 skill 不负责：

- 长篇文案本身的创作
- 复杂配音脚本拆角色
- DAW 级别音频后期
- 视频剪辑时间线混音
- 非语音媒体投递策略

如果用户要的是“多角色剧本拆分 + 每个角色单独配音 + 时间轴拼装”，应把 voice-router 作为其中一环，不要让它吞掉整个制作流程。

## First-Phase Scope

第一阶段只要求做到：

- model 层可配置
- slot 层可配置
- task / agent binding 可命中
- NoizAI / MiniMax 可切换
- Feishu 投递稳定
- 失败时能真实报错
- 默认不乱降级成别的发送形式

第一阶段暂不强求：

- 情绪自动识别选 voice
- 文本风格自动选 slot
- 时间段动态切换 slot
- 多角色剧本自动拆轨
- slot 内复杂权重路由
- 平台级高级互动体验

先把“结构对、链路稳、能解释、能排错”做实。

## Implementation Notes

如果后续补脚本，建议最少拆成这些模块：

补充约束：

- provider 脚本不要写死 Linux 路径，例如 `/home/...`
- 路径应从当前 skill 目录或 workspace 根目录动态解析
- 这样才能兼容 macOS、Linux 与迁移后的目录结构

- `scripts/route_voice.py`：只做路由解析
- `scripts/generate_noizai.py`
- `scripts/generate_minimax.py`
- `scripts/transcode_to_opus.sh`
- `scripts/deliver_feishu.py`

保持每层单一职责，便于替换 provider 或平台。

## Config Reading Examples

### 例 1：用户问“main 默认声音是什么？”

推荐读取顺序：

1. `bindings.agent_bindings.main`
2. `slots.slot_main`
3. `models.<slot_main.primary_model>`

推荐回答方式：

- “当前 main 默认命中的是‘主助手声音’这个 slot。”
- “这个 slot 的主模型是 `model_noiz_default`。”
- “底层 provider 是 NoizAI，voice 是 `warm_default`。”

### 例 2：用户问“为什么 morning_brief 不是 main 那个声音？”

推荐读取顺序：

1. `bindings.task_bindings.morning_brief`
2. `bindings.agent_bindings.main`
3. 比较优先级

推荐回答方式：

- “因为 `morning_brief` 命中了 task binding，它优先级高于 main 的 agent binding。”
- “所以最终走的是 `slot_morning`，而不是 `slot_main`。”

### 例 3：用户说“以后 daily_news 默认换正式女声”

推荐修改顺序：

1. 先确认 `bindings.task_bindings.daily_news` 当前指向哪个 slot
2. 若只是换该任务默认 slot，就改 task binding
3. 若仍使用原 slot，只是想把这个 slot 里的主模型换掉，再改 `slots.<slot>.primary_model`
4. 只有用户明确要求到底层 provider/voice 时，才改 `models`

### 例 4：用户说“Feishu 不要 mp3，走稳定链路”

优先检查：

1. `delivery.profiles.feishu.preferred_format`
2. `delivery.profiles.feishu.send_mode`
3. `delivery.profiles.feishu.allow_direct_mp3_send`

如果 `allow_direct_mp3_send = false`，就不要临时偷懒发 mp3。

## Field Naming Guardrails

为了减少配置漂移，默认遵守这些命名习惯：

- model 键名优先表达“provider + 风格 / 用途”，例如 `model_minimax_formal`
- slot 键名优先表达“角色 / 场景”，例如 `slot_main`、`slot_morning`
- task binding 键名尽量与真实任务名一致，例如 `daily_news`
- agent binding 键名尽量与真实 agent id 一致，例如 `main`
- delivery profile 键名直接用平台名，例如 `feishu`

不要把：

- slot 命名成 `slot_provider_1`
- model 命名成 `model_new_final_v2`
- 同一概念在不同层使用不同叫法

一旦命名漂移，后续排障和自动路由都会变差。

## References

当前已补充：

- `references/config-schema.md`：`voice_router.json` 的结构契约、字段职责、命名规则、读取顺序与校验清单

如果这个 skill 继续扩展，建议后续再补这些 reference 文件：

- `references/provider-noizai.md`：NoizAI 接入约束
- `references/provider-minimax.md`：MiniMax 接入约束
- `references/platform-feishu.md`：Feishu 语音发送经验
- `references/failure-cases.md`：常见失败与排查方式

SKILL.md 只保留核心流程，不把所有字段说明全塞进正文；字段细节优先写进 reference 文件。
