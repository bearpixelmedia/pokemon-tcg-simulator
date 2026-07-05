from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from core.card_blueprints import list_blueprints
from core.unresolved_registry import clear_unresolved_registry, snapshot_unresolved_registry
from sim.game import (
    analyze_card_text,
    analyze_standard_coverage,
    analyze_template_recommendations,
    build_blueprint_card,
    build_legality_snapshot,
    run_data_pipeline_health,
    run_fidelity_audit,
    run_batch_simulations,
    run_full_yolo_pass,
    run_quality_gate_checks,
    run_simulation,
    verify_simulation_replay,
)

app = Flask(__name__)

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/run_sim', methods=['POST'])
def run_sim():
    payload = request.get_json(silent=True) or {}
    turn_limit = payload.get("turn_limit", 10)
    seed = payload.get("seed")

    try:
        turn_limit = int(turn_limit)
    except (TypeError, ValueError):
        return jsonify({"error": "turn_limit must be an integer."}), 400

    if seed is not None:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            return jsonify({"error": "seed must be an integer or null."}), 400

    return jsonify(run_simulation(turn_limit=turn_limit, seed=seed))


@app.route('/run_sim/verify_replay', methods=['POST'])
def run_sim_verify_replay():
    payload = request.get_json(silent=True) or {}
    turn_limit = payload.get("turn_limit", 10)
    seed = payload.get("seed")

    try:
        turn_limit = int(turn_limit)
    except (TypeError, ValueError):
        return jsonify({"error": "turn_limit must be an integer."}), 400

    if seed is not None:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            return jsonify({"error": "seed must be an integer or null."}), 400

    return jsonify(verify_simulation_replay(turn_limit=turn_limit, seed=seed))


@app.route('/run_sim/batch', methods=['POST'])
def run_sim_batch():
    payload = request.get_json(silent=True) or {}
    games = payload.get("games", 20)
    turn_limit = payload.get("turn_limit", 10)
    base_seed = payload.get("base_seed")

    try:
        games = int(games)
        turn_limit = int(turn_limit)
    except (TypeError, ValueError):
        return jsonify({"error": "games and turn_limit must be integers."}), 400

    if base_seed is not None:
        try:
            base_seed = int(base_seed)
        except (TypeError, ValueError):
            return jsonify({"error": "base_seed must be an integer or null."}), 400

    return jsonify(run_batch_simulations(games=games, turn_limit=turn_limit, base_seed=base_seed))


@app.route('/compile_text', methods=['POST'])
def compile_text():
    payload = request.get_json(silent=True) or {}
    text = payload.get("text", "")
    return jsonify(analyze_card_text(text))


@app.route('/blueprints', methods=['GET'])
def blueprints():
    return jsonify({"blueprints": list_blueprints()})


@app.route('/build_card', methods=['POST'])
def build_card():
    payload = request.get_json(silent=True) or {}
    blueprint_key = payload.get("blueprint_key", "")
    variables = payload.get("variables", {})

    try:
        built_card = build_blueprint_card(blueprint_key, variables)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    return jsonify(built_card)


@app.route('/coverage/analyze', methods=['POST'])
def coverage_analyze():
    payload = request.get_json(silent=True) or {}
    limit_cards = payload.get("limit_cards", 250)
    include_examples = bool(payload.get("include_examples", True))
    force_refresh = bool(payload.get("force_refresh", False))
    marks = payload.get("marks", ["H", "I", "J"])
    marks_tuple = tuple(str(mark).upper() for mark in marks)

    if limit_cards is not None:
        try:
            limit_cards = int(limit_cards)
        except (TypeError, ValueError):
            return jsonify({"error": "limit_cards must be an integer or null."}), 400

    try:
        report = analyze_standard_coverage(
            limit_cards=limit_cards,
            marks=marks_tuple,
            include_examples=include_examples,
            force_refresh=force_refresh,
        )
    except Exception as error:
        return jsonify({"error": str(error)}), 500

    return jsonify(report)


@app.route('/coverage/recommend_templates', methods=['POST'])
def coverage_recommend_templates():
    payload = request.get_json(silent=True) or {}
    limit_cards = payload.get("limit_cards", 250)
    include_examples = bool(payload.get("include_examples", False))
    force_refresh = bool(payload.get("force_refresh", False))
    marks = payload.get("marks", ["H", "I", "J"])
    marks_tuple = tuple(str(mark).upper() for mark in marks)

    if limit_cards is not None:
        try:
            limit_cards = int(limit_cards)
        except (TypeError, ValueError):
            return jsonify({"error": "limit_cards must be an integer or null."}), 400

    try:
        report = analyze_template_recommendations(
            limit_cards=limit_cards,
            marks=marks_tuple,
            include_examples=include_examples,
            force_refresh=force_refresh,
        )
    except Exception as error:
        return jsonify({"error": str(error)}), 500

    return jsonify(report)


@app.route('/coverage/unresolved_registry', methods=['GET'])
def coverage_unresolved_registry():
    limit_raw = request.args.get("limit", "100")
    try:
        limit = int(limit_raw)
    except ValueError:
        return jsonify({"error": "limit must be an integer."}), 400

    return jsonify(snapshot_unresolved_registry(limit=limit))


@app.route('/coverage/unresolved_registry/clear', methods=['POST'])
def coverage_unresolved_registry_clear():
    clear_unresolved_registry()
    return jsonify({"cleared": True})


@app.route('/yolo/run', methods=['POST'])
def yolo_run():
    payload = request.get_json(silent=True) or {}
    limit_cards = payload.get("limit_cards", 350)
    include_examples = bool(payload.get("include_examples", True))
    force_refresh = bool(payload.get("force_refresh", False))
    marks = payload.get("marks", ["H", "I", "J"])
    marks_tuple = tuple(str(mark).upper() for mark in marks)

    if limit_cards is not None:
        try:
            limit_cards = int(limit_cards)
        except (TypeError, ValueError):
            return jsonify({"error": "limit_cards must be an integer or null."}), 400

    try:
        report = run_full_yolo_pass(
            limit_cards=limit_cards,
            marks=marks_tuple,
            include_examples=include_examples,
            force_refresh=force_refresh,
        )
    except Exception as error:
        return jsonify({"error": str(error)}), 500

    return jsonify(report)


@app.route('/legality/snapshot', methods=['POST'])
def legality_snapshot():
    payload = request.get_json(silent=True) or {}
    as_of_date = payload.get("as_of_date")
    waiting_days = payload.get("waiting_days", 14)
    limit_cards = payload.get("limit_cards", 500)
    marks = payload.get("marks", ["H", "I", "J"])

    try:
        waiting_days = int(waiting_days)
    except (TypeError, ValueError):
        return jsonify({"error": "waiting_days must be an integer."}), 400

    if limit_cards is not None:
        try:
            limit_cards = int(limit_cards)
        except (TypeError, ValueError):
            return jsonify({"error": "limit_cards must be an integer or null."}), 400

    marks_tuple = tuple(str(mark).upper() for mark in marks)
    return jsonify(
        build_legality_snapshot(
            as_of_date=as_of_date,
            marks=marks_tuple,
            waiting_days=waiting_days,
            limit_cards=limit_cards,
        )
    )


@app.route('/quality/gates', methods=['POST'])
def quality_gates():
    payload = request.get_json(silent=True) or {}
    coverage_limit_cards = payload.get("coverage_limit_cards", 250)
    legality_limit_cards = payload.get("legality_limit_cards", 300)
    marks = payload.get("marks", ["H", "I", "J"])
    update_baseline = bool(payload.get("update_baseline", False))
    force_refresh = bool(payload.get("force_refresh", False))

    if coverage_limit_cards is not None:
        try:
            coverage_limit_cards = int(coverage_limit_cards)
        except (TypeError, ValueError):
            return jsonify({"error": "coverage_limit_cards must be an integer or null."}), 400
    if legality_limit_cards is not None:
        try:
            legality_limit_cards = int(legality_limit_cards)
        except (TypeError, ValueError):
            return jsonify({"error": "legality_limit_cards must be an integer or null."}), 400

    marks_tuple = tuple(str(mark).upper() for mark in marks)
    return jsonify(
        run_quality_gate_checks(
            coverage_limit_cards=coverage_limit_cards,
            legality_limit_cards=legality_limit_cards,
            marks=marks_tuple,
            update_baseline=update_baseline,
            force_refresh=force_refresh,
        )
    )


@app.route('/data/pipeline/health', methods=['POST'])
def data_pipeline_health():
    payload = request.get_json(silent=True) or {}
    limit_cards = payload.get("limit_cards", 200)
    marks = payload.get("marks", ["H", "I", "J"])
    write_snapshot = bool(payload.get("write_snapshot", True))

    if limit_cards is not None:
        try:
            limit_cards = int(limit_cards)
        except (TypeError, ValueError):
            return jsonify({"error": "limit_cards must be an integer or null."}), 400

    marks_tuple = tuple(str(mark).upper() for mark in marks)
    return jsonify(
        run_data_pipeline_health(
            marks=marks_tuple,
            limit_cards=limit_cards,
            write_snapshot=write_snapshot,
        )
    )


@app.route('/fidelity/audit', methods=['POST'])
def fidelity_audit():
    payload = request.get_json(silent=True) or {}
    limit_cards = payload.get("limit_cards", 200)
    marks = payload.get("marks", ["H", "I", "J"])
    manifest_path = payload.get("manifest_path", "artifacts/fidelity/hook_manifest_latest.json")

    if limit_cards is not None:
        try:
            limit_cards = int(limit_cards)
        except (TypeError, ValueError):
            return jsonify({"error": "limit_cards must be an integer or null."}), 400

    marks_tuple = tuple(str(mark).upper() for mark in marks)
    return jsonify(
        run_fidelity_audit(
            marks=marks_tuple,
            limit_cards=limit_cards,
            manifest_path=str(manifest_path),
        )
    )

if __name__ == "__main__":
    app.run(debug=True)