# Implementation Launch Readiness

`check_implementation_launch_readiness.py` is the last read-only check after
local authorization consumption. It requires both current invocation readiness
and an independently valid consumption marker.

The CLI accepts the complete proposal, workspace, approval, preflight,
authorization, and consumption-marker chain with separately carried SHA-256
values. Exit code `0` means `launch_ready=true`, `2` means a deterministic gate
blocked readiness, and `1` means an input, policy, or runtime error.

## Honest Boundary

`launch_ready=true` does not select a runner, authorize invocation, start a
process, enforce network isolation, or couple the marker atomically to process
creation. It only proves that the pre-consumption and post-consumption evidence
agree at the time of this read-only check.

The bounded synthetic next step is documented in
`docs/agent-guides/implementation-launch-transaction-proof.md`.
