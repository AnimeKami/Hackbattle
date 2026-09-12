import unittest
import base64
from types import SimpleNamespace

import cv2
import numpy as np

import pupil_core
import app as pupil_app


def _image_data_uri(image):
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise AssertionError("could not encode test image")
    return "data:image/png;base64," + base64.b64encode(encoded.tobytes()).decode()


class ComputePlrMetricsTests(unittest.TestCase):
    def test_latency_is_constriction_onset_and_time_to_min_is_separate(self):
        flash_time = 1.0
        timestamps = [i / 10.0 for i in range(31)]
        diameters = []
        for timestamp in timestamps:
            if timestamp < flash_time:
                diameter = 100.0
            elif timestamp < 1.4:
                diameter = 100.0
            elif timestamp < 1.6:
                diameter = 90.0
            else:
                diameter = 70.0
            diameters.append(diameter)

        metrics = pupil_core.compute_plr_metrics(timestamps, diameters, flash_time)

        self.assertAlmostEqual(metrics["latency_sec"], 0.4)
        self.assertAlmostEqual(metrics["time_to_min_sec"], 0.6)
        self.assertNotEqual(metrics["latency_sec"], metrics["time_to_min_sec"])

    def test_single_outlier_does_not_throw_off_smoothed_metrics(self):
        flash_time = 1.0
        timestamps = [i / 10.0 for i in range(31)]
        diameters = [
            100.0 if timestamp < 1.4 else 90.0 if timestamp < 1.7 else 70.0
            for timestamp in timestamps
        ]
        diameters[12] = 500.0  # isolated bad frame after the flash

        metrics = pupil_core.compute_plr_metrics(timestamps, diameters, flash_time)

        self.assertAlmostEqual(metrics["baseline_diameter_px"], 100.0)
        self.assertAlmostEqual(metrics["min_diameter_px"], 70.0)
        self.assertAlmostEqual(metrics["latency_sec"], 0.4)

    def test_invalid_diameters_are_ignored_without_changing_valid_values(self):
        metrics = pupil_core.compute_plr_metrics(
            [0.0, 0.5, 1.0, 1.5, 2.0, 2.5],
            [50.0, 50.0, -10.0, 25.0, 0.0, 25.0],
            flash_time=1.0,
        )

        self.assertNotIn("error", metrics)
        self.assertAlmostEqual(metrics["baseline_diameter_px"], 50.0)
        self.assertAlmostEqual(metrics["min_diameter_px"], 25.0)

    def test_unsorted_frames_are_calculated_in_timestamp_order(self):
        metrics = pupil_core.compute_plr_metrics(
            [1.5, 0.0, 1.0, 0.5, 2.0],
            [25.0, 50.0, 50.0, 50.0, 20.0],
            flash_time=1.0,
        )

        self.assertAlmostEqual(metrics["baseline_diameter_px"], 50.0)
        self.assertAlmostEqual(metrics["min_diameter_px"], 20.0)
        self.assertAlmostEqual(metrics["time_to_min_sec"], 1.0)

    def test_iris_calibration_from_synthetic_image_is_sane(self):
        image = np.full((100, 160, 3), 200, dtype=np.uint8)
        cv2.circle(image, (80, 50), 20, (120, 120, 120), -1)
        cv2.circle(image, (80, 50), 10, (10, 10, 10), -1)

        landmarks = [SimpleNamespace(x=0.0, y=0.0) for _ in range(478)]
        for center_idx, border_indices, cx in (
            (pupil_core.LEFT_IRIS_CENTER, pupil_core.LEFT_IRIS_BORDER, 80),
            (pupil_core.RIGHT_IRIS_CENTER, pupil_core.RIGHT_IRIS_BORDER, 80),
        ):
            landmarks[center_idx] = SimpleNamespace(x=cx / 160, y=50 / 100)
            for index, (dx, dy) in zip(border_indices, ((20, 0), (0, 20), (-20, 0), (0, -20))):
                landmarks[index] = SimpleNamespace(x=(cx + dx) / 160, y=(50 + dy) / 100)

        measured_iris_px = pupil_core.measure_iris_diameter_px(landmarks, 160, 100)
        self.assertAlmostEqual(measured_iris_px, 40.0)

        timestamps = [0.0, 0.5, 1.0, 1.5]
        metrics = pupil_core.compute_plr_metrics(
            timestamps,
            [20.0, 20.0, 10.0, 10.0],
            flash_time=0.75,
            iris_diameters=[measured_iris_px] * 4,
        )

        self.assertGreater(metrics["baseline_diameter_mm"], 5.0)
        self.assertLess(metrics["baseline_diameter_mm"], 6.5)
        self.assertGreater(metrics["min_diameter_mm"], 2.0)
        self.assertLess(metrics["min_diameter_mm"], 4.0)

    def test_minimum_mm_uses_the_same_frame_as_minimum_px(self):
        metrics = pupil_core.compute_plr_metrics(
            [0.0, 0.5, 1.0, 1.5],
            [20.0, 20.0, 10.0, 12.0],
            flash_time=0.75,
            iris_diameters=[40.0, 40.0, 20.0, 40.0],
        )

        self.assertAlmostEqual(metrics["min_diameter_px"], 10.0)
        self.assertAlmostEqual(metrics["min_diameter_mm"], 5.85)

    def test_clean_pupil_has_higher_confidence_than_irregular_blob(self):
        landmarks = [SimpleNamespace(x=0.0, y=0.0) for _ in range(478)]
        landmarks[pupil_core.LEFT_IRIS_CENTER] = SimpleNamespace(x=0.5, y=0.5)
        for index, (dx, dy) in zip(pupil_core.LEFT_IRIS_BORDER, ((25, 0), (0, 25), (-25, 0), (0, -25))):
            landmarks[index] = SimpleNamespace(x=(50 + dx) / 100, y=(50 + dy) / 100)
        for index, y in zip(pupil_core.LEFT_EYE, (35, 38, 42, 46, 48, 52, 54, 58, 62, 65, 66, 64, 60, 55, 45, 38)):
            landmarks[index] = SimpleNamespace(x=0.5, y=y / 100)

        clean_image = np.full((100, 100, 3), 200, dtype=np.uint8)
        cv2.circle(clean_image, (50, 50), 25, (120, 120, 120), -1)
        cv2.circle(clean_image, (50, 50), 10, (10, 10, 10), -1)
        irregular_image = clean_image.copy()
        cv2.ellipse(irregular_image, (50, 50), (15, 7), 25, 0, 360, (10, 10, 10), -1)

        clean_diameter, clean_confidence = pupil_core._detect_pupil_in_eye(
            clean_image, landmarks, pupil_core.LEFT_IRIS_CENTER, pupil_core.LEFT_IRIS_BORDER,
            pupil_core.LEFT_EYE, 100, 100
        )
        irregular_diameter, irregular_confidence = pupil_core._detect_pupil_in_eye(
            irregular_image, landmarks, pupil_core.LEFT_IRIS_CENTER, pupil_core.LEFT_IRIS_BORDER,
            pupil_core.LEFT_EYE, 100, 100
        )

        self.assertIsNotNone(clean_diameter)
        self.assertIsNotNone(irregular_diameter)
        self.assertGreaterEqual(clean_confidence, 0.0)
        self.assertLessEqual(clean_confidence, 1.0)
        self.assertGreater(clean_confidence, irregular_confidence)

    def test_lighting_preflight_warns_for_dark_and_bright_frames_only(self):
        client = pupil_app.app.test_client()
        timestamps = [{"t": float(i), "image": ""} for i in range(10)]
        for value, expected_message in (
            (0, "too dim"),
            (255, "too bright"),
        ):
            image_uri = _image_data_uri(np.full((20, 20, 3), value, dtype=np.uint8))
            frames = [{"t": float(i), "image": image_uri} for i in range(10)]
            response = client.post("/analyze_session", json={"flash_time": 5.0, "frames": frames})
            payload = response.get_json()
            self.assertEqual(payload["status"], "warning")
            self.assertEqual(payload["warning_type"], "lighting")
            self.assertIn(expected_message, payload["message"])

        normal_uri = _image_data_uri(np.full((20, 20, 3), 128, dtype=np.uint8))
        frames = [{"t": float(i), "image": normal_uri} for i in range(10)]
        original_mesh = pupil_app.get_face_mesh
        original_detector = pupil_core.analyze_frame_bgr
        pupil_app.get_face_mesh = lambda: object()
        pupil_core.analyze_frame_bgr = lambda image, mesh, **kwargs: {"diameter": 50.0, "confidence": 0.9, "iris_diameter": 40.0}
        try:
            payload = client.post("/analyze_session", json={"flash_time": 5.0, "frames": frames}).get_json()
        finally:
            pupil_app.get_face_mesh = original_mesh
            pupil_core.analyze_frame_bgr = original_detector
        self.assertNotEqual(payload.get("status"), "warning")
        self.assertAlmostEqual(payload["average_confidence"], 0.9)


if __name__ == "__main__":
    unittest.main()