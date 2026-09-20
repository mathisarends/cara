# Dreaming

## Goal

`dreaming` continuously improves Cara's skills from past agent runs.

It analyzes conversations and tool traces, identifies recurring failure patterns, proposes skill changes, evaluates them against the current skill version, and promotes only improvements that pass the benchmark harness.

## Inputs

Dreaming reads:

- conversations
- turns
- tool calls and results
- errors
- active skill versions
- optional user feedback
- existing regression scenarios

## Flow

```text
past runs
  ↓
mine interesting experiences
  ↓
classify failures
  ↓
cluster recurring problems
  ↓
attribute problem to skill
  ↓
generate skill candidate
  ↓
baseline vs candidate evaluation
  ↓
reject or promote
```

## Main Components

### `ExperienceMiner`

Selects useful runs, especially:

- tool errors
- repeated tool calls
- unnecessary calls
- invalid arguments
- self-corrections
- user corrections
- unusually long or failed runs

### `DreamAnalyzer`

Turns experiences into structured issues:

```text
skill
problem category
evidence
root cause
suggested improvement
confidence
```

It should cluster similar issues instead of optimizing for individual conversations.

### `SkillOptimizer`

Takes:

```text
current skill
+ clustered issues
```

and produces a new immutable skill candidate.

It never edits the production skill directly.

### `EvaluationHarness`

Runs the current skill and candidate against the same scenarios.

Measures at least:

- task success
- tool errors
- unnecessary tool calls
- latency
- token usage
- regressions

Evaluation may combine deterministic assertions and LLM judging.

### `PromotionPolicy`

A candidate is promoted only when:

- success does not regress
- no critical regression exists
- relevant target metrics improve

Initially promotion should require human approval.

## Regression Corpus

Production failures can become permanent regression scenarios.

This allows the benchmark suite to grow from real usage over time.

## Scheduling

`libs/scheduler` periodically triggers:

```python
await dream_service.run()
```

The dreaming feature itself contains no scheduling logic.

## Boundaries

```text
gateway/features/dreaming
    Cara-specific improvement orchestration

libs/agent_eval
    generic agent evaluation harness

libs/scheduler
    scheduling only

agent/
    production agent runtime

workspace/skills/
    active skills
```

## Core Rule

**Production traces generate hypotheses. The evaluation harness decides whether a change is an improvement.**
