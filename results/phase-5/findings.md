# Phase 5 findings — hand-written ReAct loop

**Run date:** 5 October 2026  
**Model:** `qwen3:8b` with thinking disabled  
**Database:** isolated `home_ai_phase5_test_local`

## Result

The hand-written Phase 5 ReAct loop passed its current frozen baseline:

| Split | Cases | Passed | Result directory |
|---|---:|---:|---|
| Development | 3 | 3 | `development-20261005T193817` |
| Held-out | 2 | 2 | `held-out-20261005T193928` |

Every case completed within the five-iteration and eight-tool-call budgets.
No proposal was confirmed, and the evaluator rejected every proposal it created;
the household snapshot was unchanged after each case.

## What the traces demonstrated

- A read chain combined Hall-light state and egg inventory in two tool calls,
  then returned both facts.
- A conditional request read the milk stock, recognised the low threshold,
  staged an oat-milk proposal, and returned pending-confirmation wording.
- Multi-device reads returned front-door lock state and Hall-light state.
- A negative constraint, “do not change anything,” remained read-only.
- A condition that was not satisfied reported the egg quantity without staging
  a write proposal.

## Corrections made during the development run

1. The tool prompt now directs the model to stage an explicitly requested
   conditional write when its read result satisfies the condition, rather than
   asking a redundant question.
2. A bounded recovery turn handles a final response that says it will create a
   proposal but has not actually called the write tool. It can only stage a
   pending proposal; it cannot execute a write.
3. Device matching now accepts a compound device name split across the model's
   room and device arguments, while still requiring all terms to identify the
   same stored device.
4. Negated wording such as “do not change anything” no longer triggers the
   false-action-success sanitizer.

## Limitations and next work

This is a small local baseline, not a production-quality score. The evaluator
uses synthetic seeded home data and checks required terms/tool evidence; saved
traces still need human review for semantic quality.

## LangGraph comparison

The same frozen cases were run through the `agent: "langgraph"` API path after
adding LangGraph 1.2.13. Both paths reuse the same model, tools, confirmation
service, safety wording, and isolated database.

| Agent | Development | Held-out | Average model calls | Average latency |
|---|---:|---:|---:|---:|
| Hand-written loop | 3/3 | 2/2 | 2.67 / 2.00 | 2,839 ms / 2,008 ms |
| LangGraph | 3/3 | 2/2 | 2.33 / 2.00 | 5,235 ms / 1,972 ms |

The values are per split (development / held-out). They are single local runs,
so the latency difference is observational rather than a benchmark claim; model
startup and sampling variation dominate this tiny sample.

LangGraph made the control flow explicit in five visible nodes:
`load_context`, `model`, `execute_read_or_stage_write`, conditional routing,
and `finalize`. Its traces include node transitions in addition to model and
tool events. It did not improve model quality by itself, and it did not replace
the application-owned iteration cap, duplicate protection, database session
history, or write-confirmation boundary.

For this project, the hand-written loop remains the smaller reference
implementation. LangGraph is now a useful alternative when the flow needs more
branches, retry policies, resumable execution, or visual graph inspection.
