# 05_PRODUCT_SPEC_seed_Data_to_Decision_20260703

> 文件用途：基于当前证据，为最强候选方向生成第一版 Product Spec 草稿。  
> 状态：Seed Draft / Not Final  
> 更新日期：2026-07-03  
> 使用方式：可以复制到 `05_PRODUCT_SPEC.md`，但需要在下一轮 Batch A 研究后再修订。

---

# Product Name

暂定名称：

```text
Insight-to-Action Auditor
```

备选名称：

```text
Data-to-Decision Assistant
Business Insight Quality Gate
Dashboard-to-Decision Copilot
AI Business Insight Validator
```

当前最推荐：

```text
Insight-to-Action Auditor
```

原因：避免听起来像普通 Data Analysis Assistant，强调从 insight 到 action 的审查和转化。

---

# Target User

Primary users:

```text
Junior analysts, Business Analytics students, and small teams that need to turn data into evidence-backed business recommendations.
```

Secondary users:

```text
Non-technical business users who read dashboards but need help understanding whether an insight supports a decision.
```

---

# One-Sentence Value Proposition

```text
Insight-to-Action Auditor helps junior analysts turn data findings into evidence-backed business recommendations by checking whether each insight is supported, actionable, and safe from common interpretation risks.
```

中文解释：

```text
它不是单纯帮你分析数据，而是帮你判断“这个数据洞察是否足以支持一个商业行动”。
```

---

# Problem Statement

Business analysts and students often know how to create charts and dashboards, but struggle to convert data findings into clear, evidence-backed business recommendations. Existing AI tools can generate insights, but those outputs may be generic, unsupported, or misleading if data context is weak. A stronger workflow needs not only generation, but also evidence checks, assumption tracking, risk detection, and human review.

---

# Core Workflow

```text
1. User uploads CSV or sample business dataset.
2. System profiles the dataset.
3. System identifies candidate insights.
4. System checks whether each insight is supported by data.
5. System flags interpretation risks.
6. System generates business recommendations.
7. System shows assumptions and missing context.
8. User reviews a final decision memo.
```

---

# Must-Have Features

## 1. CSV / sample data input

User can upload a CSV or select a sample dataset.

## 2. Data summary

System summarizes:

- rows / columns
- missing values
- numeric / categorical fields
- time fields
- possible target metrics

## 3. Candidate insight generation

System identifies:

- trends
- anomalies
- segment differences
- top / bottom performers
- possible metric changes

## 4. Evidence check

Each insight must include:

```text
Insight:
Supporting Data:
Confidence:
Missing Context:
```

## 5. Risk detection

System flags:

- missing values
- outliers
- small sample size
- short time window
- unclear metric definition
- correlation vs causation risk
- unsupported recommendation
- visualization risk if chart metadata is used

## 6. Recommendation generation

Each recommendation must include:

```text
Recommendation:
Why:
Evidence:
Assumptions:
Risks:
Human Review Required:
```

## 7. Decision memo output

System generates a structured memo:

```text
Executive Summary
Key Insights
Evidence
Risks and Assumptions
Recommended Actions
Human Review Checklist
```

---

# Nice-to-Have Features

```text
1. Simple chart generation
2. Before/After comparison panel
3. Export memo to Markdown
4. Upload existing AI-generated report for audit
5. Simple scoring: Evidence Strength / Actionability / Risk Level
```

---

# Out of Scope

```text
1. Power BI / Tableau API integration
2. Real-time dashboard connection
3. Complex machine learning model training
4. Multi-user collaboration
5. Authentication
6. Enterprise deployment
7. Full BI platform replacement
8. Automatic business action execution
```

---

# AI Core Functions

```text
1. Interpret dataset summary.
2. Generate candidate insights.
3. Translate insights into business recommendations.
4. Detect weak assumptions and unsupported claims.
5. Generate structured decision memo.
6. Produce human review checklist.
```

---

# Non-AI / Rule-Based Functions

```text
1. CSV loading and validation
2. Missing value detection
3. Outlier detection
4. Data type detection
5. Basic metric summary
6. Rule-based risk flags
7. Output formatting
```

---

# Human Review Points

```text
1. User reviews whether the business context is correct.
2. User checks whether recommendations are feasible.
3. User confirms whether missing information should change the conclusion.
4. User approves final decision memo.
```

---

# Demo Scenario

## Before

A junior analyst has a sales dataset and creates a few charts. The dataset shows revenue differences across regions and products, but the analyst is unsure what recommendation to make.

## During

The system:

1. Uploads the dataset.
2. Profiles the data.
3. Finds candidate insights.
4. Flags risk: one region has small sample size; one product spike is driven by outlier.
5. Generates evidence-backed recommendations.
6. Shows assumptions and human review checklist.

## After

The analyst gets a structured decision memo that separates:

```text
Insight
Evidence
Risk
Recommendation
Human Review
```

---

# Success Criteria

```text
□ The system produces structured output, not generic chat.
□ Each recommendation includes supporting evidence.
□ The system flags at least 3 types of interpretation risk.
□ The demo clearly shows Before → During → After.
□ The MVP can run locally or in Streamlit.
□ The project does not require external enterprise integrations.
□ IBM Bob usage is recorded in development logs.
```

---

# Current Risks

```text
1. The project may still look like a CSV chatbot.
2. Business recommendations may sound generic.
3. Evidence checks may be too shallow.
4. Sample dataset must be carefully chosen.
5. Need to show why this is a workflow system, not just a chat interface.
```

---

# Next Validation Needed

```text
1. Run Batch A deep research.
2. Find more user evidence from junior analysts / BI users.
3. Analyze direct competitors: Power BI Copilot, Tableau Pulse, ChatGPT Advanced Data Analysis.
4. Create 2 sample datasets and test whether demo story is strong.
5. Red-team the product against “generic CSV chatbot” criticism.
```

