# Pokémon TCG Simulator — YOLO Master Plan (Full Coverage Path)

This plan describes *everything needed* to reach deterministic, test-backed, data-driven coverage for all Standard-legal cards.

## Mission

Build a modular engine where card wording compiles into reusable operations, with measurable coverage and an iterative path to 100% Standard support.

---

## Phase 0 — Infrastructure Baseline (completed)

- [x] Modular engine packages (`core/`, `sim/`, `templates/`)
- [x] Text compiler (`text -> EffectProgram`)
- [x] Variable blueprints (`template + variables -> card text`)
- [x] Effect operation executor (demo runtime)
- [x] Flask API + dashboard controls for compile/build/simulate
- [x] Standard coverage analyzer (H/I/J ingestion + coverage metrics)

Exit criteria:
- Compiler resolves known templates
- Coverage endpoint returns stable metrics
- Dashboard can run compile and coverage operations

---

## Phase 1 — YOLO Automation Pass (executing now)

Goal: run all core analysis actions sequentially in one command/API flow.

### 1.1 Sequential pipeline runner
- [x] Add orchestrator: `coverage baseline -> unresolved mining -> snapshot export`
- [x] Support configurable scope (`marks`, `limit`, `force_refresh`)
- [x] Return machine-readable report and saved artifact paths

### 1.2 Unresolved-clause mining
- [x] Normalize unresolved text
- [x] Cluster by shape/signature
- [x] Suggest candidate template forms with placeholders
- [x] Prioritize by frequency

### 1.3 Coverage artifacts/history
- [x] Persist latest run summary and recommended templates
- [x] Persist timestamped snapshots for progress comparison
- [x] Include reproducible metadata

Exit criteria:
- A single YOLO API call runs all stages and returns actionable outputs

---

## Phase 2 — Rules Engine Fidelity

### 2.1 Turn-state correctness
- [x] Full phase/state machine
- [x] Turn windows and operation ordering
- [x] Deterministic RNG and replayability

### 2.2 Rule mechanics
- [x] Full Special Conditions semantics
- [x] Attach/pay energy costs
- [x] Retreat/evolution/devolution rules
- [x] KO/prize/checkup correctness
- [x] Trainer lifecycle and legality restrictions
- [x] Replacement and prevention effects timing

Exit criteria:
- Deterministic replay tests for core flow pass

---

## Phase 3 — Text Coverage Expansion System

### 3.1 Template library growth
- [x] Add high-frequency unresolved patterns from mining
- [x] Add parameterized handlers for common “if/choose/up to” variants
- [x] Add composition support for multi-clause effects

### 3.2 Controlled fallbacks
- [x] Mark unsupported clauses with explicit reason
- [x] Add optional script hooks only for outliers
- [x] Keep unresolved registry queryable

Exit criteria:
- Coverage trend moves upward each template sprint

---

## Phase 4 — Legality and Card Data Governance

### 4.1 Legality model
- [x] Regulation marks + release gates
- [x] Reprint/errata handling model
- [x] Snapshot by date/season

### 4.2 Data pipeline
- [x] Scheduled ingest
- [x] Schema drift checks
- [x] Source reliability checks

Exit criteria:
- Standard pool snapshot is reproducible and auditable

---

## Phase 5 — Verification and Confidence

### 5.1 Tests
- [x] Unit tests per operation
- [x] Unit tests per template family
- [x] Regression fixtures for known interactions
- [x] Replay equivalence tests (seeded)

### 5.2 Quality gates
- [x] CI fails on coverage regressions
- [x] CI fails on legality snapshot mismatches
- [x] Coverage dashboard published as build artifact

Exit criteria:
- No silent behavior regressions

---

## Phase 6 — AI Simulation Layer

- [x] Legal action generator
- [x] Heuristic bot policies
- [x] Batch simulation runner
- [x] Strategy/performance telemetry

Exit criteria:
- Sim output is legal, deterministic, and measurable

---

## 100% Definition of Done

All of the following must be true:

1. Every Standard-legal card text block has a resolved behavior path (template or controlled scripted fallback).
2. Rule-engine conformance tests pass for critical mechanics and known edge cases.
3. Coverage dashboard reports 100% resolved text blocks for current legality snapshot.
4. Replay determinism and regression suite are green.
5. Legality snapshoting is automated and reproducible.

---

## Execution notes

- “One go” implementation can deliver major architecture and automation milestones.
- Final 100% requires iterative template/ruling verification loops by design.

---

## Phase 7 — Semantic De-genericization (completed)

Goal: replace generic fallback semantics with explicit subsystem contracts.

- [x] Track map created (`SYSTEM_COMPLETENESS_MAP.md`)
- [x] Card-identity runtime model module (`core/state_model.py`)
- [x] Timing window dispatcher module (`core/timing_windows.py`)
- [x] Continuous-layer conflict resolver module (`core/effect_layers.py`)
- [x] Target legality validator module (`core/targeting.py`)
- [x] Cost payment + rollback transaction module (`core/cost_engine.py`)
- [x] Setup/opening flow module (`core/setup_engine.py`)
- [x] Golden ruling harness module (`core/golden_regression.py`)
- [x] Full-surface legal action generator module (`core/legal_actions_full.py`)

Exit criteria:
- New semantic modules are test-covered and integrated in repository docs.

---

## Phase 8 — Core Hardening Verification (completed)

- [x] Added dedicated tests for all new hardening modules
- [x] Full unit suite passes
- [x] Quality gates and data pipeline health checks pass
- [x] Wired timing windows into live turn/effect runtime
- [x] Wired setup/mulligan flow into turn simulation bootstrap
- [x] Wired full legal-action metadata into AI action selection
- [x] Wired continuous-rule storage/layered damage modifiers into effect execution
- [x] Wired golden regression suite into quality-gate execution
- [x] Added replacement/prevention priority stack semantics for deterministic damage resolution
- [x] Added turn-end expiry for temporary continuous/stack/timing rules
- [x] Externalized precedence policy into dedicated stack-policy module (config-driven ordering helpers)

Exit criteria:
- No regressions in deterministic replay and text/runtime coverage guarantees.
