# Home AI Agent System — Version 6: Bounded Multi-Agent Orchestration

**Updated: 5 October 2026 · Phase 5 complete · Phase 6 implementation in progress**

Phase 6 adds controlled delegation to the Phase 5 single-agent loop. The
purpose is to learn routing, task decomposition, specialist handoff, and result
aggregation without creating an autonomous swarm or weakening confirmation.

## 1. Starting point from Phase 5

The hand-written ReAct loop remains the reference implementation. It and the
LangGraph reproduction both passed the current 3/3 development and 2/2
held-out cases with no confirmed writes. LangGraph improved trace visibility,
but not model quality, so Phase 6 reuses the hand-written loop inside each
specialist.

The application continues to own iteration limits, tool validation, duplicate
protection, session context, tracing, and write confirmation.

## 2. Goal and non-goals

The coordinator chooses one or two domain specialists, gives them bounded
sub-tasks, restricts their tools in code, and combines their results.

This phase does not add autonomous writes, specialist-to-specialist messaging,
parallel execution, a new model, persistent agent memory, or a replacement for
the existing `handwritten` and `langgraph` API paths.

## 3. Design

### Coordinator

One structured routing call produces at most two typed tasks assigned to
`household` or `scheduler`, or asks for clarification. The coordinator has no
household tools.

### Household specialist

Handles device state, inventory, shopping-list actions, general household
records, and home-data tools. It receives an application-enforced tool subset.

### Scheduler specialist

Handles calendar-event proposals. The first slice gives it only the calendar
proposal tool. Narrow calendar reads can be added after evaluation justifies
them.

### Aggregator

Combines specialist answers, partial failures, and pending proposals while
preserving the distinction between a read, proposal, confirmed action, and
failure.

## 4. Limits

| Limit | Value |
|---|---:|
| Specialists per request | 2 |
| Total specialist tool calls | 8 |
| Iterations per specialist | 5 |
| Execution | Sequential |
| Writes | Pending proposals only |

The remaining global tool budget is passed to each specialist.

## 5. Step-by-step implementation

### Step 6.0 — Close Phase 5

Mark Phase 5 complete in the roadmap and README. Keep the hand-written path as
the default regression reference.

**Gate:** status and evidence agree across the roadmap, README, and Version 5
findings.

### Step 6.1 — Add typed routing contracts

Add strict Pydantic contracts for tasks and route plans. Reject unknown fields,
unsupported specialist names, empty tasks, and more than two tasks. Treat the
user message as data during routing.

**Implemented in:** `src/app/multi_agent.py`.

### Step 6.2 — Add application-enforced tool subsets

Limit the tool definitions supplied to each specialist and validate every tool
call against the same set before execution. Prompts explain authority but do
not provide the authority boundary.

**Implemented in:** `src/app/tools.py` and `src/app/llm.py`.

### Step 6.3 — Reuse the Phase 5 loop

Pass each specialist its domain prompt, restricted definitions, session
context, and remaining global budget. Preserve duplicate protection, tracing,
iteration limits, and pending-action staging.

**Gate:** Phase 5 safeguards remain green.

### Step 6.4 — Dispatch and aggregate

Dispatch at most two tasks sequentially. Record route, specialist, sub-task,
tool trace, proposals, and aggregate diagnostics. Report partial completion
truthfully if one specialist fails.

**Implemented in:** `src/app/multi_agent.py`.

### Step 6.5 — Expose the optional API path

Add `multi_agent` to `/chat`; retain `handwritten` as the default and
`langgraph` for comparison.

**Implemented in:** `src/app/main.py`.

### Step 6.6 — Test and evaluate

Test single-domain routing, mixed-domain routing, clarification, restricted
tools, proposal aggregation, budget exhaustion, failures, injection, and
no-write behavior. Then run frozen development and held-out cases, saving
routes, traces, model calls, latency, proposals, and cleanup results.

**Initial safeguards:** `src/tests/test_phase6.py`.

**Remaining evaluation work:** `src/app/evaluate_phase6.py` and `results/phase-6/`.

### Step 6.7 — Findings and completion decision

Write `results/phase-6/findings.md` only after verification. Compare routing
quality, latency, model-call overhead, failure behavior, and confirmation
safety with the Phase 5 single-agent reference.

## 6. Completion criteria

Phase 6 is complete when held-out routing accuracy is at least 90% for the
defined local cases; mixed requests reach all required specialists; tool
subsets and global budgets are enforced; no unconfirmed write occurs; pending
proposals remain traceable; failures are truthful; Phase 2–5 regressions stay
green; and overhead is documented.

## 7. File map

| Area | File |
|---|---|
| Coordinator and specialists | `src/app/multi_agent.py` |
| Tool restriction | `src/app/tools.py`, `src/app/llm.py` |
| API selector | `src/app/main.py` |
| Safeguards | `src/tests/test_phase6.py` |
| Evaluation runner | `src/app/evaluate_phase6.py` |
| Evidence | `results/phase-6/` |
| Findings | `results/phase-6/findings.md` |

