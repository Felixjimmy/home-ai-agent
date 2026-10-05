# Home AI Agent System — Version 5: Phase 5 Single-Agent ReAct implementation plan

**Updated: 5 October 2026 · Phase 5 complete for the defined local scope**

This document is the execution plan for Phase 5. It builds on Phase 4 session
and memory handling without changing their authority boundaries: sessions are
context, memories are untrusted data, live state comes from read tools, and
writes are only proposals until an explicit confirmation succeeds.

## 1. Goal and completion definition

Phase 5 turns the existing tool-enabled chat flow into a measured single-agent
ReAct loop. The model may inspect a tool result and choose a later tool call
before it returns its final answer. The application—not the model—owns the
iteration budget, tool validation, duplicate protection, tracing, and write
confirmation.

Phase 5 is complete when the hand-written loop and a LangGraph reproduction
pass the same frozen cases, demonstrate loop protection, preserve Phase 2
confirmation gating and Phase 4 session behavior, and have an honest results
record under `results/phase-5/`.

## 2. Implemented reference loop

The first, hand-written implementation is in `src/app/llm.py:run_agent`.
It now provides:

- a maximum of five model iterations and eight total tool calls;
- prompt assembly using Phase 4 context and memory references;
- tool schema validation before every execution;
- normalized read-tool results appended to the model conversation;
- write tools staged as pending actions, never executed by the loop;
- duplicate-call refusal rather than replaying a tool result indefinitely;
- iteration, tool-call, duplicate-call, and stop-reason diagnostics in the
  opt-in evaluation trace; and
- a truthful safe response when the model does not finish within the budget.

Focused safeguards are covered in `src/tests/test_phase5.py`. These tests mock
the model and database-backed tool execution so they are deterministic. The
first real-model baseline passed 3/3 development cases and 2/2 held-out cases;
see [Phase 5 findings](../../results/phase-5/findings.md).

## 2.1 Completion record

Phase 5 completed on 5 October 2026 for the defined local learning scope. The
hand-written loop and LangGraph graph each passed the frozen development (3/3)
and held-out (2/2) cases with no confirmed writes. The full evidence and the
latency/model-call comparison are in [Phase 5 findings](../../results/phase-5/findings.md).

## 3. Build sequence and historical implementation record

### Step 5.0 — Freeze the baseline

1. Start PostgreSQL and rerun the Phase 2, Phase 3, Phase 4, and Phase 5 test
   suites with `PYTHONPATH=src`.
2. Save the exact model, thinking setting, tool registry, test revision, and
   environment in a Phase 5 run manifest.
3. Confirm a session can still continue after one or more tool calls and that
   no memory record grants write authority.

**Gate:** baseline failures are recorded separately from Phase 5 behavior.

### Step 5.1 — Hand-written ReAct loop

This is implemented. Keep its state machine explicit:

```text
load Phase 4 context → ask model → final answer
                         │
                         └→ validate call → run read / stage write
                                             │
                                             └→ append result → ask model
```

The loop stops on a final answer, an iteration cap, a tool-call cap, or an
unavailable model. Invalid arguments, duplicate calls, and tool failures are
returned as safe tool results so the model can clarify or finish without
claiming success. An error result is context for the model, not evidence that
the requested action succeeded.

**Gate:** duplicate calls do not perform a second database read/write; a write
proposal remains pending even if later model text says it is complete.

### Step 5.2 — Frozen multi-step evaluation

Create development and held-out JSON cases before tuning the prompt. Include:

| Group | Required examples |
|---|---|
| Read chains | Device read followed by inventory read; answer uses both results |
| Mixed request | Read inventory, then propose a shopping-list addition only when low |
| Evidence boundary | Document fact plus live device read; no document text authorizes a write |
| Loop safety | Duplicate call, malformed arguments, unknown tool, tool error, and iteration cap |
| Memory safety | Remembered text asks for a write; current instruction overrides an old preference |
| Regression | Existing Phase 2 confirmation and Phase 3 injection/citation cases |

For each case save the response, trace, call order, iteration count, proposal
IDs and status, latency, request ID, and a before/after household snapshot.
Reject or expire every proposal created by an evaluation run.

**Initial local targets:** 100% no unconfirmed write; 100% duplicate protection;
100% iteration-cap behavior; at least 90% correct tool sequence and final
answer on held-out answerable cases; no unexplained Phase 2–4 regression.

### Step 5.3 — Failure and recovery behavior

Test model timeouts, database failures, invalid tool schemas, empty model
content, and a read that cannot find a target. The API must return a clear
failure or clarification, preserve any already staged proposal for audit, and
never say a failed or pending action is done. Do not automatically retry a
write proposal; a new explicit request or confirmation is required.

### Step 5.4 — LangGraph comparison — complete

Only after the reference evaluation is stable, add LangGraph as an optional
dependency and reproduce these nodes:

1. `load_context`
2. `model`
3. `validate_tool_call`
4. `execute_read_or_stage_write`
5. `finalize`

Use the same constants, tool registry, confirmation functions, memory selector,
and frozen tests. Do not let framework persistence replace the PostgreSQL
session record, and do not give the graph direct database-write authority.

Compare the two versions on implementation size, trace clarity, retry and
branching support, state persistence, latency, and failure behavior. The goal
is to learn what the framework provides, not to claim it is automatically safer.

### Step 5.5 — Completion record — complete

Add `results/phase-5/findings.md` with commands, environment, case hashes,
scores, failures, traces, trade-offs, and the reason for choosing or deferring
LangGraph. Update the roadmap only after both implementations have been
evaluated against the frozen held-out set.

## 4. File map

| Area | File |
|---|---|
| Reference loop | `src/app/llm.py` |
| API/session integration | `src/app/main.py`, `src/app/memory.py` |
| Tool policy and confirmation | `src/app/tools.py`, `src/app/actions.py` |
| Unit safeguards | `src/tests/test_phase5.py` |
| Evaluation harness | `src/app/evaluate_phase5.py` and `results/phase-5/` |
| Framework comparison | New LangGraph adapter only after Step 5.2 |

## 5. Deliberate non-goals

Phase 5 does not add multi-agent routing, autonomous execution, authentication,
cloud deployment, vector memory search, or hidden chain-of-thought logging.
Those are later phases or require a separate privacy and safety decision.
