# Implementation Patch Post-Validation

`validate_implementation_patch.py` is the deterministic boundary after a
candidate-ready implementation result. It revalidates that exact result,
generates a complete Git patch from the declared workspace and base commit,
applies diff policy, classifies supervision risk, and writes one external
receipt.

It does not invoke an agent, run Gradle, approve the patch, authorize
publication, create a branch, commit, push, or open a pull request.

## Run

The result and expected-session files must be external evidence. The patch and
receipt paths must be absent, distinct, and outside both the source checkout
and implementation workspace:

```text
python .agent/checks/validate_implementation_patch.py \
  --repo <trusted-source-checkout> \
  --result <external-path>/result.json \
  --expected-session <external-path>/expected-session.json \
  --patch-output <external-absent-path>/patch.diff \
  --receipt-output <external-absent-path>/patch-validation.json \
  --format json
```

An optional `--stderr` file must be empty. As with the standalone result CLI,
this manual form cannot prove the files came from a real runner. A future
runner must pass its actual bounded execution record to `validate_patch(...)`.

## Outcomes

`post_validation_complete=true` means the result was candidate-ready and the
complete patch was generated, evaluated, and classified under the exact bound
policies.

`patch_candidate_ready=true` additionally requires the patch to be retained
and allowed by diff policy, and to contain at least one changed file and one
byte. A policy-blocked or empty patch may still produce a receipt and remain
auditable, but it is never candidate-ready. Classification cannot override a
policy block.

The receipt binds:

- the exact implementation session identity and result digest;
- patch path, digest, size, facts, policy decision, and violations;
- whether the patch is nonempty for candidate-readiness purposes;
- deterministic risk, route, and required human gates;
- the still-pending quality-gate state;
- trusted tool and policy bytes.

If any post-generation step fails, both output paths are removed. This is safe
because the contract requires them to be absent before the operation.

## Proof

```text
python .agent/checks/prove_implementation_patch_validation.py \
  --repo . \
  --format json
```

The proof creates disposable local Git repositories and verifies:

- an allowed complete patch becomes candidate-ready;
- a protected-path patch is retained but policy-blocked and routed to `C`;
- an empty patch remains auditable but cannot become candidate-ready;
- an invalid implementation result creates neither patch nor receipt.

## Honest Boundary

This satisfies only `implementation_patch_post_validation`. The quality gate is
explicitly recorded as required, incomplete, and not passed. Kotlin tests,
lint, Detekt, and `verifyPlugin` still need a later controlled execution
boundary.

`runner_enforced_output_post_validation` also remains unproven until a real
runner atomically connects its captured result to this gate. A complete receipt
is current-state evidence, not approval or permission to publish. Its
independent current-state consumer is documented in
`implementation-patch-post-validation-validation.md`; that validator still
does not prove historical production or runner enforcement.
