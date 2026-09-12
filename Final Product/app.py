"""
app.py — Magic Eye Lab backend (merged, final).

This wires together:
  - pupil_core.py: the accurate detection engine (bilateral eye tracking,
    blink rejection, adaptive Otsu/percentile thresholding to find the real
    pupil rather than the iris). Uses MediaPipe's modern Tasks API + the
    bundled models/face_landmarker.task, which works with the current
    mediapipe release -- no version pinning needed.
  - templates/code.html: the "Magic Eye Lab" gamified frontend.

Endpoints:
  GET  /            -> serves templates/code.html
  GET  /health      -> liveness check
  GET  /demo        -> fully synthetic pipeline, no camera needed (stage fallback)
  POST /analyze_session -> real analysis: { flash_time, frames: [{t, image}, ...] }
"""

import base64
import sys
from pathlib import Path

import cv2
import numpy as np
from flask import Flask, jsonify, render_template, request

import pupil_core

# `code.html` lives beside this app.py in the Final Product bundle rather than
# in Flask's conventional templates/ directory.
app = Flask(__name__, template_folder=str(Path(__file__).resolve().parent))

# MediaPipe Face Landmarker is loaded once, lazily -- it's a bit slow to init.
_face_mesh = None

LATENCY_DELAYED_SEC = 1.0
ASYMMETRY_BASELINE_RATIO = 0.20
ASYMMETRY_RESPONSE_DELTA_PCT = 20.0


def get_face_mesh():
    global _face_mesh
    if _face_mesh is None:
        import mediapipe as mp
        app_dir = Path(__file__).resolve().parent
        model_candidates = (
            app_dir / "models" / "face_landmarker.task",
            app_dir.parent / "models" / "face_landmarker.task",
        )
        model_path = next((path for path in model_candidates if path.is_file()), None)
        if model_path is None:
            raise FileNotFoundError(
                "MediaPipe Face Landmarker model not found. Checked: "
                + ", ".join(str(path) for path in model_candidates)
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


def decode_base64_image(b64_str):
    if "," in b64_str:  # strip "data:image/jpeg;base64," prefix if present
        b64_str = b64_str.split(",", 1)[1]
    img_bytes = base64.b64decode(b64_str)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def assess_plr(metrics, left_metrics=None, right_metrics=None):
    """Translate measured PLR features into an honest screening assessment."""
    if "error" in metrics:
        return None, None, None

    if left_metrics and right_metrics:
        left_baseline = left_metrics.get("baseline_diameter_px")
        right_baseline = right_metrics.get("baseline_diameter_px")
        if left_baseline and right_baseline:
            baseline_ratio = abs(left_baseline - right_baseline) / max(left_baseline, right_baseline)
            if baseline_ratio > ASYMMETRY_BASELINE_RATIO:
                return (
                    "Asymmetric baseline pupil sizes detected — repeat the test and seek clinical evaluation if this persists.",
                    "Pupil Asymmetry Flag ⚠️",
                    "baseline_asymmetry",
                )

        left_pct = left_metrics.get("pct_constriction")
        right_pct = right_metrics.get("pct_constriction")
        if left_pct is not None and right_pct is not None:
            if abs(left_pct - right_pct) > ASYMMETRY_RESPONSE_DELTA_PCT:
                return (
                    "Asymmetric light response detected — repeat the test and seek clinical evaluation if this persists.",
                    "RAPD Screening Flag ⚠️",
                    "response_asymmetry",
                )

    pct = metrics["pct_constriction"]
    if pct < 5.0:
        return (
            "Little to no pupillary constriction detected — repeat the test; if confirmed, seek urgent clinical evaluation.",
            "Absent Reflex Flag ⚠️",
            "absent_reflex",
        )
    if pct < 15.0:
        return (
            "Reduced pupillary constriction detected — repeat the test in a dimmer room and seek clinical evaluation if this persists.",
            "Reduced Reflex Flag ⚠️",
            "reduced_reflex",
        )
    if metrics["latency_sec"] > LATENCY_DELAYED_SEC:
        return (
            "Delayed pupillary constriction detected — repeat the test under consistent lighting and seek clinical evaluation if this persists.",
            "Delayed Reflex Flag ⚠️",
            "delayed_reflex",
        )
    return (
        "Normal Pupillary Light Reflex detected — nice, brisk constriction!",
        "Gold Star Reflex Detective 🌟",
        "normal",
    )


@app.route("/")
def index():
    """Serves the Magic Eye Lab frontend."""
    return render_template("code.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/demo")
def demo():
    """Fully synthetic pipeline -- no camera needed. Stage-safety fallback."""
    metrics, csv_path, plot_path = pupil_core.run_synthetic_demo()
    with open(plot_path, "rb") as f:
        plot_b64 = base64.b64encode(f.read()).decode("utf-8")
    return jsonify({"metrics": metrics, "plot_png_base64": plot_b64})


@app.route("/analyze_session", methods=["POST"])
def analyze_session():
    """
    Body: {"flash_time": 2.0, "frames": [{"t": 0.05, "image": "<base64 jpg>"}, ...]}
    Returns the Magic Eye Lab response schema (status/assessment/badge/metrics)
    that templates/code.html's JS reads, backed by pupil_core's real detection.
    """
    data = request.get_json(force=True)

    if not data or "frames" not in data:
        return jsonify({
            "status": "error",
            "error": "Missing frame payload. Minimum 10 frames required."
        }), 200

    flash_time = float(data.get("flash_time", 2.0))
    frames = data.get("frames", [])

    if len(frames) < 10:
        return jsonify({
            "status": "error",
            "error": f"Insufficient frames received ({len(frames)}). Require >= 10 frames."
        }), 200

    face_mesh = get_face_mesh()
    timestamps, diameters = [], []
    left_diameters, right_diameters = [], []

    for item in frames:
        t = float(item.get("t", 0.0))
        b64_img = item.get("image", "")
        if not b64_img:
            timestamps.append(t)
            diameters.append(None)
            left_diameters.append(None)
            right_diameters.append(None)
            continue
        try:
            img = decode_base64_image(b64_img)
            measurement = (
                pupil_core.analyze_frame_bgr(img, face_mesh, return_bilateral=True)
                if img is not None else None
            )
            if isinstance(measurement, dict):
                diameter = measurement.get("diameter")
                left_diameters.append(measurement.get("left"))
                right_diameters.append(measurement.get("right"))
            else:
                diameter = measurement
                left_diameters.append(None)
                right_diameters.append(None)
        except Exception:
            diameter = None  # a detection failure is a gap, never a guessed value
            left_diameters.append(None)
            right_diameters.append(None)
        timestamps.append(t)
        diameters.append(diameter)

    metrics = pupil_core.compute_plr_metrics(timestamps, diameters, flash_time)

    valid_count = sum(1 for d in diameters if d is not None)
    pre_valid = sum(1 for t, d in zip(timestamps, diameters) if t < flash_time and d is not None)
    post_valid = sum(1 for t, d in zip(timestamps, diameters) if t >= flash_time and d is not None)
    print(f"[PLR DIAG] Session complete: {valid_count}/{len(diameters)} frames valid "
          f"(pre-flash: {pre_valid}, post-flash: {post_valid})", file=sys.stderr, flush=True)
    print(f"[PLR DIAG] Calculated metrics: {metrics}", file=sys.stderr, flush=True)

    # pupil_core.compute_plr_metrics() returns {"error": "..."} when there's
    # not enough valid data -- surface that honestly rather than guessing.
    if "error" in metrics:
        return jsonify({
            "status": "error",
            "error": (
                f"Not enough valid pupil detections to score this session "
                f"({pre_valid} pre-flash, {post_valid} post-flash valid frames). "
                f"Make sure your face and eyes are clearly visible and well lit, "
                f"then try again."
            ),
            "frames_processed": len(timestamps),
            "timestamps": timestamps,
            "diameters_px": diameters,
        }), 200

    left_metrics = pupil_core.compute_plr_metrics(timestamps, left_diameters, flash_time)
    right_metrics = pupil_core.compute_plr_metrics(timestamps, right_diameters, flash_time)
    left_metrics = None if "error" in left_metrics else left_metrics
    right_metrics = None if "error" in right_metrics else right_metrics
    assessment, badge, finding = assess_plr(metrics, left_metrics, right_metrics)

    return jsonify({
        "status": "success",
        "assessment": assessment,
        "badge": badge,
        "dual_eye_status": "Bilateral tracking with automatic single-eye fallback",
        "frames_processed": len(timestamps),
        "valid_pre_flash_frames": pre_valid,
        "valid_post_flash_frames": post_valid,
        "metrics": metrics,
        "left_eye_metrics": left_metrics,
        "right_eye_metrics": right_metrics,
        "finding": finding,
        "timestamps": timestamps,
        "diameters_px": diameters,
    }), 200


if __name__ == "__main__":
    print("Starting Magic Eye Lab PLR Backend Server on http://127.0.0.1:5000")
    app.run(host="0.0.0.0", port=5000, debug=True)
