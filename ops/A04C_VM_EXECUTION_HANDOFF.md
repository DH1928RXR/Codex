# EOR A04C — VM Execution Handoff

## Authority and current checkpoint

This is a bounded execution handoff for the existing EOR autonomy campaign. Do **not** design a replacement system.

Active operational authority: Google Drive document `1EOSUL6gmhxdMMQNQ4T4HThZPDcPjIDeqyHgEYh7h8GE` — **EOR — Luna Master Execution Contract — Autonomy Stack Completion**. Re-read it before execution if available and reconcile any newer receipts. Its current corrected stage is:

`CURRENT_STAGE=A04C_ACTUATOR_REBIND`

A04P is already PRELIVE PASS and must not be repeated. Receipt: Drive `1vW-sDgv56-Chl9n3xwWEC3GSyttIdv5Y`.

Frozen A04P facts:
- bridge source SHA-256 `0642063e7570da5ccae9cbec8b62595c2e1f4e7105199783d4873b555898abe`
- prelive tests `21/21`
- qualification task state `READY`
- persist-before-effect PASS
- restart reread PASS
- duplicate suppression PASS
- production mutation false

The prior A04P receipt's `H4_PLATFORM_BOUNDARY` classification is **superseded**. Same-host L1-002/L4-016 evidence already proved the required on-demand Codex App-Server carrier.

## Exact certified actuator lineage to reuse

Host: `eor-g000-supervisor`

Historical certified R4 source:
- path: `/home/danhebb/luna2/codex_app_server_runner_r4.py`
- SHA-256: `db65aaf6c985bff29bfdcab54aa8ed8e30d4321da53c6044fd74c295eec4cfcd`

Historical certified Codex carrier:
- binary: `/home/danhebb/.local/bin/codex`
- certified historical SHA-256: `bbc3341e44c9ead340ed9570c17be936e37870f570751a941699ffd04d672827`
- certified version: `codex-cli 0.149.0`
- invocation: `codex app-server --stdio`
- schema invocation: `codex app-server generate-json-schema --out <fresh /tmp directory>`
- `CODEX_HOME=/home/danhebb/.codex`
- auth mode: ChatGPT/file-backed machine-local auth; never print/read secret contents
- fixed model profile: `gpt-5.6-luna`
- config: `approvalPolicy=never`, `sandbox=readOnly`, `networkAccess=false`, `ephemeral=true`
- historical proof workspace: `/tmp/luna1-appserver-proof`
- proven same-thread continuity: thread `01a039a9-c94f-7e63-b5be-631847566fd0`
- historical transcript SHA-256: `efbf3c3d16829a346e4bbd48634955f99e558c95237e188cdf22c1796d042352`

App-Server is an on-demand **stdio subprocess**, not a required network daemon or permanently exposed endpoint.

## Governing construction rule

**LOOKUP BEFORE BUILD.** Reuse existing exact artifacts and verified primitives. No new capability may be built when an existing verified capability performs that part of the work.

Do **not** create:
- another controller or scheduler
- another queue/checkpoint/receipt/replay protocol
- another App-Server client
- a generic process/shell API
- a dedicated R15 daemon
- a browser-driver dependency
- an alternate model/provider transport

C remains controller owner. R15 is the worker-effect composition. R4/App-Server is the certified model actuator.

## Required execution

1. **Reconcile current host state** on `eor-g000-supervisor`.
   - Verify `/home/danhebb/.local/bin/codex` existence, current SHA-256 and version.
   - Verify `app-server` and JSON-schema support.
   - Check `/home/danhebb/.codex` only for presence/usability of already-authorized machine-local auth. Do not output secret contents.
   - Reconcile the A04P bridge/package and current durable task/worker/checkpoint stores.
   - If newer authority-grade receipts have advanced A04C, continue from the earliest not-yet-proven stage instead of repeating work.

2. **Rebind exact R4**.
   - Re-hash `/home/danhebb/luna2/codex_app_server_runner_r4.py`.
   - If that historical path is absent, locate the frozen/certified exact R4 artifact/evidence and stage those **exact bytes** into the existing A04P package.
   - Do not reconstruct a new protocol implementation.

3. **Close the smallest actuator seam** inside the existing A04P bridge.
   - Spawn the verified Codex binary as `codex app-server --stdio`.
   - Consume the certified R4 protocol implementation.
   - Keep the fixed Luna profile/config above.
   - Capture the JSON-RPC lifecycle/terminal evidence and return it to the already-qualified durable R15/C bridge.

4. **Zero-model-activation carrier preflight first**.
   Prove, without `thread/start` or `turn/start`:
   - binary/path/version/hash binding
   - schema/protocol compatibility
   - stdio process spawn
   - initialize -> initialized lifecycle
   - auth availability
   - fixed workspace/model/config binding
   - clean termination

   Persist `A04C_ACTUATOR_BIND_READY=true` only if this exact preflight passes. If current version/path drifted but supported App-Server remains available, perform only the narrow compatibility qualification needed; ordinary drift is local repair, not H4.

5. **Execute exactly one harmless A04 live task** after the preflight passes.
   - Use the already-materialized durable READY qualification task if still exact and unambiguous; otherwise reconcile before any replay.
   - Requested work is response-only and harmless; expected sentinel should remain `EOR_A04_WORKER_OK` if that is the frozen task contract.
   - Required lineage: C durable state -> R15 READY/CLAIMED/attempt -> compiled prompt -> exactly one R4/App-Server activation -> terminal event/journal -> telemetry -> receipt -> task COMPLETE -> worker DORMANT -> C evaluation -> restart-safe DECIDED checkpoint/next decision.

6. **Zero-replay reconstruction proof**.
   Reconstruct/re-run over the same durable state and require:
   - model activation delta `0`
   - no duplicate receipt
   - no duplicate telemetry
   - no replay of completed effect

7. Persist a bounded machine-readable A04/A04C receipt containing exact paths/hashes, thread/turn IDs, activation accounting, task/worker/attempt/checkpoint identities, terminal/receipt/evaluation lineage, and reconstruction result.

8. On PASS, **continue immediately to A05** and then keep following the Master Execution Contract. Do not stop merely to report a local pass/fail or ask Dan/Sol for routine routing.

## Fail/stop policy

Missing path, version drift, package/import/config gap, ordinary permission defect inside the already-authorized VM/project surface, or deterministic test failure is local engineering work: repair the smallest monotonic seam, test it, persist evidence, and continue.

Return only for the Master Contract's genuine H1-H4 hard stops or mission completion. In particular:
- H1 only if machine-local supported auth cannot be recovered and interactive login/MFA/account authorization is truly required.
- H4 only if the current host lacks any usable App-Server mechanism **and** the previously certified carrier cannot be restored/rebound without materially different architecture.

## Environment boundary for this Codex invocation

First determine whether this Codex task actually has access to `eor-g000-supervisor` / the existing EOR VM execution environment. If yes, execute the bounded work above. If this Codex environment is cloud-only and cannot reach the existing VM, **do not substitute a cloud simulation or build a new control plane**. Report the exact unreachable-VM boundary and preserve this handoff for a Codex invocation that has the existing machine actuator.
