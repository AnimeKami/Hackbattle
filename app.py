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

import cv2
import numpy as np
from flask import Flask, jsonify, request

import pupil_core

app = Flask(__name__)

# MediaPipe face mesh is loaded once, lazily -- it's a bit slow to init.
_face_mesh = None


def get_face_mesh():
    global _face_mesh
    if _face_mesh is None:
        import mediapipe as mp
        _face_mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,  # required -- this is what gives iris landmarks
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
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

    return jsonify({
        "timestamps": timestamps,
        "diameters_px": diameters,
        "metrics": metrics,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
