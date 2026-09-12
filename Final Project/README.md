# Pupillary Light Reflex (PLR) Module

A phone/webcam-based screening tool that measures how fast and how much a
person's pupil constricts in response to a light flash. This is a real,
published clinical signal (used in concussion/TBI screening and autonomic
nervous system assessment) — it is **not** general "organ health via pupil"
(which is pseudoscience). Framed correctly, this is a legitimate early
screening/wellness signal, not a diagnostic device.

## Files in this repo

| File | Purpose |
|---|---|
| `pupil_core.py` | All detection + analysis logic. No server, no camera dependency — importable and independently testable. |
| `app.py` | Flask backend. Wraps `pupil_core.py` as HTTP endpoints for a browser frontend. |
| `index.html` | Browser capture page. Uses `getUserMedia` to grab webcam frames, flashes the screen white as the light stimulus, POSTs frames to the backend. |
| `requirements.txt` | Python dependencies. |

## Core idea / architecture

```
Browser (index.html)
  │  getUserMedia() captures webcam frames as JPEG, timestamps each one
  │  triggers a full-white <div> flash at t = flash_time (default 2.0s)
  ▼
POST /analyze_session  { flash_time, frames: [{t, image(base64 jpg)}, ...] }
  ▼
Flask backend (app.py)
  │  for each frame: decode -> MediaPipe FaceMesh -> crop eye ROI
  ▼
pupil_core.analyze_frame_bgr()
  │  Otsu threshold + contour detection INSIDE the eye ROI to find the pupil
  ▼
pupil_core.compute_plr_metrics()
  │  compares pre-flash baseline diameter to post-flash minimum diameter
  ▼
Response: { timestamps, diameters_px, metrics }
```

## The one non-obvious technical detail (important context for any model
## extending this code)

MediaPipe's iris landmarks (indices 468–477 with `refine_landmarks=True`)
track the **iris** (the colored ring), not the **pupil** (the black center).
The iris does not meaningfully change size when light hits the eye — only
the pupil does. If you use iris-landmark distance as a proxy for "pupil
diameter," the diameter-over-time graph will be nearly flat and the whole
screening signal disappears.

The fix used here: MediaPipe is only used to **locate the eye region**
(`eye_bounding_box()` using the eye-contour landmark indices `LEFT_EYE` /
`RIGHT_EYE` in `pupil_core.py`). Inside that cropped region, a separate
classic-CV step finds the actual pupil:

1. Grayscale + Gaussian blur the eye crop.
2. Otsu's threshold (auto-picks a black/white cutoff — robust to lighting
   changes, no hand-tuned threshold value needed).
3. Find contours, keep only ones sized/shaped like a pupil (circularity +
   radius fraction of the crop + distance from crop center) — this rejects
   eyelashes, shadows, and eyebrow edges that also come out dark.
4. The best-scoring contour's `minEnclosingCircle` diameter is reported as
   the pupil diameter in pixels for that frame.

Any model modifying this code should preserve this two-stage design
(MediaPipe for eye localization, classic CV for pupil measurement) rather
than trying to read pupil size directly off MediaPipe landmarks.

## Metrics returned by `compute_plr_metrics()`

| Field | Meaning |
|---|---|
| `baseline_diameter_px` | Median pupil diameter before the flash. |
| `min_diameter_px` | Smallest pupil diameter after the flash. |
| `latency_sec` | Time from flash to the detected start of constriction. |
| `time_to_min_sec` | Time from flash to the smallest post-flash diameter. |
| `pct_constriction` | `(baseline - min) / baseline * 100` — how much the pupil shrank. |
| `baseline_diameter_mm`, `min_diameter_mm` | Pupil sizes estimated from per-frame iris calibration using an assumed 11.7 mm average iris diameter. |

The `_px` values are relative, session-local measurements. The `_mm` values
are estimates based on iris calibration and should not be treated as absolute
clinical measurements.

## Known limitations (be upfront about these, don't paper over them)

- **Estimated, not clinically validated.** The `_mm` values use iris-based
  calibration with an assumed 11.7 mm average human iris diameter; they have
  not been validated against a reference pupillometer.
- **Glasses/reflections** can confuse the thresholding step (specular
  highlights can be picked up as a false "pupil").
- **Single eye only** by default (`RIGHT_EYE`); `LEFT_EYE` indices exist in
  the file if bilateral comparison is wanted.
- **Threshold-based, not ML-based.** No trained model, no clinical
  validation dataset — this is a prototype/demo pipeline, not a validated
  diagnostic tool. Frame any product built on this as screening/wellness,
  not diagnosis.
- **Synthetic mode** (`pupil_core.run_synthetic_demo()` / `GET /demo`)
  exists specifically as a no-camera fallback — useful for demos, CI,
  or for another model to test changes without needing a real face/camera.

## Quick start

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 1. Verify the core logic with zero camera involved:
python3 pupil_core.py

# 2. Start the backend:
python3 app.py

# 3. Open index.html in a browser, allow camera access, click Start.
```

## API reference

### `GET /health`
Returns `{"status": "ok"}` if the server is up.

### `GET /demo`
Runs the fully synthetic pipeline (no camera/frames needed). Returns:
```json
{
  "metrics": { "baseline_diameter_px": ..., "min_diameter_px": ...,
               "latency_sec": ..., "pct_constriction": ... },
  "plot_png_base64": "<base64-encoded PNG>"
}
```

### `POST /analyze_session`
Request body:
```json
{
  "flash_time": 2.0,
  "frames": [
    {"t": 0.05, "image": "<base64 jpeg, with or without data-URI prefix>"},
    ...
  ]
}
```
Requires at least 10 frames. Returns:
```json
{
  "timestamps": [0.05, 0.11, ...],
  "diameters_px": [36.1, 35.8, null, ...],
  "diameters_px_raw": [36.1, 35.8, null, ...],
  "confidence": [0.92, 0.88, null, ...],
  "average_confidence": 0.90,
  "metrics": { "baseline_diameter_px": ..., "min_diameter_px": ...,
               "latency_sec": ..., "pct_constriction": ... }
}
```
`diameters_px` entries can be `null` for frames where no face/pupil was
detected — callers should handle gaps, not assume a dense series.
Pass optional `min_confidence` in the request body to exclude lower-confidence
frames from metric computation while retaining them in `diameters_px_raw`.

## Extending this module

- To add the left eye too: call `analyze_frame_bgr` a second time with
  `pupil_core.LEFT_EYE` instead of hardcoding `RIGHT_EYE` inside the
  function (currently right-eye is hardcoded — refactor to accept an eye
  argument if bilateral tracking is needed).
- To combine with a gyroscope/tremor module: this module's HTTP response
  shape (`timestamps` + a numeric series + a `metrics` dict) intentionally
  mirrors a typical sensor-analysis pipeline, so a combined dashboard can
  treat both modules' outputs uniformly.
