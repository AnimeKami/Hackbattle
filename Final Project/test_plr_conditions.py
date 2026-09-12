import importlib.util
from pathlib import Path

import cv2
import numpy as np
import pytest


ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / "app.py"
spec = importlib.util.spec_from_file_location("final_product_app", APP_PATH)
final_app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final_app)


def _mid_brightness_image_uri():
    image = np.full((12, 12, 3), 128, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    import base64
    return "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode()


def _profile(name):
    flash_time = 2.0
    fps = 20
    timestamps = [i / fps for i in range(120)]

    if name == "healthy_control":
        baseline, minimum, latency = 7.0, 4.0, 0.3
    elif name == "miosis":
        baseline, minimum, latency = 2.0, 1.4, 0.3
    elif name == "mydriasis":
        baseline, minimum, latency = 8.0, 8.0, 0.3
    elif name == "sluggish_delayed_reflex":
        baseline, minimum, latency = 7.0, 3.5, 1.5
    elif name in {"anisocoria", "rapd"}:
        baseline, minimum, latency = 7.0, 4.0, 0.3
    else:
        raise ValueError(name)

    def curve(base, minimum_value, response_latency, onset_delay=0.0):
        values = []
        for timestamp in timestamps:
            if timestamp < flash_time + onset_delay:
                value = base
            elif timestamp < flash_time + onset_delay + response_latency:
                progress = (timestamp - flash_time - onset_delay) / response_latency
                value = base + progress * (minimum_value - base)
            else:
                value = minimum_value
            values.append(value)
        return values

    if name == "anisocoria":
        left = curve(7.0, 4.0, 0.3)
        right = curve(4.0, 2.5, 0.3)
    elif name == "rapd":
        left = curve(7.0, 3.5, 0.3)
        right = curve(7.0, 6.5, 0.3)
    else:
        left = right = None

    if left is None:
        onset_delay = latency if name == "sluggish_delayed_reflex" else 0.0
        duration = 0.3 if name == "sluggish_delayed_reflex" else latency
        measurements = [{"diameter": value, "confidence": 0.95, "iris_diameter": 40.0} for value in curve(baseline, minimum, duration, onset_delay)]
    else:
        measurements = [
            {
                "diameter": (left_value + right_value) / 2.0,
                "left": left_value,
                "right": right_value,
                "confidence": 0.95,
                "iris_diameter": 40.0,
            }
            for left_value, right_value in zip(left, right)
        ]
    return flash_time, timestamps, measurements


@pytest.mark.parametrize(
    ("profile", "expected_finding"),
    [
        ("healthy_control", "normal"),
        ("miosis", "normal"),
        ("mydriasis", "absent_reflex"),
        ("anisocoria", "baseline_asymmetry"),
        ("rapd", "response_asymmetry"),
        ("sluggish_delayed_reflex", "delayed_reflex"),
    ],
)
def test_plr_condition_finding(profile, expected_finding, monkeypatch):
    flash_time, timestamps, measurements = _profile(profile)
    values = iter(measurements)
    monkeypatch.setattr(final_app, "get_face_mesh", lambda: object())
    monkeypatch.setattr(final_app.pupil_core, "analyze_frame_bgr", lambda image, mesh, **kwargs: next(values))

    image_uri = _mid_brightness_image_uri()
    response = final_app.app.test_client().post(
        "/analyze_session",
        json={
            "flash_time": flash_time,
            "frames": [{"t": timestamp, "image": image_uri} for timestamp in timestamps],
        },
    )

    payload = response.get_json()
    assert payload["status"] == "success"
    assert payload["finding"] == expected_finding


@pytest.mark.parametrize(
    "payload",
    [
        {
            "timestamp": "2026-09-12T12:00:00+00:00",
            "assessment": "Normal Pupillary Light Reflex detected",
            "finding": "normal",
            "metrics": {
                "baseline_diameter_px": 7.0,
                "min_diameter_px": 4.0,
                "latency_sec": 0.3,
                "pct_constriction": 42.9,
                "baseline_diameter_mm": 2.05,
                "min_diameter_mm": 1.17,
            },
        },
        {
            "timestamp": "2026-09-12T12:01:00+00:00",
            "assessment": "Asymmetric light response detected",
            "finding": "response_asymmetry",
            "metrics": {
                "baseline_diameter_px": 7.0,
                "min_diameter_px": 5.0,
                "latency_sec": 0.4,
                "pct_constriction": 28.6,
            },
            "left_eye_metrics": {"baseline_diameter_px": 7.0, "min_diameter_px": 3.5, "pct_constriction": 50.0},
            "right_eye_metrics": {"baseline_diameter_px": 7.0, "min_diameter_px": 6.5, "pct_constriction": 7.1},
        },
    ],
)
def test_export_report_returns_non_empty_clinical_report(payload):
    response = final_app.app.test_client().post("/export_report", json=payload)

    assert response.status_code == 200
    assert response.data
    assert b"PUPILLARY LIGHT REFLEX SCREENING REPORT" in response.data
    assert b"DISCLAIMER: This is a screening tool, not a diagnostic device." in response.data