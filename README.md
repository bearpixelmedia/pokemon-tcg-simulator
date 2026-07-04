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
  Applies compiled operations to a simulation state.
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
  Builds Standard legality snapshots with release-date waiting gates.
- `core/quality_gates.py`  
  Runs replay determinism, coverage regression, and legality checks.
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

## YOLO run artifacts

Running `/yolo/run` writes JSON artifacts under:

- `/workspace/artifacts/yolo/coverage_latest.json`
- `/workspace/artifacts/yolo/mining_latest.json`
- `/workspace/artifacts/yolo/yolo_latest.json`
- plus timestamped history snapshots
