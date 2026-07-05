# Pokémon TCG Full Simulator

Complete modular engine with:
- Status conditions (Poison, Burn, Paralysis, Sleep, Confusion)
- Modular effect system (text -> operation DSL)
- Web dashboard
- Vercel ready

## Architecture

- `core/text_compiler.py`  
  Compiles card wording into normalized operations using reusable text templates.
- `core/card_blueprints.py`  
  Defines variable wording blueprints so one template can generate many card effects.
- `core/effects.py`  
  Applies compiled operations to a simulation state, including ordered replacement/prevention stack resolution and temporary-rule expiry.
- `core/standard_coverage.py`  
  Ingests Standard-legal cards by regulation mark and reports text-template coverage.
- `core/template_mining.py`  
  Clusters unresolved clauses and suggests candidate template patterns.
- `core/yolo_pipeline.py`  
  Runs the sequential YOLO pipeline and writes snapshot artifacts.
- `core/turn_engine.py`  
  Deterministic turn/phase state machine with replay checksums.
- `core/ai_policy.py`  
  Legal action generation and heuristic policy selection for simulation agents.
- `core/rules_mechanics.py`  
  Retreat/evolution/devolution/KO-prize helpers used by the turn engine.
- `core/legality_snapshot.py`  
  Builds Standard legality snapshots with release-date waiting gates and reprint/errata metadata overlays.
- `core/quality_gates.py`  
  Runs replay determinism, coverage regression, legality checks, and emits a coverage dashboard artifact.
- `core/state_model.py`  
  Strongly typed runtime state model with legacy/demo state adapter.
- `core/timing_windows.py`  
  Timing window bus for deterministic trigger dispatch with ordered replacement/prevention/normal handler priority.
- `core/effect_layers.py`  
  Continuous-effect layer resolver for rule stacking and modifier precedence.
- `core/priority_stack_policy.py`  
  Centralized replacement/prevention priority policy and timing-rule ordering helpers used across runtime modules.
- `core/targeting.py`  
  Target legality helpers for selector/count validation.
- `core/cost_engine.py`  
  Transactional cost payment with rollback safety.
- `core/setup_engine.py`  
  Opening/setup phase engine (hand/prize invariants and mulligan flow).
- `core/golden_regression.py`  
  Golden-case regression harness for scenario-level semantic checks.
- `core/legal_actions_full.py`  
  Expanded legal-action surface with reasoned legality metadata.
- `core/trainer_lifecycle.py`  
  Enforces trainer lifecycle constraints (Supporter/Stadium/Tool limits by turn and board legality).
- `core/reprint_errata.py`  
  Applies named-card reprint and errata overlays used by legality snapshots.
- `core/data_pipeline.py`  
  Pipeline reliability + schema drift checks with artifact snapshot export.
- `core/unresolved_registry.py`  
  Runtime registry for unresolved text clauses seen by the compiler.
- `core/script_fallbacks.py`  
  Controlled script-hook fallbacks for complex unresolved clause families.
- `sim/game.py`  
  Runs AI vs AI simulations using blueprint-generated card text.
- `templates/dashboard.html`  
  UI for simulation, text compilation, and blueprint testing.

## Run locally
```bash
pip install -r requirements.txt
python3 app.py
```

Then open http://127.0.0.1:5000

## API endpoints

- `POST /run_sim` -> run AI vs AI demo simulation
- `POST /run_sim/verify_replay` -> run deterministic replay consistency check
- `POST /run_sim/batch` -> run many simulations and aggregate win/turn metrics
- `POST /compile_text` -> compile card text into operation DSL
- `GET /blueprints` -> list available variable wording blueprints
- `POST /build_card` -> instantiate blueprint with variables and compile it
- `POST /coverage/analyze` -> run Standard card text coverage analysis
- `POST /coverage/recommend_templates` -> mine unresolved clauses into template candidates
- `GET /coverage/unresolved_registry` -> inspect unresolved compiler registry
- `POST /coverage/unresolved_registry/clear` -> clear unresolved registry
- `POST /yolo/run` -> execute coverage + mining + snapshot export in one pass
- `POST /legality/snapshot` -> build legality snapshot with release-date waiting rule
- `POST /quality/gates` -> run quality gates and optional baseline update
- `POST /data/pipeline/health` -> run ingest reliability and schema drift checks

## YOLO run artifacts

Running `/yolo/run` writes JSON artifacts under:

- `/workspace/artifacts/yolo/coverage_latest.json`
- `/workspace/artifacts/yolo/mining_latest.json`
- `/workspace/artifacts/yolo/yolo_latest.json`
- plus timestamped history snapshots

## CI quality and ingest checks

- GitHub Actions workflow: `.github/workflows/quality-gates.yml`
  - Runs unit tests
  - Fails PRs on quality gate regressions
  - Runs scheduled ingest health checks
  - Uploads coverage + pipeline artifacts (`artifacts/quality`, `artifacts/pipeline`)
