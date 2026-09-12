"""
Motor Health Screen -- Backend API
--------------------------------------
A small Flask API that accepts phone sensor data (gyroscope, optionally
accelerometer) and runs one of three motor-screening analyses:

  POST /api/tremor              - hold-still tremor test
  POST /api/vibration-response  - continuous-vibration resistance test
  POST /api/reflex              - rhythmic-vibration reaction-time test
  GET  /api/health              - service healthcheck

Each POST endpoint expects JSON of the form:
  {
    "samples": [
      {"time": 0.0, "gyro_x": 0.01, "gyro_y": -0.02, "gyro_z": 0.00, ...},
      {"time": 0.017, "gyro_x": 0.02, "gyro_y": -0.01, "gyro_z": 0.01, ...},
      ...
    ]
  }

The /api/reflex endpoint additionally requires each sample to include
"pulse_index" and "pulse_active" fields (see README for how a frontend
should tag these while capturing sensor data during a rhythmic vibration).

This service does NOT provide a diagnosis. Every response includes a
disclaimer field for this reason -- do not strip it out in a client app.
"""

from flask import Flask, request, jsonify
from flask_cors import CORS

from analysis import tremor, vibration_response, reflex
from analysis.signal_utils import dataframe_from_samples, estimate_sampling_rate

app = Flask(__name__)
CORS(app)  # allow requests from a separate frontend/mobile app during development

DISCLAIMER = (
    "This is a screening tool, not a medical diagnosis. "
    "Always consult a qualified doctor about health concerns."
)


def _parse_samples_from_request() -> tuple:
    """Shared request parsing + validation for all test endpoints."""
    body = request.get_json(silent=True)
    if not body or "samples" not in body:
        raise ValueError("Request body must be JSON with a 'samples' array.")

    samples = body["samples"]
    if not isinstance(samples, list) or len(samples) < 10:
        raise ValueError("'samples' must be a list with at least 10 readings.")

    df = dataframe_from_samples(samples)
    fs = estimate_sampling_rate(df)
    return df, fs


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
    except Exception as e:  # unexpected processing error
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
        
        # Enforce the required fields for this specific test
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


if __name__ == "__main__":
    # debug=True is convenient for a hackathon; turn off before any public deployment
    app.run(host="0.0.0.0", port=5000, debug=True)