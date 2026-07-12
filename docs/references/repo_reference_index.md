# RoleLens 参考仓库索引

> 更新日期：2026-07-11  
> 原则：少而相关；clone 只用于本地研究，进入项目知识区的应是本目录 notes，而不是第三方仓库全文。

## 已 clone 并提炼

| 优先级 | 仓库 | 本地位置 | 快照 | 用途 | 对应笔记 |
|---|---|---|---|---|---|
| 必须 | `IBM-SkillsBuild-AI-Builders-Challenge/hands-on-labs` | `reference_repos/official/hands-on-labs/` | `bc5d7eb340ba2f02c157fe2125c70195f0e20b4b` | 官方 labs、README/setup/spec/Bob 工作流 | `official_hands_on_labs_notes.md` |
| 强烈建议 | `IBM-SkillsBuild-AI-Builders-Challenge/Onbrief` | `reference_repos/submissions/onbrief/` | `884f47fe5e293ca733238e54e4cc16d71ec25324` | 结构化中间物 → 生成 → 一致性检查 → 交付包 | `onbrief_pattern_analysis.md` |
| 选择性 | `IBM-SkillsBuild-AI-Builders-Challenge/AssetOpsBench` | `reference_repos/architecture/AssetOpsBench/` | `6b3beefb099b8b770008972d4022a86e322cbf6b`（shallow） | domain tools/roles、MCP boundary、trajectory、evaluation | `assetopsbench_agent_architecture_notes.md` |

## 只读 README / 页面扫描，不 clone

| 仓库 | 当前可见定位 | 可借鉴 | 结论 |
|---|---|---|---|
| `same-whistle` | IBM Challenge 组织中的公开小型仓库；本次 GitHub 页面正文抓取未成功 | 仅在后续能验证 README 后研究 explainable audit language | 不进入核心参考，不 clone |
| `RefLens.ai` | IBM Challenge 组织中的公开小型仓库；本次 GitHub 页面正文抓取未成功 | 仅在后续能验证 README 后研究 consistency/audit rationale | 不进入核心参考，不 clone |
| `matchmind-ai` | 将 football events 转成 momentum/tactical/key-moment explanations；README 强调 explainability、不同受众层级、Granite + LangFlow | `event → explanation → key moment`、problem/solution/architecture/challenge alignment 的 README 顺序 | 可作叙事参考，不进入产品架构 |
| `RaceRecapAi` | 将 FastF1 telemetry/analytics 转成个性化 recap，列出清晰 project tree、setup 和 watsonx/Granite 配置 | README 的功能、目录、setup 写法 | 距 RoleLens 远，不 clone |
| `f1-telemetry-vfs-router` | 页面定位强调 telemetry + biometrics、edge/VFS、Granite 与实时 failure prediction | 技术定位句和 demo 叙事可观察 | 高技术噪声风险，不 clone |
| `BioTactix-AI` | 页面定位强调 biometric fatigue + tactical spacing、Granite/watsonx.ai、XAI 和 substitution alerts | explainable output 的定位语言可观察 | 业务与 RoleLens 远，不 clone |

说明：README-only 项目只作为轻量浏览参照。`same-whistle` 和 `RefLens.ai` 本次只确认了仓库身份与公开状态，没有取得足够正文证据，因此不在其他笔记中引用其具体能力。

## 明确不 clone

- `friendly-fishstick`
- `resume-ai-pro`
- `World-Cup-game-assistant`
- `yc.inn`
- `local-llm-academic-tutor`
- 随机空仓库、无关 fork、private repos

原因：与 RoleLens 目标弱相关、质量/可验证性不稳定、容易扩大上下文噪声，且不能帮助证明 evidence、risk、review 和 decision workflow。

## 综合模式地图

```text
官方 hands-on-labs
  └─ 如何让项目可学、可运行、可复现；如何记录 Bob 的开发过程

Onbrief
  └─ 如何用结构化中间层连接生成、检查和最终交付

AssetOpsBench
  └─ 如何让 domain roles、tool boundaries、trajectory 和 evaluation 可验证

RoleLens
  └─ materials → evidence → role views → risk review → human decision → memo/action
```

## RoleLens 采用 / 不采用决策

### 采用

- 独立 spec 与 phased, runnable demo。
- 可追溯 evidence object 作为共享中间层。
- role-specific tool/data/output boundary。
- 按维度给 rationale 和 concrete fix 的 review contract。
- 保存 trajectory，并支持离线重复评分。
- deterministic checks + LLM judge + human review 的混合评估。
- IBM Bob 的可核验 build log。

### 不采用

- 仅凭多个 prompt 就称 multi-agent。
- 生成模型对自己的输出给一个总分即视为审查。
- 堆砌 Granite/Bob/MCP 名称而没有运行时位置和证据。
- 为复制比赛项目外观而引入体育、遥测或创意行业功能。
- 将第三方完整仓库上传到项目知识区。

## 建议上传到项目知识区的文件

只上传以下整理材料：

1. `official_hands_on_labs_notes.md`
2. `onbrief_pattern_analysis.md`
3. `assetopsbench_agent_architecture_notes.md`
4. `repo_reference_index.md`

上传前可再加一份 RoleLens 自有的 `reference_to_product_decisions.md`，把“参考观察”转换成已批准的产品决策，避免第三方描述与本项目事实混在一起。

