# voice-router Final Summary

这是当前 `voice-router` 的一页式收口文档，用来快速说明：

- 这套东西现在有什么
- 它已经能做什么
- 它还不做什么
- 日常维护时先看哪里
- 常用检查命令有哪些

---

## 1. Current Position

`voice-router` 当前已经不是单一 `SKILL.md`，而是一套小型内部规范与执行体系。

当前状态：
- 达尔文复评稳定在 **99/100**
- 已接近封顶
- 重点从“继续加分”转向“维护、防漂移、真实环境验证”

---

## 2. What It Contains

### Core

- `SKILL.md`
- `voice_router.json`

### Scripts

- `scripts/route_voice.py`
- `scripts/run_voice_pipeline.py`
- `scripts/generate_noizai.py`
- `scripts/generate_minimax.py`
- `scripts/generate_xai.py`
- `scripts/transcode_to_opus.sh`
- `scripts/deliver_feishu.py`
- `scripts/validate_config.py`
- `scripts/smoke_tests.py`
- `scripts/provider_integration_smoke.py`

### References

- `references/config-schema.md`
- `references/platform-feishu.md`
- `references/script-contract.md`
- `references/failure-cases.md`
- `references/provider-noizai.md`
- `references/provider-minimax.md`

---

## 3. What It Is Good At

当前这套最强的地方：

### 1) 语音路由清晰

能稳定区分：
- `explicit_slot`
- `explicit_model`
- `task_binding`
- `agent_binding`
- `task_default`

### 2) 配置层级清楚

能稳定判断该改哪一层：
- `bindings`
- `slots`
- `models`
- `delivery`

### 3) Feishu 稳定链路明确

当前推荐：
- `preferred_format = opus`
- `send_mode = audio_file`
- `allow_direct_mp3_send = false`

### 4) 失败分层成熟

当前默认按这四层报障：
- 路由
- 生成
- 校验
- 发送

### 5) 有最小回归保护

- `validate_config.py`
- `smoke_tests.py`
- `provider_integration_smoke.py`

---

## 4. What It Does NOT Fully Own

当前它还不是完全自闭环系统。

### 不完全由 skill 自身控制的部分

- 运行时最终消息发送
- 用户侧真实播放体验
- provider 外部套餐 / 权限限制

### 这意味着

- `delivery plan` 不等于最终已发送
- provider 失败不一定等于 skill 设计失败
- 最终闭环仍需结合运行时和真实平台环境判断

---

## 5. Current Reality Check

### 已真实验证成功

- NoizAI provider integration smoke
- NoizAI 生成成功
- 生成结果可转为 opus

### 已真实验证但不计为 skill 缺陷

- MiniMax 当前某模型失败，原因是套餐 / plan 不支持
- 这属于 `external_constraint`
- 不算当前 skill 设计缺陷

---

## 6. Daily Maintenance Entry Points

日常维护时，优先看这几个文件：

### 改流程
- `SKILL.md`

### 改配置
- `voice_router.json`
- `references/config-schema.md`

### 查平台链路
- `references/platform-feishu.md`

### 查脚本契约
- `references/script-contract.md`

### 查历史坑
- `references/failure-cases.md`

### 查 provider 限制
- `references/provider-noizai.md`
- `references/provider-minimax.md`

---

## 7. Common Commands

### 1) 校验配置

```bash
python3 scripts/validate_config.py \
  --config voice_router.json
```

### 2) 跑最小 smoke tests

```bash
python3 scripts/smoke_tests.py
```

### 3) 跑 provider integration smoke

```bash
python3 scripts/provider_integration_smoke.py \
  --config voice_router.json \
  --providers noizai minimax \
  --models model_noiz_default model_minimax_formal
```

### 4) 单独看 route 解析

```bash
python3 scripts/route_voice.py \
  --config voice_router.json \
  --task daily_news --agent main --channel feishu
```

---

## 8. Current Risk Priorities

仍需长期盯住的风险：

1. Feishu 假成功
2. route 优先级实现再次漂移
3. disabled model / 假默认重新出现
4. 配置字段再次变成“文档有、实现没吃”
5. provider 外部限制被误判成 skill 缺陷

---

## 9. Recommended Maintenance Rule

以后每次改动，至少按这个顺序走：

1. 先改最小范围
2. 跑 `validate_config.py`
3. 跑 `smoke_tests.py`
4. 如果改到 provider 相关，再跑 `provider_integration_smoke.py`
5. 若改了配置字段 / 输出结构，同步更新 reference 文档

---

## 10. Suggested Next Focus

这套现在已经很成熟了，后续不建议大改主干。

更推荐的小步增强方向：

- 补 `provider-xai.md`
- 增加更多 provider integration smoke 场景
- 增加最终发送闭环验证
- 继续积累 `failure-cases.md`

---

## 11. One-line Summary

`voice-router` 当前已经是一套 **高成熟、可维护、近满分的语音路由与平台投递规范系统**。后续重点不是“从 99 冲 100”，而是 **别漂、别烂、持续稳住**。
