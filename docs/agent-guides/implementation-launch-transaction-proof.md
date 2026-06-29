# Implementation Launch Transaction Proof

`prove_implementation_launch_transaction.py` exercises one synthetic local
claim-before-spawn mechanism. It creates an exclusive claim bound to a harmless
marker digest, then starts one isolated Python child through
`isolated_process.py`. A replay is rejected before another child can start.

The result is fixture evidence only. It does not use a real authorization
chain, invoke Codex, provide crash atomicity, prevent cross-host replay, or
prove the required authorization-consumption-to-process-start control.
