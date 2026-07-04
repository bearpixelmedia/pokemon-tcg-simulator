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
- `POST /compile_text` -> compile card text into operation DSL
- `GET /blueprints` -> list available variable wording blueprints
- `POST /build_card` -> instantiate blueprint with variables and compile it
- `POST /coverage/analyze` -> run Standard card text coverage analysis
- `POST /coverage/recommend_templates` -> mine unresolved clauses into template candidates
- `POST /yolo/run` -> execute coverage + mining + snapshot export in one pass

## YOLO run artifacts

Running `/yolo/run` writes JSON artifacts under:

- `/workspace/artifacts/yolo/coverage_latest.json`
- `/workspace/artifacts/yolo/mining_latest.json`
- `/workspace/artifacts/yolo/yolo_latest.json`
- plus timestamped history snapshots
