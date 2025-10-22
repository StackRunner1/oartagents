## Partial reads and partial upserts — platform-agnostic patterns for agentic systems

Date: 2025-10-21 Status: Design guideline for main application

This document specifies contracts and patterns for “partial reads” (fetch a
range within a resource) and “partial upserts” (insert/replace/append content at
a specific position within an existing resource). It is intentionally
platform-agnostic so it can be implemented against local files, object storage,
relational/NoSQL databases, and vector/RAG backends.

---

## Core goals

- Efficiency: minimize IO, token usage, and latency by targeting only the needed
  region.
- Determinism: bound reads/writes precisely by indices; preserve invariants
  (encoding, newline, schema).
- Observability: every operation carries a precise “what/where/why” record
  (range, version, actor).
- Safety: strict bounds checking, preconditions (version/ETag), and role/ACL
  checks.

---

## Terminology

- Resource: file/blob/row/document the agent reads or writes.
- Range units: lines, bytes, tokens, JSON-path segments, or domain sections
  (e.g., headings/paragraphs).
- Locator: how we address a resource (path/URL, DB key, collection + id,
  JSONPath, etc.).

---

## Contracts

### 1) Partial Read

Request

- resource_id: string (opaque to caller but resolvable by the system)
- locator: { path | url | db: { table/collection, id/key }, json_path?,
  vector_id? }
- range: { start: number, end: number, units: 'lines' | 'bytes' | 'tokens' |
  'jsonpath' | 'sections' }
- projection?: string[] (columns/fields to include when applicable)
- max_bytes?: number (upper bound to avoid over-fetch)
- encoding?: 'utf-8' | 'utf-16' | ...

Response

- snippet: string | object (depending on resource)
- range: { start, end, units }
- version: { etag?: string, sha256?: string, lsn?: string, updated_at?: string }
- content_type?: string
- source: 'file' | 'object-storage' | 'db' | 'vector-store'
- recommended_prompts?: string[] (optional next actions)

Error modes

- out_of_bounds, not_found, precondition_required, too_large, permission_denied,
  encoding_mismatch.

### 2) Partial Upsert

Request

- resource_id, locator (as above)
- target:
  - insert: { at: number, units }
  - replace: { start: number, end: number, units }
  - append: { at_end: true }
- content: string | object (payload to merge/insert)
- mode: 'insert' | 'replace' | 'append'
- preconditions?: { if_match_etag?: string, if_not_modified_since?: string,
  expected_sha256?: string }
- transform?: { formatter?: 'md' | 'json' | 'sql', normalize_newlines?: boolean
  }

Response

- range_after?: { start, end, units }
- version_after: { etag?: string, sha256?: string, lsn?: string, updated_at?:
  string }
- affected: { bytes?: number, lines?: number, fields?: string[] }
- preview?: string | object (small diff/summary)

Error modes

- precondition_failed (version mismatch), invalid_range, schema_violation,
  permission_denied.

---

## Implementation patterns by backend

### A) Local files

- Reads: small files → read/split/slice; large files → line→byte index
  (seek+read). Handle CRLF vs LF. Compute sha256 for versioning.
- Upserts: acquire file lock; apply insert/replace/append by bytes or lines;
  preserve encoding and newline style; write atomically (temp file + rename).
- Observability: log path, range, sha256_before/after.

### B) Object storage (S3/GCS/Azure Blob/Supabase Storage)

- Reads: Range GET (bytes=start-end). Maintain a line/section index in a
  metadata store to translate logical (lines/tokens) to bytes.
- Upserts: object stores don’t support “write range” natively. Options:
  1. Read-around compose: GET byte ranges around the insertion, assemble new
     object server-side, PUT new version; use ETag preconditions.
  2. Server function: invoke a backend service that performs the compose near
     data.
- Indexing: maintain per-object indexes (lines/sections/tokens) and invalidate
  after writes.
- Security: signed URLs, short TTL, bucket ACLs.

### C) Relational databases (Postgres, MySQL)

- Reads: project specific columns; for text blobs use substring for byte/char
  ranges; for JSON use JSONPath selectors; return version via
  xmin/LSN/updated_at.
- Upserts: prefer field-level updates over monolithic text; for text, apply
  substring-based splice with WHERE version=expected to ensure optimistic
  concurrency; return updated snippet via RETURNING.
- Indexing: if doing line/section addressing for documents, maintain a mapping
  table (doc_id, line_no, byte_start, byte_end) and recompute on change.

### D) Document stores (Mongo/Firestore)

- Reads: field projection + dot-path; for large bodies store segments
  (paragraphs/sections) as separate docs.
- Upserts: atomic updates with $push/$set/$setOnInsert as appropriate; validate
  schema via JSON Schema.

### E) Vector stores and RAG

- Reads: retrieve chunks with metadata that includes { file_path,
  byte/line/tokens range }.
- Upserts: append/replace chunk content and re-embed; keep chunk boundaries
  aligned with your addressing scheme to make follow-up partial reads trivial.

---

## Indexing strategies

- Line/byte index: array of byte offsets for each newline (fast, simple).
- Token index: useful for LLM-bounded operations (maintain with the tokenizer
  used upstream).
- Structural index: headings/sections/AST nodes for semantic inserts.
- Invalidation: after any upsert, recompute or lazily update affected ranges
  only.

---

## Observability, governance, and safety

- Log read_range / upsert_range with: actor, resource_id, locator, range,
  version_before/after, bytes read/written, reason.
- Enforce guardrails: maximum range window, total bytes, allowed resource
  patterns, read-only contexts.
- Apply ACLs/RLS or signed URL policies; always prefer least privilege.
- Redaction: ensure snippets returned to agents exclude secrets/PII based on
  policy.

---

## Performance & scaling

- Batch and cache line/section indexes.
- Coalesce adjacent reads; prefetch small next/prev windows.
- Use optimistic concurrency to avoid locking contention; fall back to retries
  with exponential backoff.

---

## Error handling patterns

- Out-of-bounds → clamp or error depending on policy.
- Precondition failed → return version details and advisory next steps.
- Encoding mismatch → normalize or reject with clear instructions.
- Partial failure in upsert → rollback and return a recovery suggestion.

---

## Frontend UX suggestions

- Partial read: “Show next/prev N lines” chips; “Open definition here”;
  copy-link to exact range.
- Partial upsert: inline diff preview; undo/redo; guarded confirmation for
  replace.

---

## Rollout plan (phased)

1. Read-only (low risk)
   - Implement Partial Read for key resources; add logging and guardrails.
2. Append-only
   - Safe writes that only add content at the end or after known markers.
3. Insert/Replace
   - Enable precise inserts/replacements with optimistic concurrency and diff
     previews.
4. Advanced addressing
   - Token/section addressing; cross-resource operations; background
     re-indexing.

---

## Test matrix (minimum)

- Boundaries: start=1, end=start, end>file, negative indices → clamp/error.
- Encodings: UTF-8/UTF-16; CRLF vs LF; binary detection.
- Concurrency: two upserts with same precondition; verify one succeeds, one
  fails.
- Size limits: large requests rejected cleanly; advisory prompts returned.
- RAG: retrieved chunk + contextual expansion calls Partial Read for adjacent
  ranges.

---

## Acceptance criteria

- APIs implement the contracts above for both reads and upserts.
- All operations are audit-logged with resource, range, and version metadata.
- Guardrails enforce maximum window and authorized resources.
- For upserts, precondition/version checks are mandatory.

---

## Implementation checklist

- [ ] Define canonical request/response types for Partial Read and Partial
      Upsert.
- [ ] Choose addressing schemes per backend (lines/bytes/tokens/sections).
- [ ] Implement line/section indexers where needed; plan invalidation.
- [ ] Add optimistic concurrency (ETag/sha/xmin/updated_at) to writes.
- [ ] Add logging/telemetry with stable event names and fields.
- [ ] Write boundary & concurrency tests.
- [ ] Integrate FE affordances (next/prev N lines, diff preview, undo).
