# 08_CRITIQUE_TEST_LOG.md — RoleLens

> 更新日期：2026-07-08  
> 状态：RoleLens Red-Team Log v1

# 1. Main Red-Team Verdict
RoleLens is promising only if it remains a focused decision workflow system.

It fails if it becomes:
```text
generic CSV chatbot
generic AI team demo
full enterprise workflow platform
meeting summarizer
dashboard clone
```

# 2. Critical Risks

## R-001 — Scope Creep
Risk: RoleLens may expand into email sending, approval workflows, long-term memory, multi-user accounts, and BI integrations.  
Severity: Critical  
Decision: Fix Now  
Mitigation: v1 only supports CSV/Excel, report text, strategy profile, role views, risk checks, workflow plan, decision memo, simulated review.

## R-002 — Generic AI Wrapper
Risk: If RoleLens only outputs insights and recommendations, it will look like ChatGPT analyzing a CSV.  
Severity: Critical  
Decision: Fix Now  
Mitigation: must include evidence objects, role-specific outputs, risk flags, missing information, action dependencies, human review checklist.

## R-003 — Role-Playing Without Evidence
Risk: AI roles may sound like shallow personas.  
Severity: High  
Decision: Fix Now  
Mitigation: every role output must include supporting evidence, risk/assumption, missing information, next action, dependency.

## R-004 — Multi-Source Parsing Failure
Risk: trying to parse too many file formats may consume development time.  
Severity: High  
Decision: Fix Now  
Mitigation: v1 supports only CSV/Excel, pasted text, TXT/markdown. PDF support optional and limited to text extraction.

## R-005 — Weak Demo Story
Risk: demo may become abstract if dataset does not show role conflicts or dependencies.  
Severity: High  
Decision: Fix Now  
Mitigation: use controlled B2B SaaS churn / retention dataset with missing usage data, high-value churn risk, outlier customers, unclear sales action, industry context.

## R-006 — Overuse of Agent Frameworks
Risk: LangGraph/CrewAI too early may shift effort from product value to framework debugging.  
Severity: Medium-High  
Decision: Delay  
Mitigation: v1 uses orchestrator function, role prompt templates, Pydantic schemas, rule-based checks.

## R-007 — IBM Bob Usage Not Visible
Risk: IBM Bob is required as primary development tool; using other AI tools too much weakens challenge fit.  
Severity: High  
Decision: Fix Now  
Mitigation: record IBM Bob usage for architecture, Streamlit app, parser, schema, role engine, risk checker, tests, README, debugging.

# 3. Required Test Cases

## Test 1 — Generic CSV Chatbot Test
Input: simple CSV and business question.  
Expected: system must produce evidence card, role-specific views, risk flags, action plan, decision memo.

## Test 2 — Missing Data Risk
Input: customer dataset with missing usage_frequency.  
Expected: Data Engineer and Data Analyst roles flag missingness before Sales is told to act broadly.

## Test 3 — Outlier Risk
Input: dataset where one customer drives large revenue.  
Expected: system flags outlier and warns against overgeneralizing.

## Test 4 — Correlation vs Causation
Input: two variables move together.  
Expected: system should not claim causation without evidence.

## Test 5 — Weak Industry Context
Input: external report says industry demand is declining.  
Expected: system may use it as context but should not treat it as direct proof of company-specific decline.

## Test 6 — Role Dependency Test
Input: Sales wants to act, but data quality is poor.  
Expected: workflow planner places Data Engineer / Data Analyst validation before broad sales action.

## Test 7 — Unsupported Recommendation Test
Input: role output recommends “increase retention budget” without financial evidence.  
Expected: risk checker flags missing ROI / cost evidence and requires executive review.

## Test 8 — Final Memo Quality Test
Input: final decision memo.  
Expected: memo includes evidence, risks, assumptions, missing information, role perspectives, action sequence, and human review checklist.

# 4. Final Red-Team Rule
Before final submission, RoleLens must answer:

```text
If the judge has already seen 20 AI assistants, why is RoleLens still memorable?
```

Expected answer:

```text
Because it does not just answer a question. It converts mixed business materials into evidence-backed role views, risk flags, and a coordinated decision workflow.
```
