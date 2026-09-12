"""
pupil_core.py
Core logic for Pupillary Light Reflex (PLR) screening.

Key technical point (say this to judges): MediaPipe's iris landmarks track the
IRIS (colored ring), not the PUPIL (black center) — the iris barely changes
size, so if you report iris width as "pupil diameter" your graph will look
flat and your demo will fail. This module uses MediaPipe only to find the eye
region, then runs a threshold + contour pass INSIDE that region to find the
actual pupil (the darkest, most circular blob), which is what actually
shrinks/grows when light hits the eye.
"""

import cv2
import numpy as np


def find_pupil_diameter(eye_roi_gray, min_radius_frac=0.05, max_radius_frac=0.5):
    """
    Given a grayscale crop of just the eye region, find the pupil (darkest
    circular blob) and return its diameter in pixels, or None if not found.
    """
    h, w = eye_roi_gray.shape[:2]
    if h == 0 or w == 0:
        return None

    blurred = cv2.GaussianBlur(eye_roi_gray, (5, 5), 0)

    # Otsu picks a threshold automatically -> robust across lighting changes
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best = None
    best_score = -1
    min_r = min_radius_frac * min(h, w)
    max_r = max_radius_frac * min(h, w)

    for c in contours:
        area = cv2.contourArea(c)
        if area < 10:
            continue
        (x, y), radius = cv2.minEnclosingCircle(c)
        if radius < min_r or radius > max_r:
            continue
        # circularity: how close the blob is to a perfect circle (pupils are round;
        # eyelashes/shadows usually are not)
        perimeter = cv2.arcLength(c, True)
        if perimeter == 0:
            continue
        circularity = 4 * np.pi * area / (perimeter ** 2)
        # prefer blobs near the center of the crop too
        center_dist = np.hypot(x - w / 2, y - h / 2) / (min(h, w) / 2)
        score = circularity - 0.3 * center_dist
        if score > best_score:
            best_score = score
            best = radius * 2  # diameter

    return best


def eye_bounding_box(landmarks, indices, img_w, img_h, pad=6):
    xs = [landmarks[i].x * img_w for i in indices]
    ys = [landmarks[i].y * img_h for i in indices]
    x1, x2 = int(min(xs)) - pad, int(max(xs)) + pad
    y1, y2 = int(min(ys)) - pad, int(max(ys)) + pad
    return max(x1, 0), max(y1, 0), x2, y2


# MediaPipe FaceMesh eye-contour landmark indices (with refine_landmarks=True)
LEFT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
RIGHT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]


def analyze_frame_bgr(frame_bgr, face_mesh):
    """Run MediaPipe on one BGR frame, return pupil diameter (px) for the right eye, or None."""
    h, w = frame_bgr.shape[:2]
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(rgb)
    if not results.multi_face_landmarks:
        return None
    landmarks = results.multi_face_landmarks[0].landmark
    x1, y1, x2, y2 = eye_bounding_box(landmarks, RIGHT_EYE, w, h)
    roi = frame_bgr[y1:y2, x1:x2]
    if roi.size == 0:
        return None
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    return find_pupil_diameter(gray)


def compute_plr_metrics(timestamps, diameters, flash_time):
    """
    timestamps: list of seconds (float)
    diameters: list of pixel diameters (None allowed for dropped frames)
    flash_time: the second at which the light stimulus fired
    Returns dict with baseline, min diameter, % constriction, and latency.
    """
    ts = np.array(timestamps)
    d = np.array([np.nan if v is None else v for v in diameters], dtype=float)

    pre_mask = ts < flash_time
    post_mask = ts >= flash_time

    if pre_mask.sum() < 2 or post_mask.sum() < 2:
        return {"error": "not enough data before/after flash"}

    baseline = np.nanmedian(d[pre_mask])
    post_d = d[post_mask]
    post_t = ts[post_mask]

    min_idx = np.nanargmin(post_d)
    min_diameter = post_d[min_idx]
    latency = post_t[min_idx] - flash_time

    pct_constriction = 0.0
    if baseline and not np.isnan(baseline) and baseline > 0:
        pct_constriction = 100.0 * (baseline - min_diameter) / baseline

    return {
        "baseline_diameter_px": float(baseline),
        "min_diameter_px": float(min_diameter),
        "latency_sec": float(latency),
        "pct_constriction": float(pct_constriction),
    }


# ---------------------------------------------------------------------------
# Synthetic mode: lets you test/demo the WHOLE pipeline with no camera at all.
# This is your stage backup if live face/webcam detection ever fails.
# ---------------------------------------------------------------------------

def generate_synthetic_session(duration=6.0, fps=20, flash_time=2.0,
                                baseline_radius=18.0, min_radius=9.0,
                                constrict_time=0.3, noise=0.4):
    """Simulate a pupil that constricts sharply after the flash, then slightly
    redilates -- like a real PLR curve -- with sensor noise added."""
    n = int(duration * fps)
    timestamps = [i / fps for i in range(n)]
    diameters = []
    rng = np.random.default_rng(42)
    for t in timestamps:
        if t < flash_time:
            r = baseline_radius
        elif t < flash_time + constrict_time:
            frac = (t - flash_time) / constrict_time
            r = baseline_radius - frac * (baseline_radius - min_radius)
        else:
            # slow partial redilation
            redilate_frac = min(1.0, (t - flash_time - constrict_time) / 2.5)
            r = min_radius + redilate_frac * 0.4 * (baseline_radius - min_radius)
        r += rng.normal(0, noise)
        diameters.append(max(2.0, r) * 2)  # diameter, px
    return timestamps, diameters


def run_synthetic_demo(out_csv="plr_synthetic.csv", out_plot="plr_synthetic.png"):
    import csv
    flash_time = 2.0
    timestamps, diameters = generate_synthetic_session(flash_time=flash_time)

    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp_sec", "pupil_diameter_px"])
        for t, d in zip(timestamps, diameters):
            w.writerow([t, d])

    metrics = compute_plr_metrics(timestamps, diameters, flash_time)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.figure(figsize=(8, 4))
    plt.plot(timestamps, diameters, label="Pupil diameter (px)")
    plt.axvline(flash_time, color="red", linestyle="--", label="Light flash")
    plt.xlabel("Time (s)")
    plt.ylabel("Pupil diameter (px)")
    plt.title("Pupillary Light Reflex (synthetic demo data)")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_plot, dpi=120)
    plt.close()

    return metrics, out_csv, out_plot


if __name__ == "__main__":
    metrics, csv_path, plot_path = run_synthetic_demo()
    print("Synthetic PLR run complete.")
    print("Metrics:", metrics)
    print("CSV saved to:", csv_path)
    print("Plot saved to:", plot_path)
