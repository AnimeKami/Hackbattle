"""
app.py — Flask backend for the pupil (PLR) module.

Endpoints:
  GET  /demo            -> runs the fully synthetic pipeline, no camera needed.
                            Use this as your on-stage fallback if live camera fails.
  POST /analyze_session  -> body: {"flash_time": 2.0,
                                    "frames": [{"t": 0.05, "image": "<base64 jpg>"}, ...]}
                            Returns pupil-diameter time series + PLR metrics.
  GET  /health           -> simple check that the server is up.

Run with:  python3 app.py
Then open http://localhost:5000/demo in a browser to sanity check it.
"""

import base64
import io
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, Response, jsonify, request, send_file

import pupil_core

app = Flask(__name__)

LIGHTING_TOO_DIM_LUMA = 40.0
LIGHTING_TOO_BRIGHT_LUMA = 220.0


def _lighting_warning(frames):
    """Return a soft warning based on the first two decodable frames."""
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

# MediaPipe Face Landmarker is loaded once, lazily -- it's a bit slow to init.
_face_mesh = None


@app.route("/")
def index():
    """Serve the integrated dashboard designed in ``code.html``."""
    return send_file(Path(__file__).resolve().parent / "code.html")


@app.route("/dashboard")
def dashboard():
    """Named dashboard URL for bookmarks and embedding."""
    return send_file(Path(__file__).resolve().parent / "code.html")


def get_face_mesh():
    global _face_mesh
    if _face_mesh is None:
        import mediapipe as mp
        model_path = Path(__file__).resolve().parent / "models" / "face_landmarker.task"
        if not model_path.is_file():
            raise FileNotFoundError(
                f"MediaPipe Face Landmarker model not found: {model_path}"
            )
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


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/demo")
def demo():
    metrics, csv_path, plot_path = pupil_core.run_synthetic_demo()
    timestamps, diameters = pupil_core.generate_synthetic_session(flash_time=2.0)
    with open(plot_path, "rb") as f:
        plot_b64 = base64.b64encode(f.read()).decode("utf-8")
    return jsonify({
        "timestamps": timestamps,
        "diameters_px": diameters,
        "metrics": metrics,
        "plot_png_base64": plot_b64,
    })


def decode_base64_image(b64_str):
    if "," in b64_str:  # strip "data:image/jpeg;base64," prefix if present
        b64_str = b64_str.split(",", 1)[1]
    img_bytes = base64.b64decode(b64_str)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


@app.route("/export_report", methods=["POST"])
def export_report():
    """Return a plain-text clinical summary for a completed session payload."""
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

    lines.extend([
        "",
        "DISCLAIMER: This is a screening tool, not a diagnostic device.",
        "Results are not a substitute for examination by a qualified clinician.",
    ])
    return Response("\n".join(lines) + "\n", mimetype="text/plain", headers={"Content-Disposition": "attachment; filename=plr_report.txt"})


@app.route("/analyze_session", methods=["POST"])
def analyze_session():
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
            continue
        measurement = pupil_core.analyze_frame_bgr(img, face_mesh, return_details=True)
        if isinstance(measurement, dict):
            diameter = measurement.get("diameter")
            iris_diameter = measurement.get("iris_diameter")
            confidence = measurement.get("confidence")
        else:
            diameter = measurement
            iris_diameter = None
            confidence = None
        timestamps.append(t)
        raw_diameters.append(diameter)
        iris_diameters.append(iris_diameter)
        confidences.append(confidence)
        min_confidence = data.get("min_confidence")
        diameters.append(
            None if min_confidence is not None and (confidence is None or confidence < float(min_confidence)) else diameter
        )

    metrics = pupil_core.compute_plr_metrics(timestamps, diameters, flash_time, iris_diameters)

    valid_count = sum(1 for d in diameters if d is not None)
    pre_valid = sum(1 for t, d in zip(timestamps, diameters) if t < flash_time and d is not None)
    post_valid = sum(1 for t, d in zip(timestamps, diameters) if t >= flash_time and d is not None)
    print(f"[PLR DIAG] Session complete: {valid_count}/{len(diameters)} frames with valid measurements (pre-flash: {pre_valid}, post-flash: {post_valid})", file=sys.stderr, flush=True)
    print(f"[PLR DIAG] Calculated metrics: {metrics}", file=sys.stderr, flush=True)

    return jsonify({
        "timestamps": timestamps,
        "diameters_px": diameters,
        "diameters_px_raw": raw_diameters,
        "confidence": confidences,
        "average_confidence": float(np.mean([c for c in confidences if c is not None])) if any(c is not None for c in confidences) else None,
        "metrics": metrics,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
