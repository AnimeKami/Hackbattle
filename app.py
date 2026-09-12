"""
Motor Health Screen -- Unified Backend & Frontend Host
"""

import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

from analysis import tremor, vibration_response, reflex, escalating_tolerance
from analysis.signal_utils import dataframe_from_samples, estimate_sampling_rate

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DISCLAIMER = (
    "This is a screening tool, not a medical diagnosis. "
    "Always consult a qualified doctor about health concerns."
)

# ---------------------------------------------------------------------------
# Frontend Static Hosting Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Serves the frontend dashboard."""
    return send_file(os.path.join(BASE_DIR, "code.html"))

@app.route("/bridge.js")
def bridge_script():
    """Serves the client-side sensor capture script."""
    return send_file(os.path.join(BASE_DIR, "bridge.js"))

# ---------------------------------------------------------------------------
# Shared Request Helper
# ---------------------------------------------------------------------------

def _parse_samples_from_request() -> tuple:
    """Shared request parsing and validation for all test endpoints."""
    body = request.get_json(silent=True)
    if not body or "samples" not in body:
        raise ValueError("Request body must be JSON with a 'samples' array.")

    samples = body["samples"]
    if not isinstance(samples, list) or len(samples) < 10:
        raise ValueError("'samples' must be a list with at least 10 readings.")

    df = dataframe_from_samples(samples)
    fs = estimate_sampling_rate(df)
    return df, fs

# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"})

@app.route("/api/tremor", methods=["POST"])
def tremor_test():
    try:
        df, fs = _parse_samples_from_request()
        result = tremor.run(df, fs)
        
        if not isinstance(result, dict):
            raise TypeError("Analysis module must return a dictionary.")
            
        result["sampling_rate_hz"] = round(fs, 1)
        result["disclaimer"] = DISCLAIMER
        return jsonify(result)
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {e}"}), 500

@app.route("/api/vibration-response", methods=["POST"])
def vibration_response_test():
    try:
        df, fs = _parse_samples_from_request()
        result = vibration_response.run(df, fs)
        
        if not isinstance(result, dict):
            raise TypeError("Analysis module must return a dictionary.")
            
        result["sampling_rate_hz"] = round(fs, 1)
        result["disclaimer"] = DISCLAIMER
        return jsonify(result)
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {e}"}), 500

@app.route("/api/reflex", methods=["POST"])
def reflex_test():
    try:
        df, fs = _parse_samples_from_request()
        
        if "pulse_index" not in df.columns or "pulse_active" not in df.columns:
            raise ValueError("The reflex endpoint requires 'pulse_index' and 'pulse_active' fields in samples.")
            
        result = reflex.run(df, fs)
        
        if not isinstance(result, dict):
            raise TypeError("Analysis module must return a dictionary.")
            
        result["sampling_rate_hz"] = round(fs, 1)
        result["disclaimer"] = DISCLAIMER
        return jsonify(result)
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {e}"}), 500

@app.route("/api/escalating", methods=["POST"])
def escalating_test():
    try:
        df, fs = _parse_samples_from_request()
        result = escalating_tolerance.run(df, fs)
        
        if not isinstance(result, dict):
            raise TypeError("Analysis module must return a dictionary.")
            
        result["sampling_rate_hz"] = round(fs, 1)
        result["disclaimer"] = DISCLAIMER
        return jsonify(result)
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {e}"}), 500

# ---------------------------------------------------------------------------
# Direct Bridge Router
# ---------------------------------------------------------------------------

@app.route("/api/forward/<mode>", methods=["POST"])
def forward_to_internal_endpoint(mode):
    """Directly dispatches to the analysis handlers."""
    if mode == "tremor":
        return tremor_test()
    elif mode == "vibration":
        return vibration_response_test()
    elif mode == "reflex":
        return reflex_test()
    elif mode == "escalating":
        return escalating_test()
    else:
        return jsonify({"error": f"Invalid test mode: {mode}"}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)