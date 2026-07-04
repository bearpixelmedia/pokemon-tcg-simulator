from flask import Flask, render_template, jsonify
app = Flask(__name__)

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/run_sim', methods=['POST'])
def run_sim():
    from sim.game import run_simulation
    return jsonify(run_simulation())

if __name__ == "__main__":
    app.run(debug=True)