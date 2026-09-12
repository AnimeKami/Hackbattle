"""
NeuroScreen Suite -- Unified Launcher
=======================================

This is the single entry point that ties all three deliverables together
into one running application:

  * mainui.html   -> served at "/"        (the hub / bridge page)
  * Gyro module   -> served at "/motor/*" (Motor & Tremor screening)
  * Pupil module  -> served at "/pupil/*" (Pupillary Light Reflex screening)

mainui.html is the bridge: its two launch buttons navigate the browser to
"/motor/" and "/pupil/", which are two independent Flask Blueprints running
inside this SAME process (no separate servers, no port juggling). Each
sub-app keeps its own API routes exactly as they were designed, just mounted
under a URL prefix so they can coexist peacefully, and each sub-app's page
has a "HUB" link back to "/".

Run with:  python3 app.py
Then open: http://localhost:5000/
"""

import os
import sys
from pathlib import Path

from flask import Blueprint, Flask, jsonify, request, send_file

BASE_DIR = Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Make each sub-module's own package-relative imports ("import pupil_core",
# "from analysis import tremor") work without editing their source files.
# ---------------------------------------------------------------------------
sys.path.insert(0, str(BASE_DIR / "motor"))
sys.path.insert(0, str(BASE_DIR / "pupil"))

from analysis import tremor, vibration_response, reflex, escalating_tolerance  # noqa: E402
from analysis.signal_utils import dataframe_from_samples, estimate_sampling_rate  # noqa: E402

import pupil_core  # noqa: E402

try:
    from flask_cors import CORS
except ImportError:  # pragma: no cover - CORS is optional at runtime
    CORS = None

app = Flask(__name__)
if CORS is not None:
    CORS(app)

MOTOR_DIR = BASE_DIR / "motor"
PUPIL_DIR = BASE_DIR / "pupil"

DISCLAIMER = (
    "This is a screening tool, not a medical diagnosis. "
    "Always consult a qualified doctor about health concerns."
)

# ===========================================================================
# HUB -- mainui.html is the bridge page linking the two modules together
# ===========================================================================


@app.route("/")
def hub():
    return send_file(BASE_DIR / "mainui.html")


@app.route("/combined/")
def combined_results():
    """Serve the browser-side shared motor/PLR results view."""
    return send_file(BASE_DIR / "combined.html")


# ===========================================================================
# MOTOR MODULE (formerly Gyro/Final Product) -- mounted at /motor
# ===========================================================================

motor_bp = Blueprint("motor", __name__, url_prefix="/motor")


@motor_bp.route("/")
def motor_index():
    return send_file(MOTOR_DIR / "code.html")


@motor_bp.route("/bridge.js")
def motor_bridge_script():
    return send_file(MOTOR_DIR / "bridge.js")


def _parse_samples_from_request() -> tuple:
    body = request.get_json(silent=True)
    if not body or "samples" not in body:
        raise ValueError("Request body must be JSON with a 'samples' array.")

    samples = body["samples"]
    if not isinstance(samples, list) or len(samples) < 10:
        raise ValueError("'samples' must be a list with at least 10 readings.")

    df = dataframe_from_samples(samples)
    df.attrs["context"] = body.get("context", "postural")
    fs = estimate_sampling_rate(df)
    return df, fs


@motor_bp.route("/api/health", methods=["GET"])
def motor_health_check():
    return jsonify({"status": "ok"})


@motor_bp.route("/api/tremor", methods=["POST"])
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


@motor_bp.route("/api/vibration-response", methods=["POST"])
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


@motor_bp.route("/api/reflex", methods=["POST"])
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


@motor_bp.route("/api/escalating", methods=["POST"])
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


@motor_bp.route("/api/forward/<mode>", methods=["POST"])
def forward_to_internal_endpoint(mode):
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


app.register_blueprint(motor_bp)

# ===========================================================================
# PUPIL MODULE (formerly Hackbattle-DaGoat/Final Project) -- mounted at /pupil
# ===========================================================================

pupil_bp = Blueprint("pupil", __name__, url_prefix="/pupil")

LIGHTING_TOO_DIM_LUMA = 40.0
LIGHTING_TOO_BRIGHT_LUMA = 220.0

_face_mesh = None


def _lighting_warning(frames):
    import cv2
    import numpy as np

    luminances = []
    for item in frames[:2]:
        try:
            image = decode_base64_image(item.get("image", ""))
            if image is not None:
                luminances.append(float(np.mean(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))))
        except (TypeError, ValueError, cv2.error):
            continue
    if not luminances:
        return None
    average_luminance = float(np.mean(luminances))
    if average_luminance < LIGHTING_TOO_DIM_LUMA:
        message = "Lighting looks too dim for a reliable reading. Move to a brighter room and try again."
    elif average_luminance > LIGHTING_TOO_BRIGHT_LUMA:
        message = "Lighting looks too bright for a reliable reading. Reduce glare and try again."
    else:
        return None
    return {
        "status": "warning",
        "warning_type": "lighting",
        "message": message,
        "average_luminance": average_luminance,
    }


def decode_base64_image(b64_str):
    import base64

    import cv2
    import numpy as np

    if "," in b64_str:
        b64_str = b64_str.split(",", 1)[1]
    img_bytes = base64.b64decode(b64_str)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def get_face_mesh():
    global _face_mesh
    if _face_mesh is None:
        import mediapipe as mp

        model_path = PUPIL_DIR / "models" / "face_landmarker.task"
        if not model_path.is_file():
            raise FileNotFoundError(f"MediaPipe Face Landmarker model not found: {model_path}")
        options = mp.tasks.vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp.tasks.vision.RunningMode.IMAGE,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        _face_mesh = mp.tasks.vision.FaceLandmarker.create_from_options(options)
    return _face_mesh


def _classify_pupil_result(metrics, left_metrics=None, right_metrics=None):
    """Map measured PLR metrics to a conservative screening label."""
    if metrics.get("error"):
        return "inconclusive", "Insufficient valid pupil measurements for a reliable screening result."

    if left_metrics and right_metrics:
        left_base = left_metrics.get("baseline_diameter_px")
        right_base = right_metrics.get("baseline_diameter_px")
        left_pct = left_metrics.get("pct_constriction")
        right_pct = right_metrics.get("pct_constriction")
        if left_base and right_base and abs(left_base - right_base) / max(left_base, right_base) >= 0.20:
            return "baseline_asymmetry", "Meaningful baseline pupil-size asymmetry detected between the eyes."
        if left_pct is not None and right_pct is not None and abs(left_pct - right_pct) >= 20.0:
            return "response_asymmetry", "Meaningful asymmetry in the two eyes' light responses detected."

    if metrics.get("pct_constriction", 0.0) <= 5.0 and metrics.get("baseline_diameter_px", 0.0) >= 8.0:
        return "absent_reflex", "Large pupil with little or no constriction detected after the flash. Urgent clinical assessment is recommended."
    if metrics.get("time_to_min_sec", 0.0) >= 1.2:
        return "delayed_reflex", "Pupillary constriction began or reached its minimum more slowly than expected."
    if metrics.get("pct_constriction", 0.0) < 25.0:
        return "reduced_reflex", "Pupillary constriction was reduced compared with the expected screening range."
    return "normal", "Brisk pupillary light response detected within the screening range."


@pupil_bp.route("/")
def pupil_index():
    return send_file(PUPIL_DIR / "code.html")


@pupil_bp.route("/dashboard")
def pupil_dashboard():
    return send_file(PUPIL_DIR / "code.html")


@pupil_bp.route("/health")
def pupil_health():
    return jsonify({"status": "ok"})


@pupil_bp.route("/demo")
def demo():
    import base64

    metrics, csv_path, plot_path = pupil_core.run_synthetic_demo()
    timestamps, diameters = pupil_core.generate_synthetic_session(flash_time=2.0)
    with open(plot_path, "rb") as f:
        plot_b64 = base64.b64encode(f.read()).decode("utf-8")
    return jsonify(
        {
            "timestamps": timestamps,
            "diameters_px": diameters,
            "metrics": metrics,
            "plot_png_base64": plot_b64,
        }
    )


@pupil_bp.route("/export_report", methods=["POST"])
def export_report():
    from datetime import datetime, timezone

    from flask import Response

    payload = request.get_json(force=True) or {}
    metrics = payload.get("metrics") or {}
    lines = [
        "PUPILLARY LIGHT REFLEX SCREENING REPORT",
        "========================================",
        f"Timestamp: {payload.get('timestamp') or datetime.now(timezone.utc).isoformat()}",
        f"Assessment: {payload.get('assessment', 'Not provided')}",
        f"Finding: {payload.get('finding', 'Not provided')}",
        "",
        "Core metrics:",
    ]
    for label, key in (
        ("Baseline diameter (px)", "baseline_diameter_px"),
        ("Minimum diameter (px)", "min_diameter_px"),
        ("Latency (sec)", "latency_sec"),
        ("Time to minimum (sec)", "time_to_min_sec"),
        ("Constriction (%)", "pct_constriction"),
        ("Baseline diameter (mm, estimated)", "baseline_diameter_mm"),
        ("Minimum diameter (mm, estimated)", "min_diameter_mm"),
    ):
        if key in metrics and metrics[key] is not None:
            lines.append(f"- {label}: {metrics[key]}")

    for eye_name, eye_key in (("Left eye", "left_eye_metrics"), ("Right eye", "right_eye_metrics")):
        eye_metrics = payload.get(eye_key)
        if eye_metrics:
            lines.extend(["", f"{eye_name}:"])
            for key in ("baseline_diameter_px", "min_diameter_px", "latency_sec", "pct_constriction", "baseline_diameter_mm", "min_diameter_mm"):
                if key in eye_metrics and eye_metrics[key] is not None:
                    lines.append(f"- {key}: {eye_metrics[key]}")

    lines.extend(
        [
            "",
            "DISCLAIMER: This is a screening tool, not a diagnostic device.",
            "Results are not a substitute for examination by a qualified clinician.",
        ]
    )
    return Response(
        "\n".join(lines) + "\n",
        mimetype="text/plain",
        headers={"Content-Disposition": "attachment; filename=plr_report.txt"},
    )


@pupil_bp.route("/analyze_session", methods=["POST"])
def analyze_session():
    import numpy as np

    data = request.get_json(force=True)
    flash_time = float(data.get("flash_time", 2.0))
    frames = data.get("frames", [])
    if len(frames) < 10:
        return jsonify({"error": "need at least 10 frames"}), 400

    lighting_warning = _lighting_warning(frames)
    if lighting_warning:
        return jsonify(lighting_warning), 200

    face_mesh = get_face_mesh()
    timestamps, diameters, iris_diameters, confidences = [], [], [], []
    left_diameters, right_diameters = [], []
    left_confidences, right_confidences = [], []
    raw_diameters = []

    for item in frames:
        t = float(item["t"])
        img = decode_base64_image(item["image"])
        if img is None:
            timestamps.append(t)
            diameters.append(None)
            raw_diameters.append(None)
            iris_diameters.append(None)
            confidences.append(None)
            left_diameters.append(None)
            right_diameters.append(None)
            left_confidences.append(None)
            right_confidences.append(None)
            continue
        measurement = pupil_core.analyze_frame_bgr(img, face_mesh, return_details=True)
        if isinstance(measurement, dict):
            diameter = measurement.get("diameter")
            iris_diameter = measurement.get("iris_diameter")
            confidence = measurement.get("confidence")
            left_diameter = measurement.get("left_diameter", diameter)
            right_diameter = measurement.get("right_diameter", diameter)
            left_confidence = measurement.get("left_confidence", confidence)
            right_confidence = measurement.get("right_confidence", confidence)
        else:
            diameter = measurement
            iris_diameter = None
            confidence = None
            left_diameter = diameter
            right_diameter = diameter
            left_confidence = confidence
            right_confidence = confidence
        timestamps.append(t)
        raw_diameters.append(diameter)
        iris_diameters.append(iris_diameter)
        confidences.append(confidence)
        left_diameters.append(left_diameter)
        right_diameters.append(right_diameter)
        left_confidences.append(left_confidence)
        right_confidences.append(right_confidence)
        min_confidence = data.get("min_confidence")
        diameters.append(
            None if min_confidence is not None and (confidence is None or confidence < float(min_confidence)) else diameter
        )

    metrics = pupil_core.compute_plr_metrics(timestamps, diameters, flash_time, iris_diameters)
    left_metrics = pupil_core.compute_plr_metrics(timestamps, left_diameters, flash_time)
    right_metrics = pupil_core.compute_plr_metrics(timestamps, right_diameters, flash_time)

    valid_count = sum(1 for d in diameters if d is not None)
    pre_valid = sum(1 for t, d in zip(timestamps, diameters) if t < flash_time and d is not None)
    post_valid = sum(1 for t, d in zip(timestamps, diameters) if t >= flash_time and d is not None)
    print(
        f"[PLR DIAG] Session complete: {valid_count}/{len(diameters)} frames with valid measurements "
        f"(pre-flash: {pre_valid}, post-flash: {post_valid})",
        file=sys.stderr,
        flush=True,
    )
    print(f"[PLR DIAG] Calculated metrics: {metrics}", file=sys.stderr, flush=True)

    finding, assessment = _classify_pupil_result(metrics, left_metrics, right_metrics)
    if metrics.get("error"):
        return jsonify({
            "status": "inconclusive",
            "finding": "inconclusive",
            "assessment": assessment,
            "error": metrics["error"],
            "timestamps": timestamps,
            "diameters_px": diameters,
            "diameters_px_raw": raw_diameters,
            "confidence": confidences,
            "average_confidence": float(np.mean([c for c in confidences if c is not None])) if any(c is not None for c in confidences) else None,
            "metrics": metrics,
        }), 422

    return jsonify(
        {
            "status": "success",
            "finding": finding,
            "assessment": assessment,
            "timestamps": timestamps,
            "diameters_px": diameters,
            "diameters_px_raw": raw_diameters,
            "confidence": confidences,
            "average_confidence": float(np.mean([c for c in confidences if c is not None]))
            if any(c is not None for c in confidences)
            else None,
            "metrics": metrics,
            "left_eye_metrics": left_metrics if "error" not in left_metrics else None,
            "right_eye_metrics": right_metrics if "error" not in right_metrics else None,
        }
    )


app.register_blueprint(pupil_bp)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
