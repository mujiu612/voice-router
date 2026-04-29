# Feishu Platform Delivery Notes for voice-router

这份文件只管飞书语音投递，不管文案创作、不管 provider 生成细节。

目标：把 voice-router 在 Feishu 场景下的稳定链路、约束、失败分层、排查顺序写清楚，避免再次回到“看似发了，实际没闭环”的老问题。

---

## 1. Core Rule

Feishu 场景下，voice-router 的第一原则不是“省事发出去”，而是：

**优先保证最终收到的是可播放、格式正确、链路闭环的语音。**

因此：

- 不拿 mp3 直接充当最终稳定方案
- 不把“平台返回成功”当成最终用户体验成功
- 不把“准备发送”说成“已发”
- 失败时必须报真实卡点层级

---

## 2. Stable Delivery Path

当前推荐稳定链路：

1. 先按 voice-router 解析 route
2. 生成原始音频文件
3. 转码为 `opus`
4. 做非空校验
5. 做 duration probe
6. 生成 Feishu delivery plan
7. 由运行时执行实际发送
8. 以“用户侧可播放”作为最终闭环标准

### Current Feishu Profile

推荐 profile 至少保持：

```json
{
  "enabled": true,
  "preferred_format": "opus",
  "send_mode": "audio_file",
  "allow_direct_mp3_send": false
}
```

### Why

- `opus` 更符合当前稳定链路
- `audio_file` 比“假装原生语音”更可控
- `allow_direct_mp3_send=false` 可以防止临时图省事退化为错误习惯

---

## 3. Delivery Boundary

`voice-router` 里的 `deliver_feishu.py` 当前职责是：

- 检查文件是否存在
- 检查文件是否非空
- 用 `ffprobe` 探测时长
- 输出结构化 delivery plan

它**不负责**：

- 直接调用 curl 发飞书 HTTP
- 绕过 OpenClaw 运行时自己发消息
- 把“计划发”当成“已经发”

### Boundary Rule

Feishu 实际发送必须交给运行时消息层完成。不要在 skill 脚本里私自扩展成 ad-hoc HTTP 发消息。

---

## 4. Success Standard

Feishu 场景的成功至少分 3 层：

### Level 1: Artifact Success

生成出的最终音频文件满足：

- 文件存在
- 文件非空
- 可读出 duration
- 格式正确（当前优先 `opus`）

### Level 2: Delivery Invocation Success

运行时消息层接受 delivery plan，并实际执行发送。

### Level 3: User-side Playback Success

用户在飞书侧能真正点开并播放。

### Rule

只有到 Level 2，才能说“已发送”。
只有到 Level 3，才能说“链路体验闭环了”。

如果 Level 2 成功但用户侧不可播放，仍然属于链路未完成闭环。

---

## 5. Failure Layers

失败时必须明确卡在哪一层。

### 1) 路由层

常见问题：

- 没命中 route
- slot 不存在
- model 不存在
- slot / model / delivery profile 被禁用

典型反馈：

- “卡在路由层，`slot_xxx` 不存在。”
- “卡在路由层，Feishu profile 当前被禁用。”

### 2) 生成层

常见问题：

- provider 调用失败
- API key 缺失
- 输出文件为空
- provider 返回的是 JSON 错误体而不是音频

典型反馈：

- “卡在生成层，MiniMax 调用失败。”
- “卡在生成层，NoizAI 生成出了空文件。”

### 3) 校验层

常见问题：

- 文件为空
- ffprobe 读不出 duration
- 转码失败
- 输出不是合法音频

典型反馈：

- “卡在校验层，opus 转码后文件为空。”
- “卡在校验层，ffprobe 无法探测时长。”

### 4) 发送层

常见问题：

- 运行时消息层未实际执行发送
- 发送返回异常
- 发送表面成功但用户侧不可播放

典型反馈：

- “卡在发送层，运行时没有完成最终投递。”
- “卡在发送层，用户侧实际不可播放，链路未闭环。”

---

## 6. Anti-patterns

这些都是明确不推荐的：

### Anti-pattern 1: 直接拿 mp3 发飞书

除非明确进入临时调试模式，否则不要把 mp3 当最终稳定方案。

### Anti-pattern 2: 只看接口返回 ok 就宣布成功

Feishu 场景必须更看重最终是否可播放。

### Anti-pattern 3: 绕过运行时，用 curl 或私写 HTTP 脚本直接发

这会把发送逻辑分叉，后面极难维护。

### Anti-pattern 4: 把“我准备好了一个音频文件”说成“我已经发给你了”

这会制造假成功。

---

## 7. Recommended Troubleshooting Order

Feishu 发送失败时，按这个顺序排查：

1. route 是否命中了正确 slot/model/profile
2. 原始音频文件是否存在且非空
3. opus 转码是否成功
4. duration probe 是否成功
5. delivery plan 是否生成成功
6. 运行时是否真正执行了发送
7. 用户侧是否能正常播放

不要一上来就怀疑 provider，也不要只盯着发送层。

---

## 8. Reporting Template

### Success

- 平台：Feishu
- 路由命中：`<slot>`
- 实际模型：`<provider/model/voice>`
- 输出格式：`opus`
- 发送方式：`audio_file`
- 当前状态：已发送 / 已闭环

### Failure

- 平台：Feishu
- 失败层级：`<路由 / 生成 / 校验 / 发送>`
- 当前尝试：`<provider/model/voice>`
- 真实原因：`<错误摘要>`
- 下一步建议：`<换模型 / 改格式 / 只导出文件 / 检查运行时发送>`

---

## 9. Future Hardening

后续如果要把 Feishu 链路继续补硬，优先顺序建议是：

1. 把平台级 `allow_direct_mp3_send` 真正做成强约束，而不是只写在配置里
2. 增加 Feishu 侧发送后的回执与结果校验
3. 增加更明确的异常分类（鉴权失败、资源上传失败、消息发送失败、用户侧不可播放）
4. 为 Feishu 单独补一份真实案例故障库

---

## 10. Non-goals

这份文件不负责：

- provider API 细节
- NoizAI / MiniMax 参数选择
- 文案内容质量
- 其他平台（Telegram / QQ）的发送细节

它只负责回答：

- 在 Feishu 场景下，什么叫稳定发送
- 哪些行为算假成功
- 出错时该怎么定位
