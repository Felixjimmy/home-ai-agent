# Phase 3 Findings — Persistent Document Retrieval

Implementation completed: 5 October 2026 · Chat model: `qwen3:8b` · Embedding
model: `embeddinggemma` (768 dimensions) · PostgreSQL with pgvector

## What was built

- Persistent upload storage for UTF-8 text, Markdown, and text-based PDFs.
- Confirmation-gated document creation, metadata update, source replacement,
  reindexing, and deletion. Uploading alone never makes a file searchable.
- Durable PostgreSQL indexing jobs with leases, retry limits, restart recovery,
  inactive-version construction, and atomic activation.
- Section/page-aware extraction, deterministic character chunking, local batch
  embeddings, exact cosine-distance search, source filters, context limits, and
  retrieval configuration hashes.
- Read-only knowledge chat with server-resolved citations and explicit
  `supported`, `insufficient`, or `conflicting` evidence states.
- A separate indexing worker and additive migrations for existing databases.
- Phase 2 action corrections: quoted-injection task recovery, application-owned
  pending wording, stable dates/target IDs, request tracing, rollback-safe
  failure recording, proposal idempotency, concurrent confirmation handling,
  and distinct expiry/failure states.

## How persistence works

Original source files are stored under `storage/documents/` unless
`DOCUMENT_STORAGE_DIR` overrides it. PostgreSQL stores document metadata,
versions, chunks, embeddings, jobs, and audit/action records. Restarting the API,
worker, or Ollama does not require another upload or re-embedding. Back up the
database and document directory together.

Replacement versions are indexed separately. The previous ready version remains
active unless and until the replacement finishes successfully. Confirmed deletion
immediately removes the document from retrieval and queues source-file cleanup.

## Phase 2 corrections

The old ten cases are now regression cases. Both the pre-model-guard-on and
pre-model-guard-off runs passed 10/10 automated task, safety, field, and
no-write checks. H10 now ignores the hostile quotation and answers the real
door-state question from a read tool. “Guard off” still means the pre-model
authority matcher is disabled; normal prompts, validation, and execution
boundaries remain active.

Calendar proposals now store the resolved timezone-aware timestamp and exact
participant identities. Device and CRUD update/delete proposals store stable
record identities and preconditions. A changed target causes a conflict instead
of silent retargeting. Legacy pending actions were expired during migration
because they do not contain these stable details.

## Verification

- **42 automated tests passed** against a separate database named with the
  `home_ai_phase3_test_` prefix. This includes the original Phase 2 unit/database
  tests and new upload, PDF extraction, citation, rollback, concurrency,
  idempotency, version replacement, deletion-during-indexing, worker-lease,
  stale-proposal, no-write knowledge-mode, and injection tests.
- All application modules compiled successfully. The Python launcher emits a
  harmless “Failed to find real location” warning in this environment while
  returning success.
- Local `embeddinggemma` smoke test returned the expected 768-dimensional vector.
- Phase 2 live-model regression: **10/10 with the pre-model guard on and 10/10
  with it off**. Full traces and normalized proposal payloads are in
  `phase2-regression-20261005T133925/`.
- Phase 3 development set: **20/20** automated checks. Median end-to-end answer
  time was 1.785 s and observed p95 was 3.289 s for this 20-case local run.
- First held-out set: **19/20**. Retrieval found the required evidence in the
  failed case, but the model omitted the required `citation_ids` property twice;
  the application correctly withheld the answer. The schema/prompt was corrected,
  so that set became development evidence and was not relabelled as untouched.
- Fresh held-out-v2 set: **20/20**, with 16/16 retrieval checks containing their
  required evidence. Median end-to-end answer time was 1.698 s and observed p95
  was 2.187 s. Three cases confirmed that embedded instructions reached the
  model context but produced no proposals or household mutations while the
  legitimate storage questions were answered.

The evaluation runner saves corpus hashes, model configuration, raw structured
answers, retrieval candidates, citations, traces, request IDs, field checks,
state snapshots, cleanup outcomes, and failures. Runs refuse to execute against
the normal household database.

## What the results do and do not prove

The development and held-out-v2 results met the plan's local learning targets:
retrieval hit rate exceeded 90%, grounded automated-answer checks exceeded 90%,
citations were structurally valid, missing/conflicting cases followed their
expected behavior, and no injection-induced write occurred.

The corpus is synthetic and small. Many tests use document filters, while the
fresh held-out set includes three unfiltered searches. Required-term matching
and valid citation IDs do not independently prove that every natural-language
claim is semantically entailed. The saved passages and answers remain available
for manual review. The latency numbers are small local samples, not general
benchmarks. OCR, encrypted/image-only PDFs, authentication/authorization,
real-device control, approximate indexes, reranking, and cloud deployment remain
outside Phase 3.

## Learning notes

- RAG is retrieval at request time, not training. `embeddinggemma` creates
  vectors for search; `qwen3:8b` writes the answer from retrieved evidence.
- Source applicability matters as much as similarity. A nearby chunk from the
  wrong appliance model must not become an answer.
- A citation is useful only when the cited passage supports the claim. The
  server can validate citation identity; semantic support still needs evaluation.
- Retrieved documents are untrusted data. Knowledge mode exposes no write tools,
  so document text cannot grant itself authority.
- Durable RAG includes replacement, deletion, retry, and restart behavior, not
  only a successful upload-and-query demo.
- Failure evidence is valuable. The first 19/20 held-out result showed a strict
  contract working safely and exposed a formatting weakness; a genuinely new
  set was used for the final held-out claim.

Phase 3 is complete for the local single-household scope defined in the v3 plan.
The API must remain on trusted local development until authentication,
authorization, and action ownership are implemented.
