# Spec-Driven Development (SDD): Personal Multi-Agent Assistant

## 1. System Intent & Architecture
This document serves as the Architectural North Star for the Personal Hierarchical Multi-Agent Assistant.
It translates human intent into unambiguous behavioral contracts following the 2026 Google Whitepaper series.

```
Agent = Model (LLM Brain) + Harness (Tools + Memory + Sub-Agent Delegation + Quality Evals)
```

## 2. Behavior-Driven Development (BDD) Specifications

### Feature: Hierarchical Task Delegation
```gherkin
Scenario: User issues a multi-domain command
  Given the user submits a command requiring both factual research and computation
  When the Master Orchestrator parses the prompt
  Then it must decompose the command into at least one "research" sub-task and one "data" or "coding" sub-task
  And it must assign each sub-task to the respective specialist agent
```

### Feature: Two-Tier Evaluation and Self-Correction Loop
```gherkin
Scenario: Sub-agent produces code with a syntax or runtime error
  Given a sub-agent generates a Python script containing a syntax or execution failure
  When the Evaluator Agent runs Tier 1 Deterministic validation
  Then the Evaluator must REJECT the output immediately
  And route actionable error critique back to the sub-agent
  And the sub-agent must self-repair the code
  And re-submit for evaluation up to MAX_EVAL_RETRIES times

Scenario: Sub-agent produces a flawless response
  Given a sub-agent produces an accurate, fact-grounded response
  When the Evaluator Agent evaluates the output against rubric dimensions
  And average score is >= 4.0
  Then the Evaluator must mark verdict as "APPROVED"
  And the Master Orchestrator advances to synthesis
```

### Feature: Persistent Memory and Auditability
```gherkin
Scenario: User preferences dictate output style
  Given the user has configured custom assistant rules in SQLite memory
  When the Master Orchestrator compiles the final report
  Then it must incorporate the persistent rules into its synthesis prompt
  And log the full execution trajectory and evaluation records into SQLite
```
