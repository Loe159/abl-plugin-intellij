# High-Confidence Secret Check

The local diff policy scans added patch lines for a deliberately small set of
high-confidence credential signatures. It is deterministic, uses only the
Python standard library, and runs automatically whenever `diff_policy.py` or
`generate_complete_patch.py` evaluates a patch.

## Current Signatures

The repository policy currently identifies:

- private-key PEM headers;
- GitHub tokens;
- AWS access-key IDs;
- Google API keys.

Signatures are configured as named regular expressions in
`.agent/policies/diff-policy.json`. The validator reports only the affected path
and signature ID. It never includes the matching line or credential value in
text or JSON diagnostics.

## Artifact Handling

Ordinary policy-blocked patches remain available for human review. A patch with
a `high_confidence_secret` violation is different:

- the requested output artifact is not written;
- content/base application checks stop immediately after the secret violation;
- patch bytes remain in process memory only and are not written by the generator;
- `artifact.retained` is `false`;
- the result may include the requested path, digest, and size, but never the
  matching value.

## Deliberate Limits

This is not a replacement for Gitleaks, provider-side push protection, secret
rotation, or least-privilege credential handling. It scans added patch lines
only and intentionally omits generic password assignments, entropy heuristics,
and repository-history scanning because those approaches require broader
fixtures and false-positive handling.

Removing a detected secret is allowed. A detected credential must still be
treated as compromised and rotated; blocking a patch does not make it safe
again. Because secret detection fails closed before content/base application
checks, a secret-blocked result does not claim that the patch is otherwise
complete or applicable.
