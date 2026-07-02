# Deterministic Read-Only Stage Output Validation

`validate_stage_output.py` validates one raw response captured from a future
read-only adapter. It never executes a model and never copies the response into
the workflow run.

The validator treats both the bundle and response as untrusted. It verifies:

- the bundle SHA-256 expected from the trusted context-building step before
  parsing its JSON;
- exact bundle schema, source order, sizes, digests, safety metadata, task
  metadata, and the current repository prompt content;
- external regular-file inputs rather than checkout paths or symbolic links;
- a UTF-8 response no larger than 20,000 bytes;
- no high-confidence secret signature;
- exactly the expected artifact identity, frontmatter, sections, issue, base
  commit, and stage-specific status;
- no unresolved placeholders or conversational preamble.

Research may return only `complete` or `blocked`. Planning may return only
`awaiting_approval` or `blocked`; it can never self-approve. Compaction may
return `in_progress`, `complete`, or `blocked`. Review may return only
`complete` or `blocked`.

## Run

Pass the SHA-256 reported separately by `build_stage_context.py`:

```text
python .agent/checks/validate_stage_output.py \
  --repo . \
  --bundle <external-path>/research-context.json \
  --bundle-sha256 <trusted-builder-sha256> \
  --response <external-path>/captured-response.md \
  --format json
```

Exit code `0` means the response is structurally accepted, `2` means validation
failed, and `1` means a tool, input, or policy error. An accepted result reports
`accepted=true` and still always reports `authorized=false`.

## Trust Boundary And Limits

The expected bundle digest must be carried separately from a trusted invocation
of the context builder. A digest supplied by the same untrusted producer as a
tampered bundle is not a trust anchor.

Version-3 bundles carry provenance metadata from context preparation. Research
bundles contain the task-approval receipt SHA-256; plan bundles contain the
stage-application receipt SHA-256 for the applied research. The response
validator checks this provenance record's schema, and the separately carried
bundle digest binds the response to it. The response validator does not
independently reopen those receipts.

Structural acceptance does not prove that research claims are true, that a plan
is good, or that a human approved anything. The validator does not mutate run
artifacts, advance statuses, execute checks, or authorize later stages. A later
operator-confirmed step may copy an accepted artifact only after its own
explicit checks.

`docs/agent-guides/manual-read-only-adapter.md` documents the limited manual
adapter that composes context building and response validation while preserving
these boundaries.
`docs/agent-guides/stage-application.md` documents the separate, explicitly
mutating copy step and its limits.
