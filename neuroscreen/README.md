# NeuroScreen Suite — Unified Build

This folder merges your three separate deliverables into **one single-process
application**, with `mainui.html` acting as the bridge/hub between the two
diagnostic modules.

```
neuroscreen/
├── app.py               <- the ONE entry point (run this)
├── mainui.html           <- the hub page, served at "/"
├── requirements.txt
├── motor/                 <- formerly "Gyro" (Motor & Tremor screening)
│   ├── code.html
│   ├── bridge.js
│   └── analysis/           (tremor.py, reflex.py, vibration_response.py, ...)
└── pupil/                 <- formerly "Pupil_part" (Pupillary Light Reflex)
    ├── code.html
    ├── pupil_core.py
    └── models/face_landmarker.task
```

## How the bridge works

- `mainui.html` is served at `/`. Its **"Launch Motor Suite"** and
  **"Launch Optical Suite"** buttons navigate the browser to `/motor/` and
  `/pupil/`.
- `app.py` runs a single Flask app with two **Blueprints**:
  - `motor` → mounted at `/motor/*` (serves `motor/code.html`,
    `motor/bridge.js`, and all `/motor/api/...` analysis endpoints)
  - `pupil` → mounted at `/pupil/*` (serves `pupil/code.html` and the
    `/pupil/demo`, `/pupil/analyze_session`, `/pupil/export_report`,
    `/pupil/health` endpoints)
- Each module's original JS was updated to call its new prefixed URL
  (e.g. `fetch('/analyze_session')` → `fetch('/pupil/analyze_session')`),
  and each module's page now has a **"HUB"** link back to `/`.

No ports to juggle, no CORS hoops to jump through — it's one server, one
process, one URL space, with `mainui.html` as the front door.

## Running it

```bash
pip install -r requirements.txt
python3 app.py
```

Then open `http://localhost:5000/` — this loads the hub. From there:
- **Motor & Tremor Screening** → `http://localhost:5000/motor/`
- **Pupillary/Optical Screening** → `http://localhost:5000/pupil/`

## Notes

- `flask-cors` is optional — `app.py` degrades gracefully if it isn't
  installed (CORS isn't needed anymore since everything is same-origin).
- The pupil module's face-tracking model (`face_landmarker.task`) was
  relocated into `pupil/models/` so `pupil_core.py`'s relative path
  resolves correctly (in the original zip it lived one directory up from
  `app.py`, which would have 404'd).
- `matplotlib`, `opencv-python`, and `mediapipe` are only required for the
  pupil module's live camera analysis / synthetic demo endpoints.
