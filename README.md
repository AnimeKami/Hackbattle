# Motor Health Screen — Backend

A phone-sensor-based motor screening backend. It takes gyroscope (and optionally
accelerometer) readings captured during one of three short tests, compares the
movement pattern against an illustrative "healthy" reference profile, and
returns a plain-language result — including whether to suggest seeing a doctor.

This repo is **backend-only** (a REST API + analysis engine). It expects a
separate frontend (web page, mobile app, etc.) to capture phone sensor data
and POST it here for analysis.

> **This is a hackathon prototype and screening tool, not a medical device.**
> It does not diagnose anything. The reference thresholds used for comparison
> are illustrative placeholders based on general published ranges (tremor
> frequency bands, tactile reaction times) — **not clinically validated
> values**. A real deployment would need reference data collected from many
> healthy volunteers, on the same hardware, to calibrate these properly.

---| Phone buzzes in a rhythmic pattern (e.g. 6 short pulses); person reacts to each buzz | Per-pulse reaction time, consistency across pulses, missed reactions, and overshoot |

All three share the same underlying signal-processing pipeline
(`analysis/signal_utils.py`): detrend → bandpass filter (1–15Hz, tunable per
test) → combine axes by summing per-axis power spectra (not by taking the
magnitude of the raw signal first — see the code comments for why that
matters: it avoids a frequency-doubling artifact from signal rectification).

---

## Project structure

```
motor-health-backend/
├── app.py                     # Flask REST API
├── requirements.txt
├── analysis/
│   ├── __init__.py
│   ├── signal_utils.py        # shared filtering / preprocessing helpers
│   ├── tremor.py              # hold-still tremor test
│   ├── vibration_response.py  # continuous-vibration resistance test
│   └── reflex.py              # rhythmic-vibration reaction test
└── sample_data/
    └── generate_synthetic.py  # generates example JSON payloads for local testing
```

---

## Setup

```bash
git clone <this-repo-url>
cd motor-health-backend
python3 -m venv venv

## The three tests

| Test | Protocol | What it measures |
|---|---|---|
| **Tremor** (`/api/tremor`) | Hold the phone as still as possible for ~10s | Resting/postural tremor amplitude and frequency band (e.g. 4–6Hz Parkinsonian-like, 4–12Hz essential-tremor-like) |
| **Vibration Response** (`/api/vibration-response`) | Phone vibrates continuously; person tries to resist and hold it steady | How much residual movement gets through, and whether control gets *worse* over time (fatigue signal) |
| **Reflex** (`/api/reflex`) 
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Running the server

```bash
python app.py
```

The API will be available at `http://localhost:5000`.

## Generating example data (no phone needed)

```bash
python sample_data/generate_synthetic.py
```

This writes `example_tremor_payload.json`, `example_vibration_response_payload.json`,
and `example_reflex_payload.json` into `sample_data/`, which you can POST straight
to the API to see it working end to end without any real sensor data.

---

## API Reference

### `GET /api/health`
Basic healthcheck.

```bash
curl http://localhost:5000/api/health
```

### `POST /api/tremor`
**Request body:**
```json
{
  "samples": [
    {"time": 0.0,  "gyro_x": 0.01, "gyro_y": -0.02, "gyro_z": 0.00},
    {"time": 0.01, "gyro_x": 0.02, "gyro_y": -0.01, "gyro_z": 0.01}
  ]
}
```
- `time` is in seconds, must be present on every sample.
- `gyro_x/y/z` are in rad/s.
- Needs at least 10 samples (realistically, several hundred for a meaningful test).

**Example:**
```bash
curl -X POST http://localhost:5000/api/tremor \
  -H "Content-Type: application/json" \
  -d @sample_data/example_tremor_payload.json
```

**Response:**
```json
{
  "features": {
    "dominant_freq_hz": 5.0,
    "tremor_power_ratio": 0.997,
    "rms": 0.2717,
    "jerk": 7.3038
  },
  "flag_doctor": true,
  "reasons": [
    "Your hand shook steadily about 5.0 times every second while holding still. ...",
    "Your hand's movements were also jerky rather than smooth."
  ],
  "sampling_rate_hz": 100.0,
  "disclaimer": "This is a screening tool, not a medical diagnosis. Always consult a qualified doctor about health concerns."
}
```

### `POST /api/vibration-response`
Same request shape as `/api/tremor`, plus an optional `vibration_active` field
(0 or 1) per sample marking when the phone was actually buzzing. If present,
only that window is analyzed.

### `POST /api/reflex`
Same request shape, but **every sample must include**:
- `pulse_index` (integer, which buzz cycle this sample belongs to; `-1` if outside any test cycle)
- `pulse_active` (0 or 1, whether the buzz was firing at this instant)

A frontend capturing this data should compute these two fields itself while
tagging samples in real time (see the "Frontend contract" section below).

**Response includes an additional `pulses` array** with per-buzz detail:
```json
{
  "pulses": [
    {"pulse_index": 0, "pulse_start_time": 0.0, "reaction_lag": 0.25, "peak_amplitude": 0.105, "missed": false},
    {"pulse_index": 1, "pulse_start_time": 0.7, "reaction_lag": null, "peak_amplitude": 0.058, "missed": true}
  ],
  "summary": {
    "num_pulses": 6,
    "missed_count": 1,
    "missed_fraction": 0.17,
    "mean_reaction_lag": 0.21,
    "reaction_lag_std": 0.03,
    "mean_peak_amplitude": 0.13
  },
  "flag_doctor": false,
  "reasons": ["Your hand reacted quickly and consistently to each buzz, ..."]
}
```

---

## Frontend contract

This backend doesn't care how sensor data was captured, as long as the JSON
shape above is respected. A typical frontend flow:

1. Trigger the phone's vibration in the desired pattern (continuous for
   vibration-response, pulsed for reflex — e.g. via the Web Vibration API,
   `navigator.vibrate()`, on Android Chrome; iOS Safari does not support this
   API, so an iOS frontend needs a native wrapper to access the Taptic Engine).
2. Simultaneously record gyroscope (and optionally accelerometer) readings
   with timestamps, tagging `vibration_active` / `pulse_index` / `pulse_active`
   as appropriate for the test type.
3. POST the collected samples as JSON to the relevant endpoint above.
4. Display `reasons` and `flag_doctor` to the user, and the underlying
   `features`/`summary`/`pulses` for any charts you want to draw.

---

## Known limitations (worth being upfront about, e.g. in a hackathon Q&A)

- **Reference thresholds are placeholders.** They're grounded in general
  published ranges, not device-calibrated clinical data.
- **Reflex detection can produce false positives.** Residual motion from one
  pulse's response can occasionally bleed into the next pulse's detection
  window, registering an artificially short reaction time. A refractory
  period (ignoring the first ~50ms of each window) would reduce this; not
  yet implemented.
- **No persistence layer.** Every request is stateless — there's no database,
  user accounts, or history tracking. Trend-over-multiple-sessions analysis
  (arguably more clinically meaningful than a single reading) would need this
  added.
- **iOS vibration limitation.** `navigator.vibrate()` isn't supported on iOS
  Safari; any iOS frontend needs a native shell to trigger real vibration.

---

## Disclaimer

This project is a screening/wellness tool built for a hackathon. It is not a
medical device, has not been clinically validated, and must not be used as a
substitute for professional medical advice, diagnosis, or treatment.
