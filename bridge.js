/**
 * bridge.js
 * Hardware control, motion event capture, and API routing.
 */

window.selectedMode = "tremor"; // "tremor" | "vibration" | "reflex" | "escalating"
window.selectedVibrationPattern = "consistent"; // "consistent" | "rhythmic"
let isRecording = false;
let samples = [];
let testStartTime = 0;
let currentVibeState = 0;
let activePulseIndex = -1;
let testCancelled = false;

const DEG_TO_RAD = Math.PI / 180.0;

window.selectMode = function (mode) {
  window.selectedMode = mode;

  const btnMap = {
    tremor: document.getElementById("btnModeTremor"),
    vibration: document.getElementById("btnModeVibration"),
    reflex: document.getElementById("btnModeReflex"),
    escalating: document.getElementById("btnModeEscalating"), // If added to code.html later
  };

  Object.entries(btnMap).forEach(([key, btn]) => {
    if (!btn) return;
    const dot = btn.querySelector("span:first-child");
    if (key === mode) {
      btn.className = "py-1.5 px-2 rounded-xl bg-cyan-500/20 border border-cyan-400/60 text-[10px] font-mono font-semibold text-cyan-200 text-center flex items-center justify-center gap-1.5 shadow-[0_0_14px_rgba(14,165,233,0.3)] transition-all cursor-pointer";
      if (dot) dot.className = "w-1.5 h-1.5 rounded-full bg-cyan-300 shadow-[0_0_6px_#38bdf8]";
    } else {
      btn.className = "py-1.5 px-2 rounded-xl bg-slate-900/50 border border-slate-700/50 text-[10px] font-mono text-slate-400 text-center flex items-center justify-center gap-1.5 hover:text-slate-200 hover:border-slate-600 transition-all cursor-pointer";
      if (dot) dot.className = "w-1.5 h-1.5 rounded-full bg-slate-500";
    }
  });

  if (window.onModeChanged) {
    window.onModeChanged(mode);
  }
};

window.selectVibrationPattern = function (pattern) {
  window.selectedVibrationPattern = pattern;

  const btnMap = {
    consistent: document.getElementById("btnPatternConsistent"),
    rhythmic: document.getElementById("btnPatternRhythmic"),
  };

  Object.entries(btnMap).forEach(([key, btn]) => {
    if (!btn) return;
    if (key === pattern) {
      btn.className = "py-1.5 px-2 rounded-xl bg-cyan-500/20 border border-cyan-400/60 text-[10px] font-mono font-semibold text-cyan-200 text-center flex items-center justify-center gap-1.5 shadow-[0_0_14px_rgba(14,165,233,0.3)] transition-all cursor-pointer";
    } else {
      btn.className = "py-1.5 px-2 rounded-xl bg-slate-900/50 border border-slate-700/50 text-[10px] font-mono text-slate-400 text-center flex items-center justify-center gap-1.5 hover:text-slate-200 hover:border-slate-600 transition-all cursor-pointer";
    }
  });
};

window.triggerStartAssessment = function () {
  startAssessment();
};

window.cancelCurrentTest = function () {
  testCancelled = true;
  isRecording = false;
  window.removeEventListener("devicemotion", handleMotion);
  if ("vibrate" in navigator) navigator.vibrate(0);
};

// ---------------------------------------------------------------------------
// Configurable Vibration Engine
//
// Supports two vibration "feels", selectable via window.selectedVibrationPattern:
//   'consistent' - a continuous-feeling buzz whose strength ramps over time
//   'rhythmic'   - distinct, evenly-spaced pulses whose strength ramps over time
//
// HARDWARE CAVEAT: the Web Vibration API (navigator.vibrate) is strictly
// on/off - it has no amplitude control, so JavaScript cannot make a phone's
// vibration motor spin "harder". What this engine does instead is vary the
// duty cycle (fraction of a short repeating window the motor is ON) - a
// higher duty cycle is felt as a stronger buzz even though motor speed never
// changes. 'consistent' uses a short ~50ms cycle so the on/off switching is
// imperceptible and it reads as one continuous buzz; 'rhythmic' uses a
// longer, fixed-length cycle so distinct pulses stay distinguishable even as
// their strength (pulse width) grows. Also note iOS Safari does not
// implement navigator.vibrate at all - the existing "vibrate" in navigator
// check already lets the rest of the test (recording/analysis) proceed
// silently without haptic feedback on those devices.
// ---------------------------------------------------------------------------

/**
 * @param {Object} cfg
 * @param {"consistent"|"rhythmic"} cfg.pattern
 * @param {number} cfg.totalMs         total stimulus duration in ms
 * @param {number} cfg.startIntensity  0..1, duty cycle at t=0
 * @param {number} cfg.endIntensity    0..1, duty cycle at t=totalMs
 * @param {number} [cfg.cycleMs]       on/off cycle length; defaults to 50ms
 *                                     for 'consistent', 400ms for 'rhythmic'
 */
async function runVibrationEngine(cfg) {
  const {
    pattern,
    totalMs,
    startIntensity,
    endIntensity,
    cycleMs = pattern === "rhythmic" ? 400 : 50,
  } = cfg;

  const canVibrate = "vibrate" in navigator;
  // Rhythmic mode caps duty below 100% so pulses never merge into a solid
  // buzz - otherwise "rhythmic" would stop feeling rhythmic near max intensity.
  const maxDuty = pattern === "rhythmic" ? 0.85 : 1.0;
  let elapsedMs = 0;

  // Perceived vibration strength does not scale linearly with duty cycle -
  // small duty-cycle increases near 0 feel like a much bigger jump than the
  // same-size increase near 1. An eased (squared) progress curve compensates
  // for that so the ramp *feels* smooth and continuous to a human hand,
  // rather than "nothing, nothing, nothing... sudden jump".
  function easeInQuad(t) {
    return t * t;
  }

  while (elapsedMs < totalMs) {
    if (testCancelled) break;

    const rawProgress = Math.min(1, elapsedMs / totalMs);
    const progress = easeInQuad(rawProgress);
    const intensity = startIntensity + (endIntensity - startIntensity) * progress;
    const duty = Math.max(0, Math.min(maxDuty, intensity));
    const onMs = Math.round(cycleMs * duty);
    const offMs = Math.max(1, cycleMs - onMs);

    currentVibeState = 1;
    if (canVibrate && onMs > 0) navigator.vibrate(onMs);
    await wait(onMs);

    currentVibeState = 0;
    if (canVibrate) navigator.vibrate(0);
    await wait(offMs);

    elapsedMs += onMs + offMs;
  }

  currentVibeState = 0;
  if (canVibrate) navigator.vibrate(0);
}

// ---------------------------------------------------------------------------
// Hardware Protocol Branches
// ---------------------------------------------------------------------------

async function runTremorProtocol() {
  // Passive hold-still test - no vibration stimulus by design.
  currentVibeState = 0;
  if ("vibrate" in navigator) navigator.vibrate(0);
  await wait(10000);
}

async function runVibrationProtocol() {
  // Sustained tactile-entrainment test: a strong, steady stimulus with a
  // gentle ramp-in so it isn't a jarring instant jolt. Respects the chosen
  // consistent/rhythmic pattern.
  await runVibrationEngine({
    pattern: window.selectedVibrationPattern,
    totalMs: 10000,
    startIntensity: 0.5,
    endIntensity: 0.9,
  });
}

async function runReflexProtocol() {
  const pulseCount = 6;
  for (let i = 0; i < pulseCount; i++) {
    if (testCancelled) break;

    activePulseIndex = i;
    currentVibeState = 1;
    if ("vibrate" in navigator) navigator.vibrate(250);
    await wait(250);

    currentVibeState = 0;
    if ("vibrate" in navigator) navigator.vibrate(0);
    await wait(1200);
  }
  activePulseIndex = -1;
}

async function runEscalatingProtocol() {
  // Progressive-tolerance test: intensity ramps from barely-perceptible to
  // maximum over the full 10s window, in the chosen consistent/rhythmic feel.
  await runVibrationEngine({
    pattern: window.selectedVibrationPattern,
    totalMs: 10000,
    startIntensity: 0.05,
    endIntensity: 1.0,
  });
}

// ---------------------------------------------------------------------------
// Main Controller
// ---------------------------------------------------------------------------

async function startAssessment() {
  if (typeof DeviceMotionEvent !== "undefined" && typeof DeviceMotionEvent.requestPermission === "function") {
    try {
      const state = await DeviceMotionEvent.requestPermission();
      if (state !== "granted") {
        alert("Sensor permission denied.");
        return;
      }
    } catch (e) {
      console.warn("Sensor bypass:", e);
    }
  }

  showRecording();
  samples = [];
  isRecording = true;
  testCancelled = false;
  currentVibeState = 0;
  activePulseIndex = -1;
  testStartTime = performance.now();

  window.addEventListener("devicemotion", handleMotion);

  if (window.selectedMode === "tremor") {
    await runTremorProtocol();
  } else if (window.selectedMode === "vibration") {
    await runVibrationProtocol();
  } else if (window.selectedMode === "reflex") {
    await runReflexProtocol();
  } else if (window.selectedMode === "escalating") {
    await runEscalatingProtocol();
  }

  isRecording = false;
  window.removeEventListener("devicemotion", handleMotion);

  if (testCancelled) return;

  if (samples.length < 10) {
    console.warn("Generating mock sensor frames (no hardware motion detected).");
    for (let i = 0; i < 50; i++) {
      samples.push({
        time: parseFloat((i * 0.02).toFixed(3)),
        gyro_x: 0.02,
        gyro_y: -0.01,
        gyro_z: 0.03,
        accel_x: 0.0,
        accel_y: 9.8,
        accel_z: 0.1,
        pulse_index: 0,
        pulse_active: 0,
        vibration_active: 0
      });
    }
  }

  await transmitData();
}

// ---------------------------------------------------------------------------
// Motion Event Logger
// ---------------------------------------------------------------------------

function handleMotion(event) {
  if (!isRecording) return;

  const rot = event.rotationRate || {};
  const acc = event.acceleration || {};
  const timeSeconds = (performance.now() - testStartTime) / 1000.0;

  const sample = {
    time: parseFloat(timeSeconds.toFixed(3)),
    gyro_x: parseFloat(((rot.beta || 0) * DEG_TO_RAD).toFixed(4)),
    gyro_y: parseFloat(((rot.gamma || 0) * DEG_TO_RAD).toFixed(4)),
    gyro_z: parseFloat(((rot.alpha || 0) * DEG_TO_RAD).toFixed(4)),
    accel_x: parseFloat((acc.x || 0).toFixed(4)),
    accel_y: parseFloat((acc.y || 0).toFixed(4)),
    accel_z: parseFloat((acc.z || 0).toFixed(4))
  };

  if (window.selectedMode === "vibration" || window.selectedMode === "escalating") {
    sample.vibration_active = currentVibeState;
  } else if (window.selectedMode === "reflex") {
    sample.pulse_index = activePulseIndex;
    sample.pulse_active = currentVibeState;
  }

  samples.push(sample);

  if (window.updateLiveGyroReadout) {
    window.updateLiveGyroReadout(sample);
  }
}

// ---------------------------------------------------------------------------
// API Dispatcher
// ---------------------------------------------------------------------------

async function transmitData() {
  const statusEl = document.getElementById("statusText");
  if (statusEl) statusEl.innerText = `Analyzing ${window.selectedMode} data...`;

  try {
    const res = await fetch(`/api/forward/${window.selectedMode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ samples: samples })
    });

    const data = await res.json();
    if (data.error) {
      alert(`Error: ${data.error}`);
      resetToInstruction();
      return;
    }

    renderBackendResults(data);
  } catch (err) {
    console.warn("Backend not reached, showing mock state:", err);
    if (window.showResults) window.showResults("consult");
  }
}

function renderBackendResults(data) {
  const resultKey = data.flag_doctor ? "consult" : "normal";
  const f = data.features || {};

  if (window.selectedMode === "tremor") {
    MOCK_DATA[resultKey] = {
      flag_doctor: data.flag_doctor,
      dominant_freq: f.dominant_freq_hz ?? 0,
      tremor_power_ratio: f.tremor_power_ratio ?? 0,
      rms_amplitude: f.rms ?? 0,
      jerk: f.jerk ?? 0,
      sampling_rate: data.sampling_rate_hz ?? 100.0,
      filter: "Detrended & Bandpass Filtered (1–15 Hz)",
      reasons: data.reasons || ["Analysis complete."]
    };
  } else if (window.selectedMode === "vibration") {
    MOCK_DATA[resultKey] = {
      flag_doctor: data.flag_doctor,
      dominant_freq: f.dominant_freq_hz ?? 0,
      tremor_power_ratio: f.variance ?? 0,
      rms_amplitude: f.mean_rms ?? 0,
      jerk: 0.0,
      sampling_rate: data.sampling_rate_hz ?? 100.0,
      filter: "Motor Entrainment Filter",
      reasons: data.reasons || ["Vibration test complete."]
    };
  } else if (window.selectedMode === "reflex") {
    MOCK_DATA[resultKey] = {
      flag_doctor: data.flag_doctor,
      dominant_freq: f.dominant_freq_hz ?? 0,
      tremor_power_ratio: 0.0,
      rms_amplitude: f.pulse_reaction_intensity ?? 0,
      jerk: 0.0,
      sampling_rate: data.sampling_rate_hz ?? 100.0,
      filter: "Perturbation Recovery Window",
      reasons: data.reasons || ["Reflex test complete."]
    };
  } else if (window.selectedMode === "escalating") {
    MOCK_DATA[resultKey] = {
      flag_doctor: data.flag_doctor,
      dominant_freq: f.dominant_freq_hz ?? 0,
      tremor_power_ratio: f.peak_variance ?? 0,
      rms_amplitude: f.baseline_variance ?? 0,
      jerk: 0.0,
      sampling_rate: data.sampling_rate_hz ?? 100.0,
      filter: "Escalating Variance Tolerance",
      reasons: data.reasons || ["Escalating test complete."]
    };
  }

  if (window.showResults) window.showResults(resultKey);

  const disclaimerBox = document.getElementById("resDisclaimer");
  if (disclaimerBox && data.disclaimer) {
    disclaimerBox.querySelector("p").innerText = data.disclaimer;
  }
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}