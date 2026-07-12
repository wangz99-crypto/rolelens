# IBM SkillsBuild hands-on-labs 参考笔记

> 研究对象：`IBM-SkillsBuild-AI-Builders-Challenge/hands-on-labs`  
> 本地位置：`reference_repos/official/hands-on-labs/`  
> 研究快照：`bc5d7eb340ba2f02c157fe2125c70195f0e20b4b`  
> 研究日期：2026-07-11

## 结论先行

这个仓库最值得 RoleLens 学习的不是某段代码，而是“把 AI 编程过程写成可复现学习路径”的方式：先说明用户会得到什么，再把环境、材料、提示词、审批动作、运行、观察、清理和总结串成一条完整路线。它还展示了从 prompt-driven 的快速实现，逐步转向 specification-driven 的规划、分阶段交付、测试与反思。

RoleLens 应借鉴这种可验证的项目叙事，但不要照搬教学口吻。我们的版本应更像一个业务决策工作台：从真实材料进入，生成可追溯 evidence objects，再形成 role-specific views、风险判断、decision memo 和明确下一步。

## 仓库事实

仓库根目录将自己定义为 IBM SkillsBuild AI Builders Challenge 的 hands-on learning labs，目标是让参与者通过 building、experimenting 和在 GitHub 上 sharing 来学习。当前快照包含三个按月份/主题组织的实验：

- `01_torcs_lab/`：TORCS 实验，含介绍、主实验、平台设置 PDF、容器构建材料与 `RESULTS.md`。
- `02_football_lab_june/`：足球预测实验，按 intro、Bob setup、主实验说明、Jupyter notebook、data、images 分层。
- `03_djapp_july/`：DJ Web 应用实验，含 `README.md`、独立 `SPEC.md`、Bob setup、可运行前端代码与截图。

当前仓库约 59 个普通文件。它不是统一模板生成的“完美样板”：例如 football 根 README 仍是 placeholder，部分内部链接/文件名与实际目录有偏差。可学习其结构和叙事方法，但不能无审查复制。

## 官方 labs 的内容组织模式

### 1. 入口先回答“做什么、学什么、多久、需要什么”

Football intro 的主要顺序是：项目概览 → 学习目标 → 预计用时 → prerequisites → 文件结构 → 按顺序完成 → Bob 如何参与 → 完成后得到什么。它降低了第一次打开仓库时的认知负担。

RoleLens README 可采用对应顺序：一句定位 → 业务问题 → 用户会完成的决策任务 → demo 输入 → 预期输出 → 5 分钟 quick start → 架构与 IBM 技术 → evidence/risk/review 机制 → limitations。

### 2. 材料按学习阶段分层，而不是把所有内容塞入一个 README

Football lab 把引导、环境设置、主要步骤、notebook、数据和图片分开；DJ lab 把用户操作流程放在 README，把可独立阅读的目标、范围、架构、阶段、技术决策和限制放进 `SPEC.md`。

对 RoleLens 的建议：

```text
README.md                 # 评委与新用户的主叙事
docs/demo_walkthrough.md  # 可复现 demo 路线
docs/architecture.md      # evidence、roles、risk、review、tool boundaries
docs/evaluation.md        # 场景、rubric、失败条件、human review
docs/bob_build_log.md     # Bob 在规划/实现/测试中做了什么
docs/limitations.md       # 非目标、已知缺口、人工责任边界
examples/                 # 小而可信的输入与期望输出
```

### 3. 用可复制的 prompt + “工具会做什么”形成可复现路径

Football lab 不只给命令，也给要提交给 Bob 的提示词，并在每个提示词后写明 Bob 会请求哪些权限、创建什么环境、返回什么结果。DJ lab 进一步让 Bob 探索代码库、生成实施计划、逐项实现和测试。

RoleLens 的 Bob 记录不应只写“Built with IBM Bob”。至少应保留三类具体证据：

- Planning：Bob 如何把业务目标转成模块、数据结构、acceptance criteria。
- Implementation：Bob 负责了哪些明确的实现单元，人类如何审阅或修改。
- Verification：Bob 如何运行测试、发现风险、根据失败结果修正。

推荐表述：IBM Bob was used as an AI development partner across planning, implementation, debugging, and verification；随后列出可检查的 artifacts，而不是笼统声称“Bob built the app”。

### 4. 从 vibe coding 过渡到 spec-driven development

DJ lab 明确指出：自然语言驱动的快速生成有速度优势，但在项目复杂后容易出现结构、质量和理解问题，因此转向由清晰 specification 引导的人机协作。其 `SPEC.md` 包含 purpose、success criteria、non-goals、scope decisions and rationale、architecture mapping、phased delivery、technical decisions、known limitations、stack/layout。

这对 RoleLens 很关键。需要先把以下内容写成可检验约束，再让模型生成：

- Evidence object 最低字段与 source trace。
- 每个 business role 能看到什么、不能断言什么。
- Risk score 的维度、证据要求与不确定性表达。
- Human review 在何处强制发生。
- Decision memo 必须引用哪些 evidence IDs。
- 缺失/冲突信息时是 abstain、flag 还是 request clarification。

### 5. 分阶段交付，每阶段都可运行

DJ `SPEC.md` 用 P0–P6 描述自包含、可运行的增量，并同时标记已完成和 planned。这比一次性展示大而模糊的 architecture 更可信。

建议 RoleLens demo 路线：

1. P0：载入一组固定业务材料并保留来源。
2. P1：抽取 evidence objects，显示引用与置信/缺失状态。
3. P2：生成两个 role-specific views，证明同源证据、不同职责视角。
4. P3：生成 risk assessment，逐项给 rationale。
5. P4：输出 decision memo，每个主张能回链证据。
6. P5：人工接受、驳回或修正，并留下 review trail。
7. P6：用固定 scenario rubric 评估 groundedness、coverage、role fit 和 actionability。

### 6. 权限、人工动作和清理都写清楚

官方 lab 明示哪些步骤因安全原因必须手动完成，也明确 Bob 在执行命令前会请求批准。流程结束时还包含停止服务/清理进程的步骤。

RoleLens 应把 human-in-the-loop 写成产品机制，而不是免责声明：上传/读取边界、敏感字段、外部工具调用、最终决策批准、审计记录和数据保留都应在 demo 中可见。

## README / notebook / setup 写法清单

### README

- 首屏一句话同时包含对象、任务、结果。
- 给出 learning/product outcomes，而不只列技术栈。
- 主流程用有序步骤，并说明每一步的成功状态。
- 图片放在关键状态之后，证明 UI 或运行结果。
- 最后总结“完成了什么、现在能做什么”。
- 对计划中但未实现的内容明确标记 planned。

### Notebook

Football notebook 与说明形成“解释步骤 → 向 Bob 提示 → 运行代码 → 观察结果”的循环。RoleLens 若使用 notebook，应把它用于可重复的 evidence/evaluation 实验，而不是作为最终 demo UI；每个单元应显示输入、转换、输出、检查点和失败解释。

### Setup

- 把账户/安装前置条件从主流程拆出。
- 给出操作系统、运行环境、依赖与启动方式。
- 说明 AI 助手的模式切换、审批和凭证边界。
- 避免把 token 或密钥直接放在聊天/README 示例中；使用 `.env.example` 和最小权限说明。
- 验证所有路径、链接、命令和拼写；官方仓库本身存在可见的小瑕疵，RoleLens 应把这当作 QA 提醒。

## Granite 与 IBM 技术表达

这个快照主要展示 IBM Bob 作为 software lifecycle/development partner；Football lab 的业务模型是常规 Python/ML workflow，DJ lab 是前端音频应用。不要从该仓库推断“使用 Bob 就等于使用 Granite”。RoleLens README 应分别说明：

- IBM Bob：用于项目开发生命周期的哪些阶段，并以 artifacts/build log 证明。
- IBM Granite / watsonx.ai（若实际使用）：在哪个运行时步骤处理什么输入、产生什么结构化输出、采用什么 guardrail/evaluation。
- 其他 IBM 组件：只写实际可运行、可演示的集成，不用 logo 堆叠代替架构说明。

## 如何证明 RoleLens 不是普通 AI wrapper

把差异落在可检查的对象和约束上：

- 同一来源被正规化为带 provenance 的 evidence objects。
- 不同角色不是不同 system prompt，而是有明确职责、输入视图和输出 schema。
- 风险不是一句模型评论，而是维度化评分、rationale、证据引用和不确定性。
- memo 不是自由生成，而是由 evidence/risk/review 状态约束。
- 人类修改形成可追踪 decision trail。
- 固定 scenarios 可以重复运行和比较，而不是只展示一次“好看的回答”。

## 直接行动项

- 为 RoleLens 建立一份独立 spec，包含 success、non-goals、scope rationale 和 phased demo。
- README 加入 5 分钟 evaluator path，以及一张从 materials 到 next action 的架构图。
- 新增 `docs/bob_build_log.md`，用实际任务/commit/test 记录 Bob 用途。
- 为每个阶段定义可观察的成功条件和一个明确失败样例。
- 对 README 内全部命令、路径、截图和 IBM 技术声明做发布前验证。

