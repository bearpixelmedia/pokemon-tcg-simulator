# Pokémon TCG Simulator — System Completeness Map

This map defines the gap between **coverage completeness** (text resolves) and
**system completeness** (engine semantics are explicit, auditable, and testable).

## Current verified baseline

- Text coverage: `100.0%` (`4649/4649`)
- Runtime hook handling: `100.0%` (`1308/1308`) deterministic execution path
- Remaining work is about **semantic explicitness and architecture hardening**
  rather than unresolved text.

---

## Track 1 — Card-identity state model

Goal: represent deck/hand/discard/prizes/attachments as concrete card instances.

Deliverables:
- `core/state_model.py`
- Strongly typed runtime state objects
- Legacy/demo-state adapter
- Serialization helpers for replay and fixtures

Acceptance:
- Runtime state can be built from existing demo state
- Card zones and in-play structures are explicit and serializable

---

## Track 2 — Timing windows and trigger bus

Goal: explicit timing model for “when/whenever/at end of turn/after attack”.

Deliverables:
- `core/timing_windows.py`
- Window enum and event bus
- Handler registration/dispatch contract

Acceptance:
- Window events can be emitted deterministically
- Handlers return stable operation lists

---

## Track 3 — Continuous-effect layer engine

Goal: deterministic layer ordering for passive effects and modifiers.

Deliverables:
- `core/effect_layers.py`
- Layered rule model (hp/type/cost/damage/status/etc.)
- Priority + source-based conflict resolution

Acceptance:
- Same rules + same seed => same resolved modifiers every run

---

## Track 4 — Target legality and selection

Goal: centralized targeting validation for attack/effect selectors.

Deliverables:
- `core/targeting.py`
- Selector validation helpers (`self`, `opponent`, `bench`, `active`, etc.)
- Multi-target legality + error surface

Acceptance:
- Invalid selectors produce deterministic, inspectable failures

---

## Track 5 — Cost payment and rollback

Goal: transactional cost payment with rollback if full payment fails.

Deliverables:
- `core/cost_engine.py`
- Cost transaction class
- Payment steps for hand/energy/discard requirements

Acceptance:
- Partial payment never corrupts state when cost resolution fails

---

## Track 6 — Setup/opening-flow engine

Goal: explicit setup/mulligan/prize setup flow independent from attack runtime.

Deliverables:
- `core/setup_engine.py`
- Opening-state initializer and mulligan simulation
- Prize-zone setup invariants

Acceptance:
- Setup emits deterministic event sequence and valid initial board

---

## Track 7 — Golden regression harness

Goal: scenario-level execution harness for ruling-critical interactions.

Deliverables:
- `core/golden_regression.py`
- Case runner + suite runner
- Snapshot output suitable for CI assertions

Acceptance:
- Golden suite produces stable pass/fail and state snapshots

---

## Track 8 — Full legal-action surface

Goal: richer legal-action generation based on explicit state model + costs.

Deliverables:
- `core/legal_actions_full.py`
- Action objects with legality reasons
- Cost/target checks integrated in action generation

Acceptance:
- Returned actions are reproducible and explainable (`reason` metadata)

---

## One-go implementation order

1. State model
2. Timing windows
3. Effect layers
4. Targeting
5. Cost engine
6. Setup engine
7. Golden regression harness
8. Full legal actions
9. Tests for each track
10. Full test + coverage + quality verification
