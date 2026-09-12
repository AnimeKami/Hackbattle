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

import sys
import cv2
import numpy as np


def find_pupil_diameter(eye_roi_gray, min_radius_frac=0.05, max_radius_frac=0.5, return_confidence=False):
    """
    Given a grayscale crop of just the eye region, find the pupil (darkest
    circular blob) and return its diameter in pixels, or None if not found.
    Set return_confidence=True to also return the 0-1 contour confidence.
    """
    h, w = eye_roi_gray.shape[:2]
    if h == 0 or w == 0:
        return (None, 0.0) if return_confidence else None

    blurred = cv2.GaussianBlur(eye_roi_gray, (5, 5), 0)

    # Otsu picks a threshold automatically -> robust across lighting changes
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return (None, 0.0) if return_confidence else None

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

    confidence = float(np.clip(best_score, 0.0, 1.0)) if best is not None else 0.0
    return (best, confidence) if return_confidence else best


def eye_bounding_box(landmarks, indices, img_w, img_h, pad=4):
    """Compute clamped bounding box for given landmark indices."""
    xs = [landmarks[i].x * img_w for i in indices]
    ys = [landmarks[i].y * img_h for i in indices]
    x1, x2 = int(min(xs)) - pad, int(max(xs)) + pad
    y1, y2 = int(min(ys)) - pad, int(max(ys)) + pad
    return max(x1, 0), max(y1, 0), min(x2, img_w), min(y2, img_h)


# MediaPipe FaceMesh landmark indices:
# Left eye (subject's right eye, camera left):
LEFT_EYE = [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159, 160, 161, 246]
LEFT_IRIS_CENTER = 468
LEFT_IRIS_BORDER = [469, 470, 471, 472]

# Right eye (subject's left eye, camera right):
RIGHT_EYE = [362, 382, 381, 380, 374, 373, 390, 249, 263, 466, 388, 387, 386, 385, 384, 398]
RIGHT_IRIS_CENTER = 473
RIGHT_IRIS_BORDER = [474, 475, 476, 477]


def measure_iris_diameter_px(landmarks, img_w, img_h):
    """Return the mean iris diameter from available MediaPipe iris landmarks."""
    diameters = []
    for center_idx, border_indices in (
        (LEFT_IRIS_CENTER, LEFT_IRIS_BORDER),
        (RIGHT_IRIS_CENTER, RIGHT_IRIS_BORDER),
    ):
        if len(landmarks) <= max([center_idx] + border_indices):
            continue
        cx = landmarks[center_idx].x * img_w
        cy = landmarks[center_idx].y * img_h
        radii = [
            np.hypot(landmarks[i].x * img_w - cx, landmarks[i].y * img_h - cy)
            for i in border_indices
        ]
        diameter = 2.0 * float(np.mean(radii))
        if np.isfinite(diameter) and diameter > 0:
            diameters.append(diameter)
    return float(np.mean(diameters)) if diameters else None


def _detect_pupil_in_eye(frame_bgr, landmarks, center_idx, border_indices, contour_indices, img_w, img_h, eye_name="Eye"):
    """
    Detect pupil in a single eye using MediaPipe iris landmarks to isolate
    the iris region, then applying OpenCV Otsu/percentile thresholding and contour
    analysis to find the pupil circle.
    """
    cx = landmarks[center_idx].x * img_w
    cy = landmarks[center_idx].y * img_h
    if not (0 <= cx < img_w and 0 <= cy < img_h):
        return None, 0.0

    # Calculate iris radius from border landmarks
    radii = [np.hypot((landmarks[b].x * img_w - cx), (landmarks[b].y * img_h - cy)) for b in border_indices]
    iris_r = float(np.mean(radii))
    if iris_r < 1.0:
        return None, 0.0

    # Check for blink: vertical distance between eyelids
    ys = [landmarks[i].y * img_h for i in contour_indices]
    eye_height = max(ys) - min(ys)
    if eye_height < max(2.5, iris_r * 0.4):
        # Eyelids closed or blinking
        return None, 0.0

    # Crop around the iris center with appropriate margin
    pad = int(np.ceil(iris_r * 1.4))
    x1 = max(0, int(cx - pad))
    y1 = max(0, int(cy - pad))
    x2 = min(img_w, int(cx + pad + 1))
    y2 = min(img_h, int(cy + pad + 1))

    if (x2 - x1) < 4 or (y2 - y1) < 4:
        return None, 0.0

    crop = frame_bgr[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    local_cx = cx - x1
    local_cy = cy - y1

    # Circular mask representing the iris boundary
    mask = np.zeros(gray.shape, dtype=np.uint8)
    cv2.circle(mask, (int(round(local_cx)), int(round(local_cy))), int(round(iris_r)), 255, -1)

    iris_pixels = blurred[mask == 255]
    if len(iris_pixels) < 6:
        return None, 0.0

    # Adaptive thresholding:
    # Use Otsu on iris pixels, but if Otsu threshold exceeds median iris brightness
    # (common when pupil is small or constricted), fall back to midpoint of lower intensity range
    val_otsu, _ = cv2.threshold(iris_pixels, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    p_med = float(np.median(iris_pixels))
    p_min = float(np.percentile(iris_pixels, 5))
    th = val_otsu if val_otsu < p_med else (p_min + p_med) / 2.0

    _, thresh = cv2.threshold(blurred, int(th), 255, cv2.THRESH_BINARY_INV)
    pupil_mask = cv2.bitwise_and(thresh, mask)

    # Fill specular corneal reflection holes
    cnts_holes, _ = cv2.findContours(pupil_mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if cnts_holes:
        cv2.drawContours(pupil_mask, cnts_holes, -1, 255, -1)

    # Find candidate pupil contours
    contours, _ = cv2.findContours(pupil_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, 0.0

    best_d = None
    best_score = -1.0

    for c in contours:
        area = cv2.contourArea(c)
        if area < 1.0:
            continue
        (pcx, pcy), r = cv2.minEnclosingCircle(c)
        # Biological bounds: pupil must be smaller than iris, and reasonable minimum size
        if r < 0.5 or r > iris_r * 0.92:
            continue
        perim = cv2.arcLength(c, True)
        circ = (4.0 * np.pi * area / (perim * perim)) if perim > 0 else 0
        dist = np.hypot(pcx - local_cx, pcy - local_cy) / (iris_r + 1e-5)
        if dist > 0.75:
            continue
        score = circ - 0.4 * dist
        if score > best_score:
            best_score = score
            best_d = float(r * 2.0)

    confidence = float(np.clip(best_score, 0.0, 1.0)) if best_d is not None else 0.0
    return best_d, confidence


def analyze_frame_bgr(frame_bgr, face_mesh, return_details=False):
    """
    Run MediaPipe on one BGR frame and return the detected pupil diameter (px), or None.
    When return_details=True, return pupil and iris diameter metadata instead.
    Handles both MediaPipe Tasks FaceLandmarker and legacy FaceMesh solutions.
    Tolerates blinking, head pose, lighting changes, and uses both eyes when available.
    """
    if frame_bgr is None or frame_bgr.size == 0:
        return None

    h, w = frame_bgr.shape[:2]
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)

    if hasattr(face_mesh, "process"):
        results = face_mesh.process(rgb)
        if not results or not results.multi_face_landmarks:
            print("[PLR DIAG] Frame: No face detected (FaceMesh)", file=sys.stderr, flush=True)
            return None
        landmarks = results.multi_face_landmarks[0].landmark
    else:
        import mediapipe as mp
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        results = face_mesh.detect(image)
        if not results or not results.face_landmarks or len(results.face_landmarks) == 0:
            print("[PLR DIAG] Frame: No face detected (FaceLandmarker)", file=sys.stderr, flush=True)
            return None
        landmarks = results.face_landmarks[0]

    num_landmarks = len(landmarks)
    if num_landmarks < 468:
        print(f"[PLR DIAG] Frame: Incomplete landmarks ({num_landmarks})", file=sys.stderr, flush=True)
        return None

    # Check if iris landmarks are available (model with 478 landmarks)
    has_iris = num_landmarks >= 478

    if has_iris:
        d_left, score_left = _detect_pupil_in_eye(
            frame_bgr, landmarks, LEFT_IRIS_CENTER, LEFT_IRIS_BORDER, LEFT_EYE, w, h, eye_name="Left"
        )
        d_right, score_right = _detect_pupil_in_eye(
            frame_bgr, landmarks, RIGHT_IRIS_CENTER, RIGHT_IRIS_BORDER, RIGHT_EYE, w, h, eye_name="Right"
        )

        if d_left is not None and d_right is not None:
            # Both eyes detected: check consistency
            rel_diff = abs(d_left - d_right) / max(d_left, d_right)
            if rel_diff <= 0.40:
                d_final = (d_left + d_right) / 2.0
            else:
                d_final = d_left if score_left >= score_right else d_right
            print(f"[PLR DIAG] Face detected ({num_landmarks} lms): Left={d_left:.2f}px, Right={d_right:.2f}px -> Combined={d_final:.2f}px", file=sys.stderr, flush=True)
            confidence = float(np.clip((score_left + score_right) / 2.0, 0.0, 1.0))
            if return_details:
                return {"diameter": float(d_final), "iris_diameter": measure_iris_diameter_px(landmarks, w, h), "confidence": confidence}
            return float(d_final)
        elif d_left is not None:
            print(f"[PLR DIAG] Face detected ({num_landmarks} lms): Left={d_left:.2f}px, Right eye failed -> Used Left={d_left:.2f}px", file=sys.stderr, flush=True)
            if return_details:
                return {"diameter": float(d_left), "iris_diameter": measure_iris_diameter_px(landmarks, w, h), "confidence": float(np.clip(score_left, 0.0, 1.0))}
            return float(d_left)
        elif d_right is not None:
            print(f"[PLR DIAG] Face detected ({num_landmarks} lms): Right={d_right:.2f}px, Left eye failed -> Used Right={d_right:.2f}px", file=sys.stderr, flush=True)
            if return_details:
                return {"diameter": float(d_right), "iris_diameter": measure_iris_diameter_px(landmarks, w, h), "confidence": float(np.clip(score_right, 0.0, 1.0))}
            return float(d_right)
        else:
            print(f"[PLR DIAG] Face detected ({num_landmarks} lms): Both eyes failed contour/blink checks", file=sys.stderr, flush=True)
            return {"diameter": None, "iris_diameter": measure_iris_diameter_px(landmarks, w, h), "confidence": 0.0} if return_details else None
    else:
        # Fallback for 468-mesh without iris landmarks: use eye contour bounding boxes
        x1_r, y1_r, x2_r, y2_r = eye_bounding_box(landmarks, RIGHT_EYE, w, h)
        roi_r = frame_bgr[y1_r:y2_r, x1_r:x2_r]
        d_r, score_r = find_pupil_diameter(cv2.cvtColor(roi_r, cv2.COLOR_BGR2GRAY), return_confidence=True) if roi_r.size > 0 else (None, 0.0)

        x1_l, y1_l, x2_l, y2_l = eye_bounding_box(landmarks, LEFT_EYE, w, h)
        roi_l = frame_bgr[y1_l:y2_l, x1_l:x2_l]
        d_l, score_l = find_pupil_diameter(cv2.cvtColor(roi_l, cv2.COLOR_BGR2GRAY), return_confidence=True) if roi_l.size > 0 else (None, 0.0)

        if d_l is not None and d_r is not None:
            d_final = (d_l + d_r) / 2.0
        else:
            d_final = d_l if d_l is not None else d_r
        print(f"[PLR DIAG] Fallback 468 lms: Left={d_l}, Right={d_r} -> {d_final}", file=sys.stderr, flush=True)
        result = {
            "diameter": float(d_final) if d_final is not None else None,
            "iris_diameter": None,
            "confidence": float(np.clip((score_l + score_r) / 2.0, 0.0, 1.0)) if d_final is not None else 0.0,
        }
        return result if return_details else result["diameter"]


def _smooth_diameters(values, window=3):
    """Suppress isolated spikes without changing genuine transitions or gaps."""
    values = np.asarray(values, dtype=float)
    smoothed = values.copy()
    if window != 3:
        raise ValueError("only a 3-frame smoothing window is supported")
    for index in range(1, len(values) - 1):
        value, previous, following = values[index - 1:index + 2]
        if not (np.isfinite(value) and np.isfinite(previous) and np.isfinite(following)):
            continue
        neighbor_median = float(np.median([previous, following]))
        neighbors_are_consistent = abs(previous - following) <= max(1.0, 0.10 * abs(neighbor_median))
        is_isolated_spike = abs(value - neighbor_median) > max(1.0, 0.20 * abs(neighbor_median))
        if neighbors_are_consistent and is_isolated_spike:
            smoothed[index] = neighbor_median
    return smoothed


def compute_plr_metrics(timestamps, diameters, flash_time, iris_diameters=None):
    """
    timestamps: list of seconds (float)
    diameters: list of pixel diameters (None allowed for dropped frames)
    flash_time: the second at which the light stimulus fired
    Returns dict with baseline, min diameter, % constriction, onset latency,
    and time to minimum. If iris_diameters are supplied, calibrated mm fields
    are also returned using the average human iris diameter (11.7 mm).
    """
    if len(timestamps) != len(diameters):
        return {"error": "timestamps and diameters must have the same length"}
    if iris_diameters is not None and len(iris_diameters) != len(diameters):
        return {"error": "iris diameters must match pupil diameter length"}

    try:
        flash_time = float(flash_time)
        ts = np.asarray(timestamps, dtype=float)
        d_raw = np.array([np.nan if v is None else v for v in diameters], dtype=float)
    except (TypeError, ValueError):
        return {"error": "timestamps and diameters must be numeric"}
    if not np.isfinite(ts).all() or not np.isfinite(flash_time):
        return {"error": "timestamps and flash time must be finite"}
    # Diameters at or below the detector's validity floor are gaps, not pupil
    # sizes. Keep the caller's raw values untouched; only derived calculations
    # use this sanitized series.
    d_raw[~np.isfinite(d_raw) | (d_raw <= 0.5)] = np.nan

    # Metrics are chronological even if a caller delivered frames out of order.
    order = np.argsort(ts, kind="stable")
    ts = ts[order]
    d_raw = d_raw[order]
    d = _smooth_diameters(d_raw)
    iris = None
    if iris_diameters is not None:
        iris = np.array([np.nan if v is None else v for v in iris_diameters], dtype=float)[order]

    pre_mask = ts < flash_time
    post_mask = ts >= flash_time

    if pre_mask.sum() < 2 or post_mask.sum() < 2:
        return {"error": "not enough data before/after flash"}

    pre_d = d[pre_mask]
    post_d = d[post_mask]
    post_t = ts[post_mask]

    # Require enough real valid pupil measurements before and after flash
    if np.isfinite(d_raw[pre_mask]).sum() < 2 or np.isfinite(d_raw[post_mask]).sum() < 2:
        return {"error": "not enough valid pupil measurements"}

    baseline = float(np.nanmedian(pre_d))

    valid_post_mask = np.isfinite(post_d) & (post_d > 0.5)
    if valid_post_mask.sum() < 2:
        return {"error": "not enough valid pupil measurements"}

    valid_post_d = post_d[valid_post_mask]
    valid_post_t = post_t[valid_post_mask]

    min_idx = int(np.argmin(valid_post_d))
    min_diameter = float(valid_post_d[min_idx])
    time_to_min = float(valid_post_t[min_idx] - flash_time)

    # Constriction latency is the start of the response, not the time to its
    # maximum effect. Use the larger of one baseline-noise standard deviation
    # and a 5% baseline change so small measurement fluctuations are ignored.
    baseline_noise = float(np.nanstd(pre_d))
    onset_threshold = max(baseline_noise, 0.05 * abs(baseline))
    onset_mask = valid_post_d < (baseline - onset_threshold)
    if onset_mask.any():
        onset_idx = int(np.flatnonzero(onset_mask)[0])
        latency = float(valid_post_t[onset_idx] - flash_time)
    else:
        # Preserve a numeric latency for existing consumers when no onset is
        # detectable; the separate field still exposes the true min timing.
        latency = time_to_min

    pct_constriction = 0.0
    if baseline > 0:
        pct_constriction = float(100.0 * (baseline - min_diameter) / baseline)

    metrics = {
        "baseline_diameter_px": float(baseline),
        "min_diameter_px": float(min_diameter),
        "latency_sec": float(latency),
        "time_to_min_sec": float(time_to_min),
        "pct_constriction": float(pct_constriction),
    }

    metrics["baseline_diameter_mm"] = None
    metrics["min_diameter_mm"] = None
    if iris is not None:
        valid_scale = np.isfinite(iris) & (iris > 0)
        scaled = np.full_like(d, np.nan)
        scaled[valid_scale] = d[valid_scale] * (11.7 / iris[valid_scale])
        scaled_pre = scaled[pre_mask]
        if np.isfinite(scaled_pre).sum() >= 2:
            metrics["baseline_diameter_mm"] = float(np.nanmedian(scaled_pre))

        post_indices = np.flatnonzero(post_mask)
        selected_min_index = post_indices[valid_post_mask][min_idx]
        if np.isfinite(scaled[selected_min_index]):
            metrics["min_diameter_mm"] = float(scaled[selected_min_index])

    return metrics


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
