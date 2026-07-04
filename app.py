from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from core.card_blueprints import list_blueprints
from sim.game import analyze_card_text, analyze_standard_coverage, build_blueprint_card, run_simulation

app = Flask(__name__)

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/run_sim', methods=['POST'])
def run_sim():
    return jsonify(run_simulation())


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

if __name__ == "__main__":
    app.run(debug=True)