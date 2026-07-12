# AssetOpsBench：domain-specific agent 与 evaluation architecture 笔记

> 研究对象：`IBM-SkillsBuild-AI-Builders-Challenge/AssetOpsBench`（仓库 README 的 canonical link 指向 `IBM/AssetOpsBench`）  
> 本地位置：`reference_repos/architecture/AssetOpsBench/`  
> shallow clone 快照：`6b3beefb099b8b770008972d4022a86e322cbf6b`  
> 研究日期：2026-07-11

## 结论先行

AssetOpsBench 最适合 RoleLens 借鉴的是三层分离：domain tools、agent/orchestration、offline evaluation。它通过具体工业角色、受限 MCP server、可保存 trajectory、ground-truth scenario 和多种 scorer 证明自己不只是一个通用聊天 agent。

RoleLens 不需要复制其工业资产栈、多 runner 规模或复杂部署。应该借鉴其边界和可评估性：把 business evidence 操作封装成明确工具，把 role 定义成职责与可用工具的组合，把每次决策保存成可重放 trajectory，再在不重新调用 agent 的情况下做离线评分。

## 仓库架构事实

当前快照包含：

- 六个 domain-oriented FastMCP servers：IoT、utilities、FMSR、work order、time-series foundation model、vibration。
- 多种 runner：plan-execute、deep agent、Claude agent、OpenAI agent、Stirrup agent，以及无工具/无规划的 direct-LLM baseline。
- 基于 stdio 的 MCP server，由 runner 按需启动；每个 server 暴露自己的 tool schema。
- plan-execute 路线会发现 server/tool 能力、生成带 server/tool/expected output 的 plan、逐步执行，并把前序结果传入后续参数解析。
- observability 分为 trace（聚合元数据/指标）与 trajectory（逐 turn/step 的内容、工具输入输出、token/时延等）。
- offline evaluation 将保存的 trajectory 与 scenario/ground truth 对齐，然后路由到 scorer，输出单次结果与聚合报告。

## 值得迁移的设计原则

### 1. Domain-specific 不等于给通用 agent 换名字

AssetOpsBench 的领域性来自实际工具和数据边界：IoT server 负责传感器，FMSR 负责 failure mode 关系，WO 负责工单，TSFM 负责时序模型，vibration 负责诊断。角色差异可在可调用工具、数据、任务和评估中被观察。

RoleLens 应把角色表达为 business data decision roles：

| RoleLens role | 核心职责 | 可用数据/工具 | 明确禁区 |
|---|---|---|---|
| Evidence Curator | 抽取、去重、标源、标冲突 | source reader、entity linker、evidence store | 不做最终批准 |
| Finance Reviewer | 检查财务假设、口径和暴露 | approved finance evidence、calculation tools | 不补造缺失数字 |
| Operations Reviewer | 检查交付、依赖、owner、时间风险 | operations evidence、dependency view | 不改写财务结论 |
| Risk Reviewer | 跨证据检查风险和不确定性 | evidence query、rubric scorer | 不自动替代业务 owner |
| Decision Editor | 汇总已批准结论与行动 | approved claims、review status | 不纳入 pending/rejected claim |

区别不应只是五段不同 prompt；每个角色都需要结构化输入、工具白名单、输出 schema、handoff contract 和评估案例。

### 2. MCP server 是能力边界，不是装饰性协议

AssetOpsBench 把领域逻辑拆成独立 stdio 服务，并由客户端发现 tool schemas。对 RoleLens，可把能力边界缩小为：

- `source-mcp`：只读原始材料和 source spans。
- `evidence-mcp`：创建/查询 versioned evidence objects。
- `policy-mcp`：读取 rubric、role policy、approval threshold。
- `decision-mcp`：创建 candidate claim/memo，但只允许引用 evidence IDs。
- `review-mcp`：记录人工 accept/reject/edit/request-evidence。

边界应实现最小权限。读取、生成候选、批准和导出不能默认由同一个无约束工具完成。若当前 MVP 不值得真的拆成多个进程，也应先在模块/API 层保持同样的契约，将 MCP 作为可替换接口而非比赛 buzzword。

### 3. Plan-execute 让路径可见、可检查

AssetOpsBench 的 plan step 包含 step number、task、server、tool、tool args、expected output；执行时按步骤路由并保存 StepResult。RoleLens 的 decision plan 可采用：

```text
Step 1 — ingest sources          → source tool      → source manifest
Step 2 — normalize evidence     → evidence tool    → evidence set v1
Step 3 — build role views       → role policies    → scoped views
Step 4 — draft candidate claims → decision tool    → claims with evidence IDs
Step 5 — evaluate risks         → review tool      → rubric results + fixes
Step 6 — human review           → approval gate    → accepted/rejected/edited
Step 7 — compose memo           → decision tool    → traceable decision pack
```

每步必须有 expected output 和失败状态。关键点是不要让执行器在工具失败后继续产生“看似完成”的 memo。

### 4. Trajectory 与 evaluation 解耦

AssetOpsBench 的评估路径是 `agent run → trajectory(run_id) → evaluate → report`，并把重新评分作为 first-class：可以更换 scorer/judge 而无需重跑 agent。

RoleLens 应保存足够但受控的 decision trajectory：run/scenario ID、模型与版本、输入 source manifest、evidence set version、role/tool calls、候选 claims、风险结果、人工修改、最终 memo。敏感原文与可分享评估记录应分层存储。

解耦带来三个直接好处：

- 修改 rubric 后可重评旧 run。
- 比较 prompt/model/role policy 时不必重新摄取材料。
- 评委可看到失败案例、修正和一致的报告，而不只看现场生成。

### 5. 评分同时看结果质量与运行行为

AssetOpsBench 当前可用的 LLM-as-judge 使用六个标准：task completion、data retrieval accuracy、generalized result verification、agent sequence correct、clarity and justification、hallucinations。总体通过要求前五项为 true 且 hallucinations 为 false；rationale/details 被保留。它还提取 turns、tool calls、unique tools、tokens、duration 和估算成本。

RoleLens 可对应设计：

- Evidence grounding：关键 claim 是否引用且忠实于来源。
- Retrieval/coverage：必要材料是否被找到，是否遗漏关键约束。
- Calculation/consistency：数字、时间、实体和跨文档陈述是否一致。
- Role-policy compliance：角色是否越权或使用不允许的数据。
- Review sequence：高风险项是否经过规定人工 gate。
- Clarity/actionability：rationale 和 next action 是否清楚。
- Unsupported claims：是否出现无依据陈述；这是 hard-fail 候选。

运行指标可以作为工程维度，但不能用低 token/低 latency 替代业务正确性。

### 6. Judge 也需要治理

AssetOpsBench 禁止同一模型对自己的 trajectory 做 self-judging，并保留完整 review details。这提醒 RoleLens：评分模型不是绝对真相。

建议做法：

- 固定一小组人工标注 scenarios 作为 anchor。
- 规则可验证的部分使用 deterministic scorer（引用存在、schema、数字一致性）。
- 语义质量才交给 LLM judge，并要求 rationale。
- 区分评估模型与被评估模型，记录版本。
- 对高风险结果做人工复核，并报告 judge disagreement。

## RoleLens 的最小 evaluation pipeline

```text
scenario fixture
  + expected evidence/required constraints
  + forbidden claims
  + required human gates
        ↓
RoleLens run + saved trajectory
        ↓
deterministic checks
  + rubric judge
  + human spot check
        ↓
scenario report + aggregate comparison
```

建议首批 8–12 个 scenarios 覆盖：材料缺失、同名实体、冲突数字、过期事实、角色越权、高风险但低证据、支持性证据充分、人工驳回后重新生成。每个 scenario 定义 expected evidence、must-not-claim、required gate 和 success criteria。

## 不应照搬的部分

- 不把工业 IoT/FMEA/work order 名词迁移到 RoleLens 产品叙事。
- 不为展示 agent 数量而做五套框架；MVP 一个可靠 orchestration + 一个 baseline 足够。
- 不在没有独立 tool boundary 时声称 multi-agent architecture。
- 不把 LLM judge 当唯一真值；仓库内部分 scorer 在当前分支仍是 skeleton。
- 不为了 MCP 而拆分微服务；先证明权限边界、可观察性和可评估性。

## README/架构表达可借鉴点

- 首屏用一句 domain + users + powered-by 的定位。
- 用 at-a-glance 数字说明 scenarios、roles/agents、评估覆盖，但数字必须可验证。
- 同时提供 quick start、example scenarios、architecture、evaluation 和 limitations。
- 展示 model-only baseline，让领域工具的真实增益可比较。
- 将架构声明连接到目录和可运行命令，不停留在图示。

## 直接行动项

- 把 RoleLens role 定义落到 tools/data/output/forbidden actions 四列。
- 设计 versioned decision trajectory schema。
- 建立至少一个 direct-LLM baseline 与 structured RoleLens pipeline 对比。
- 编写 8–12 个固定 scenarios 和混合 deterministic/LLM/human rubric。
- 将 unsupported claim 和 missing required human review 设为 hard-fail。
- README 用一条真实 run 展示 plan、tool boundaries、risk result、human edit 和 final memo。

