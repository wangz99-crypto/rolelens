# Onbrief 模式分析：生成、审查与修正

> 研究对象：`IBM-SkillsBuild-AI-Builders-Challenge/Onbrief`  
> 本地位置：`reference_repos/submissions/onbrief/`  
> 研究快照：`884f47fe5e293ca733238e54e4cc16d71ec25324`  
> 研究日期：2026-07-11

## 证据边界

当前公开快照只有一个 `README.md`，并且 README 只有一段项目定位。没有公开代码、截图、输入/输出 schema、评分 rubric、IBM Bob build log 或可运行 setup。因此下面明确分为“仓库明示事实”和“RoleLens 设计推导”。不能把推导写成 Onbrief 已实现细节，也不应复制其文案。

## 仓库明示的产品链路

README 明示 Onbrief 面向 Creative Industries，并自述使用 IBM Bob 为 AI Builders Challenge 构建。其定位可拆为：

```text
messy campaign idea
  → structured creative brief（messaging + art direction）
  → on-brief copy + shot/production cards
  → consistency check（text or image vs brief）
  → export pack（brief + prompt cards + checklist + social plan）
```

这段定位的强处是：输入痛点、结构化中间物、生成物、质量检查和最终交付包都在一句话中出现。它不是只说“用 AI 生成营销内容”。

## 为什么这个模式适合 RoleLens

RoleLens 可以借鉴的是工作流语法，而不是创意行业功能：

| Onbrief 定位中的阶段 | RoleLens 对应阶段 | 需要证明的产品机制 |
|---|---|---|
| messy campaign idea | messy business materials | 多来源载入、文档边界、来源标识 |
| structured creative brief | evidence objects | schema、provenance、冲突/缺失状态 |
| messaging + art direction | role-specific views | 同一证据在不同业务职责下的相关性与权限 |
| generated copy/cards | decision memo / proposed action | 结构化输出、引用和可执行动作 |
| consistency check | evidence/risk review | 维度化判断、rationale、失败原因 |
| export pack | decision pack | memo、证据、风险、review trail、next action |

最有价值的共同点是先建立一个规范化中间层，再让生成和审查围绕同一中间层发生。这样“审查”不是模型对自己刚生成文本的泛泛点评，而是把输出逐项对照 brief/evidence contract。

## RoleLens 应采用的生成—审查—修正闭环

```text
材料摄取
  → 证据正规化
  → 角色视图
  → 候选结论/行动
  → 独立风险审查
  → 具体修正建议
  → 人工决定
  → 可追踪 memo
```

### 1. 生成前先冻结判断依据

每次 run 先生成 versioned evidence set，并记录 source span、时间、实体、claim type、置信/缺失/冲突。之后的 view、risk 和 memo 都引用 evidence ID。没有依据的结论不能在 memo 中悄悄出现。

### 2. 审查必须按维度输出

Onbrief 当前 README 没有公开 per-dimension scoring 细节。RoleLens 可自行定义一套业务决策 rubric，例如：

- Grounding：每个关键主张是否有证据。
- Coverage：关键材料/约束是否遗漏。
- Consistency：不同来源或不同段落是否矛盾。
- Role fit：该结论是否属于当前角色职责和权限。
- Risk severity：若判断错误，对业务的影响有多大。
- Uncertainty：未知项是否被明确表达。
- Actionability：修正建议是否具体、可分派、可验证。

每个维度至少输出 `status/score`、`rationale`、`evidence_ids`、`concrete_fix`。不要只给总分。

### 3. 修正建议要能改变下一次输出

`concrete_fix` 应是机器和人都能执行的操作，例如“补充 Q3 pipeline 表中 owner 字段”“删除未被 E-014 支持的收入预测”“把结论从 approve 降级为 conditional review”。修正后重新运行审查，并保留 before/after 差异。

### 4. 人工审查不是最后一个按钮

应允许审阅者逐条 accept、reject、edit 或 request evidence；memo 只吸收已批准状态。高风险或证据冲突项应强制人工处理，不能用模型置信度自动越过。

## 推荐的结构化输出

```json
{
  "decision_item_id": "D-001",
  "role": "finance_reviewer",
  "claim": "...",
  "evidence_ids": ["E-003", "E-014"],
  "review": {
    "grounding": {"status": "pass", "rationale": "..."},
    "consistency": {"status": "warn", "rationale": "..."},
    "risk": {"severity": "high", "rationale": "..."},
    "concrete_fix": "Request the missing owner and effective date."
  },
  "human_status": "pending"
}
```

## README 叙事建议

RoleLens 的定位句也应覆盖完整链路，但不要塞入未经证明的能力。可采用这个逻辑模板：

> RoleLens turns fragmented business materials into traceable evidence, creates role-specific decision views, checks claims and risks against their sources, and produces a human-reviewed decision memo with concrete next actions.

随后用一个具体案例证明每个动词：上传了什么、形成哪些 evidence、两个角色看到什么差异、哪一项被标为 risk、审阅者如何修正、最终 memo 如何回链来源。

## “Built with IBM Bob” 写法

Onbrief 只在定位句末声明 Built with IBM Bob，没有提供过程证据。RoleLens 应更强：

- 写明 Bob 参与 requirements/spec、schema design、implementation、tests、README/demo 的具体任务。
- 链接或列出 Bob 产生后经人类审阅的 artifacts。
- 展示一次 Bob 帮助发现并修复失败 case 的记录。
- 避免暗示 Bob 是 RoleLens 运行时模型，除非产品确实这样部署。

## 不应学习或复制的内容

- 不复制 Onbrief 的一句话文案或创意行业术语。
- 不声称 Onbrief 已公开实现 critical scoring、per-dimension rationale 或 concrete fix；当前快照无法验证。
- 不把“生成 + 自评”直接视为可信，需要独立 rubric、source grounding 和 human gate。
- 不因结构相似而让 RoleLens 偏向 campaign/content generation；核心仍是 business data decision roles。

## 直接行动项

- 为 RoleLens 定义 evidence contract 和 review contract。
- 在 demo 中加入一个会失败的候选结论，展示审查与修正闭环。
- UI 同屏展示 claim、source、risk rationale 和 concrete fix。
- 导出的 decision pack 包含 evidence appendix 和 human review trail。
- README 的 IBM Bob 声明改为可核验 build log，而非一句标签。

