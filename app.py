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
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

import pupil_core

app = Flask(__name__)

# MediaPipe Face Landmarker is loaded once, lazily -- it's a bit slow to init.
_face_mesh = None


@app.route("/")
def index():
    return render_template("index.html")


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
    with open(plot_path, "rb") as f:
        plot_b64 = base64.b64encode(f.read()).decode("utf-8")
    return jsonify({"metrics": metrics, "plot_png_base64": plot_b64})


def decode_base64_image(b64_str):
    if "," in b64_str:  # strip "data:image/jpeg;base64," prefix if present
        b64_str = b64_str.split(",", 1)[1]
    img_bytes = base64.b64decode(b64_str)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


@app.route("/analyze_session", methods=["POST"])
def analyze_session():
    data = request.get_json(force=True)
    flash_time = float(data.get("flash_time", 2.0))
    frames = data.get("frames", [])
    if len(frames) < 10:
        return jsonify({"error": "need at least 10 frames"}), 400

    face_mesh = get_face_mesh()
    timestamps, diameters = [], []

    for item in frames:
        t = float(item["t"])
        img = decode_base64_image(item["image"])
        if img is None:
            timestamps.append(t)
            diameters.append(None)
            continue
        diameter = pupil_core.analyze_frame_bgr(img, face_mesh)
        timestamps.append(t)
        diameters.append(diameter)

    metrics = pupil_core.compute_plr_metrics(timestamps, diameters, flash_time)

    valid_count = sum(1 for d in diameters if d is not None)
    pre_valid = sum(1 for t, d in zip(timestamps, diameters) if t < flash_time and d is not None)
    post_valid = sum(1 for t, d in zip(timestamps, diameters) if t >= flash_time and d is not None)
    print(f"[PLR DIAG] Session complete: {valid_count}/{len(diameters)} frames with valid measurements (pre-flash: {pre_valid}, post-flash: {post_valid})", file=sys.stderr, flush=True)
    print(f"[PLR DIAG] Calculated metrics: {metrics}", file=sys.stderr, flush=True)

    return jsonify({
        "timestamps": timestamps,
        "diameters_px": diameters,
        "metrics": metrics,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
