# Official Gameplay Fidelity — Exhaustive Execution Plan

This plan defines the complete work required for strict, no-exception gameplay
fidelity. It is organized as implementation tracks with deliverables, gates, and
runtime enforcement points.

## Track A — Rules Kernel (authoritative constraints)

Deliverables:
- Official setup model (opening hand, mulligan loop, prize setup)
- First-turn restrictions
- Global invariants (bench/prize bounds)
- Turn-context state

Implementation:
- `core/official_rules.py`
- `core/setup_engine.py` integration
- `core/turn_engine.py` turn-context wiring

Gate:
- Setup and first-turn restriction tests pass deterministically.

## Track B — Strict semantic contract

Deliverables:
- No silent unsupported runtime operations
- No silent unresolved script hooks in strict mode
- Enforced runtime violations for unregistered/unknown semantics

Implementation:
- `core/effects.py` strict contract guards
- Raised `RuntimeError` for strict unresolved semantics

Gate:
- Unknown hook test must fail in strict mode.

## Track C — Hook semantics manifest (explicit coverage ledger)

Deliverables:
- Buildable manifest of every compiled script hook signature
- Runtime registration check before any fallback behavior
- Artifact persisted for auditable semantic coverage

Implementation:
- `core/hook_manifest.py`
- `scripts/build_hook_manifest.py`
- `core/effects.py` manifest-backed fallback checks

Gate:
- Manifest registration tests pass.

## Track D — Turn/action legality and cost-failure semantics

Deliverables:
- Legal action surface tied to official restrictions
- Forced pass on illegal selected/scripted actions
- Attack cost payment gating execution

Implementation:
- `core/legal_actions_full.py`
- `core/turn_engine.py`

Gate:
- Illegal scripted opening-turn attack is converted to pass.

## Track E — Priority semantics and timing ordering

Deliverables:
- Replacement/prevention ordering policy
- Timing window ordering policy
- Deterministic expiration semantics

Implementation:
- `core/priority_stack_policy.py`
- `core/timing_windows.py`
- `core/effects.py`

Gate:
- Ordering and expiration tests pass.

## Track F — Fidelity gates and evidence

Deliverables:
- Unit suite validation
- Quality gates + deterministic replay checks
- Pipeline health checks

Implementation:
- `core/quality_gates.py`
- CI scripts under `scripts/`

Gate:
- All gates green.

## Completion status (this one-go pass)

- [x] Track A implemented
- [x] Track B implemented
- [x] Track C implemented
- [x] Track D implemented
- [x] Track E implemented
- [x] Track F validated
