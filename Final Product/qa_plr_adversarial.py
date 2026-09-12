"""Adversarial QA for the Magic Eye Lab PLR scoring pipeline.

This deliberately tests the layers separately:
1. compute_plr_metrics() with noisy synthetic time series;
2. /analyze_session assessment logic with a deterministic detector stub;
3. OpenCV pupil-contour detection on generated eye crops;
4. the real MediaPipe-backed endpoint with generated images.

The generated eye crops are not photographs of faces, so a real Face Landmarker
failure is an expected and useful result rather than a fabricated success.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import random
from pathlib import Path

import cv2
import numpy as np

import app
import pupil_core


FPS = 20
DURATION_SEC = 6.0
FLASH_TIME = 2.0
FRAME_COUNT = int(DURATION_SEC * FPS)


def make_profile(name: str, rng: random.Random):
    baseline = {
        "healthy": 7.0,
        "miosis": 2.0,
        "fixed_dilation": 8.0,
        "delayed": 7.0,
    }[name] * rng.uniform(0.94, 1.06)

    if name == "healthy":
        minimum, latency, duration = 4.0, rng.uniform(0.2, 0.4), 0.3
    elif name == "miosis":
        minimum, latency, duration = baseline * rng.uniform(0.70, 0.90), 0.3, 0.3
    elif name == "fixed_dilation":
        minimum, latency, duration = baseline * rng.uniform(0.98, 1.02), 0.3, 0.3
    elif name == "delayed":
        minimum, latency, duration = 3.5, rng.uniform(1.5, 2.0), 0.3
    else:
        raise ValueError(name)

    timestamps = [i / FPS for i in range(FRAME_COUNT)]
    diameters = []
    for t in timestamps:
        if t < FLASH_TIME:
            value = baseline
        elif t < FLASH_TIME + latency:
            progress = min(1.0, (t - FLASH_TIME) / max(latency, 1e-6))
            value = baseline + progress * (minimum - baseline)
        else:
            redilate = min(1.0, (t - FLASH_TIME - latency) / 2.5)
            value = minimum + redilate * 0.25 * (baseline - minimum)
        diameters.append(max(0.1, value + rng.gauss(0, baseline * 0.015)))
    return timestamps, diameters, baseline, minimum, latency


def make_eye_image(diameter: float, width: int = 160, height: int = 100) -> np.ndarray:
    """Create a synthetic eye crop with a dark circular pupil."""
    image = np.full((height, width, 3), 210, dtype=np.uint8)
    # Add a lighter iris disk so the pupil is a distinct contour.
    center = (width // 2, height // 2)
    iris_radius = min(width, height) // 3
    cv2.circle(image, center, iris_radius, (150, 150, 150), -1)
    pupil_radius = max(2, int(diameter / 2))
    cv2.circle(image, center, pupil_radius, (10, 10, 10), -1)
    return image


def image_data_uri(image: np.ndarray) -> str:
    ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise RuntimeError("Could not encode synthetic eye image")
    return "data:image/jpeg;base64," + base64.b64encode(encoded.tobytes()).decode()


def post_with_detector_stub(client, timestamps, diameters, bilateral_measurements=None):
    values = iter(bilateral_measurements if bilateral_measurements is not None else diameters)
    original_detector = pupil_core.analyze_frame_bgr
    original_mesh = app.get_face_mesh
    pupil_core.analyze_frame_bgr = lambda image, mesh, **kwargs: next(values)
    app.get_face_mesh = lambda: object()
    try:
        valid_image = image_data_uri(np.zeros((8, 8, 3), dtype=np.uint8))
        frames = [{"t": t, "image": valid_image} for t in timestamps]
        response = client.post(
            "/analyze_session",
            json={"flash_time": FLASH_TIME, "frames": frames},
        )
        return response.get_json()
    finally:
        pupil_core.analyze_frame_bgr = original_detector
        app.get_face_mesh = original_mesh


def post_real_images(client, timestamps, diameters):
    frames = [
        {"t": t, "image": image_data_uri(make_eye_image(diameter * 8.0))}
        for t, diameter in zip(timestamps, diameters)
    ]
    # The generated crop intentionally has no face geometry. Suppress the
    # expected per-frame diagnostic noise while preserving the response.
    with contextlib.redirect_stderr(io.StringIO()):
        response = client.post(
            "/analyze_session",
            json={"flash_time": FLASH_TIME, "frames": frames},
        )
    return response.get_json()


def run():
    rng = random.Random(20260912)
    client = app.app.test_client()
    results = {}

    for name in ("healthy", "miosis", "fixed_dilation", "delayed"):
        runs = []
        for _ in range(3):
            timestamps, diameters, baseline, minimum, latency = make_profile(name, rng)
            direct = pupil_core.compute_plr_metrics(timestamps, diameters, FLASH_TIME)
            route = post_with_detector_stub(client, timestamps, diameters)
            eye_diameter = pupil_core.find_pupil_diameter(
                cv2.cvtColor(make_eye_image(minimum * 8.0), cv2.COLOR_BGR2GRAY)
            )
            real_endpoint = post_real_images(client, timestamps, diameters)
            runs.append({
                "target": {
                    "baseline": round(baseline, 3),
                    "minimum": round(minimum, 3),
                    "latency": round(latency, 3),
                },
                "direct_metrics": direct,
                "route": {
                    "status": route.get("status"),
                    "assessment": route.get("assessment"),
                    "badge": route.get("badge"),
                    "metrics": route.get("metrics"),
                },
                "synthetic_eye_detected_diameter": eye_diameter,
                "real_image_endpoint": {
                    "status": real_endpoint.get("status"),
                    "error": real_endpoint.get("error"),
                    "valid_frames": sum(
                        d is not None for d in real_endpoint.get("diameters_px", [])
                    ),
                },
            })
        results[name] = runs

    # The current single-series endpoint has no way to accept separate eye
    # streams. Quantify how averaging hides left/right differences.
    left = [7.0] * 40 + [4.0] * 80
    right = [3.0] * 40 + [2.8] * 80
    averaged = [(l + r) / 2 for l, r in zip(left, right)]
    results["anisocoria_average_demo"] = {
        "left_metrics": pupil_core.compute_plr_metrics(
            [i / FPS for i in range(120)], left, FLASH_TIME
        ),
        "right_metrics": pupil_core.compute_plr_metrics(
            [i / FPS for i in range(120)], right, FLASH_TIME
        ),
        "averaged_metrics": pupil_core.compute_plr_metrics(
            [i / FPS for i in range(120)], averaged, FLASH_TIME
        ),
        "endpoint_has_separate_eye_fields": False,
    }
    averaged_route = post_with_detector_stub(
        client,
        [i / FPS for i in range(120)],
        averaged,
    )
    results["anisocoria_average_demo"]["current_endpoint_route"] = {
        "status": averaged_route.get("status"),
        "assessment": averaged_route.get("assessment"),
        "badge": averaged_route.get("badge"),
        "metrics": averaged_route.get("metrics"),
    }
    asymmetry_measurements = [
        {"diameter": (l + r) / 2, "left": l, "right": r}
        for l, r in zip(left, right)
    ]
    asymmetry_route = post_with_detector_stub(
        client,
        [i / FPS for i in range(120)],
        averaged,
        bilateral_measurements=asymmetry_measurements,
    )
    results["anisocoria_average_demo"]["bilateral_route_after_fix"] = {
        "status": asymmetry_route.get("status"),
        "assessment": asymmetry_route.get("assessment"),
        "badge": asymmetry_route.get("badge"),
        "finding": asymmetry_route.get("finding"),
        "left_eye_metrics": asymmetry_route.get("left_eye_metrics"),
        "right_eye_metrics": asymmetry_route.get("right_eye_metrics"),
    }
    anisocoria_runs = []
    for _ in range(3):
        left_base = 7.0 * rng.uniform(0.94, 1.06)
        right_base = 3.0 * rng.uniform(0.94, 1.06)
        left_series = [left_base] * 40 + [left_base * rng.uniform(0.54, 0.62)] * 80
        right_series = [right_base] * 40 + [right_base * rng.uniform(0.88, 0.96)] * 80
        combined = [(l + r) / 2 for l, r in zip(left_series, right_series)]
        measurements = [
            {"diameter": (l + r) / 2, "left": l, "right": r}
            for l, r in zip(left_series, right_series)
        ]
        bilateral = post_with_detector_stub(
            client, [i / FPS for i in range(120)], combined,
            bilateral_measurements=measurements,
        )
        real = post_real_images(client, [i / FPS for i in range(120)], combined)
        anisocoria_runs.append({
            "left_metrics": pupil_core.compute_plr_metrics([i / FPS for i in range(120)], left_series, FLASH_TIME),
            "right_metrics": pupil_core.compute_plr_metrics([i / FPS for i in range(120)], right_series, FLASH_TIME),
            "averaged_metrics": pupil_core.compute_plr_metrics([i / FPS for i in range(120)], combined, FLASH_TIME),
            "bilateral_route": {"status": bilateral.get("status"), "assessment": bilateral.get("assessment"), "badge": bilateral.get("badge")},
            "synthetic_eye_detected_diameters": [
                pupil_core.find_pupil_diameter(cv2.cvtColor(make_eye_image(left_base * 8), cv2.COLOR_BGR2GRAY)),
                pupil_core.find_pupil_diameter(cv2.cvtColor(make_eye_image(right_base * 8), cv2.COLOR_BGR2GRAY)),
            ],
            "real_image_endpoint": {"status": real.get("status"), "valid_frames": sum(d is not None for d in real.get("diameters_px", []))},
        })
    results["anisocoria_average_demo"]["randomized_runs"] = anisocoria_runs

    results["rapd_average_demo"] = {
        "normal_eye_pct": 45.0,
        "weak_eye_pct": 5.0,
        "averaged_pct": 25.0,
        "endpoint_has_separate_eye_fields": False,
    }
    rapd_route = post_with_detector_stub(
        client,
        [i / FPS for i in range(120)],
        averaged,
    )
    results["rapd_average_demo"]["current_endpoint_route"] = {
        "status": rapd_route.get("status"),
        "assessment": rapd_route.get("assessment"),
        "badge": rapd_route.get("badge"),
        "metrics": rapd_route.get("metrics"),
    }
    normal_eye = [7.0] * 40 + [3.8] * 80
    weak_eye = [7.0] * 40 + [6.5] * 80
    rapd_measurements = [
        {"diameter": (l + r) / 2, "left": l, "right": r}
        for l, r in zip(normal_eye, weak_eye)
    ]
    rapd_bilateral_route = post_with_detector_stub(
        client,
        [i / FPS for i in range(120)],
        [(l + r) / 2 for l, r in zip(normal_eye, weak_eye)],
        bilateral_measurements=rapd_measurements,
    )
    results["rapd_average_demo"]["bilateral_route_after_fix"] = {
        "status": rapd_bilateral_route.get("status"),
        "assessment": rapd_bilateral_route.get("assessment"),
        "badge": rapd_bilateral_route.get("badge"),
        "finding": rapd_bilateral_route.get("finding"),
        "left_eye_metrics": rapd_bilateral_route.get("left_eye_metrics"),
        "right_eye_metrics": rapd_bilateral_route.get("right_eye_metrics"),
    }
    rapd_runs = []
    for _ in range(3):
        left_base = 7.0 * rng.uniform(0.94, 1.06)
        right_base = 7.0 * rng.uniform(0.94, 1.06)
        left_series = [left_base] * 40 + [left_base * rng.uniform(0.50, 0.60)] * 80
        right_series = [right_base] * 40 + [right_base * rng.uniform(0.88, 0.96)] * 80
        combined = [(l + r) / 2 for l, r in zip(left_series, right_series)]
        measurements = [
            {"diameter": (l + r) / 2, "left": l, "right": r}
            for l, r in zip(left_series, right_series)
        ]
        bilateral = post_with_detector_stub(
            client, [i / FPS for i in range(120)], combined,
            bilateral_measurements=measurements,
        )
        real = post_real_images(client, [i / FPS for i in range(120)], combined)
        rapd_runs.append({
            "left_metrics": pupil_core.compute_plr_metrics([i / FPS for i in range(120)], left_series, FLASH_TIME),
            "right_metrics": pupil_core.compute_plr_metrics([i / FPS for i in range(120)], right_series, FLASH_TIME),
            "averaged_metrics": pupil_core.compute_plr_metrics([i / FPS for i in range(120)], combined, FLASH_TIME),
            "bilateral_route": {"status": bilateral.get("status"), "assessment": bilateral.get("assessment"), "badge": bilateral.get("badge")},
            "synthetic_eye_detected_diameters": [
                pupil_core.find_pupil_diameter(cv2.cvtColor(make_eye_image(left_base * 8), cv2.COLOR_BGR2GRAY)),
                pupil_core.find_pupil_diameter(cv2.cvtColor(make_eye_image(right_base * 8), cv2.COLOR_BGR2GRAY)),
            ],
            "real_image_endpoint": {"status": real.get("status"), "valid_frames": sum(d is not None for d in real.get("diameters_px", []))},
        })
    results["rapd_average_demo"]["randomized_runs"] = rapd_runs

    # Honest failure path: no images / invalid frames.
    failure = client.post(
        "/analyze_session",
        json={
            "flash_time": FLASH_TIME,
            "frames": [
                {"t": i / FPS, "image": ""} for i in range(FRAME_COUNT)
            ],
        },
    ).get_json()
    results["no_face_failure"] = {
        "status": failure.get("status"),
        "error": failure.get("error"),
    }

    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    run()