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
- `POST /compile_text` -> compile card text into operation DSL
- `GET /blueprints` -> list available variable wording blueprints
- `POST /build_card` -> instantiate blueprint with variables and compile it
