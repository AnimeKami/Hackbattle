import json
import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

FLASK_BACKEND_URL = "http://127.0.0.1:5000"


@app.route("/")
def index():
    """Serves the frontend HTML file to the connected phone."""
    return send_file("code.html")


@app.route("/bridge.js")
def bridge_script():
    """Serves the client-side sensor & vibration runner."""
    return send_file("bridge.js")


@app.route("/api/forward/<mode>", methods=["POST"])
def forward_to_backend(mode):
    """
    Receives JSON payload from the phone browser, verifies formatting,
    and forwards it to the target backend analysis route in app.py.
    """
    endpoint_map = {
        "tremor": f"{FLASK_BACKEND_URL}/api/tremor",
        "vibration": f"{FLASK_BACKEND_URL}/api/vibration-response",
        "reflex": f"{FLASK_BACKEND_URL}/api/reflex",
    }

    target_url = endpoint_map.get(mode)
    if not target_url:
        return jsonify({"error": f"Invalid test mode: {mode}"}), 400

    payload = request.get_json(silent=True)
    if not payload or "samples" not in payload:
        return jsonify({"error": "Payload must contain a 'samples' array"}), 400

    samples = payload.get("samples", [])
    if not isinstance(samples, list) or len(samples) < 10:
        return jsonify({"error": "'samples' must contain at least 10 items"}), 400

    # Reflex endpoint validation required by app.py
    if mode == "reflex":
        first_sample = samples[0]
        if "pulse_index" not in first_sample or "pulse_active" not in first_sample:
            return jsonify({
                "error": "Reflex test samples must include 'pulse_index' and 'pulse_active'"
            }), 400

    try:
        backend_response = requests.post(
            target_url,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=15,
        )
        return jsonify(backend_response.json()), backend_response.status_code
    except requests.exceptions.RequestException as err:
        return jsonify({"error": f"Failed to forward to backend engine: {err}"}), 502


if __name__ == "__main__":
    # Host on 0.0.0.0 so phone on same Wi-Fi / tunnel can reach it
    app.run(host="0.0.0.0", port=8080, debug=True)