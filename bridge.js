/**
 * bridge.js
 * Manages phone motor actuation, sensor capture, and telemetry packaging.
 */

let selectedMode = "tremor"; // Options: "tremor", "vibration", "reflex"
let isRecording = false;
let samples = [];
let testStartTime = 0;
let currentVibeState = 0;
let activePulseIndex = -1;

const DEG_TO_RAD = Math.PI / 180.0;

// Setup test mode button listeners from code.html header
document.addEventListener("DOMContentLoaded", () => {
  const modePills = document.querySelectorAll("header .grid button");
  if (modePills.length >= 3) {
    modePills[0].addEventListener("click", () => switchMode("tremor", modePills, 0));
    modePills[1].addEventListener("click", () => switchMode("vibration", modePills, 1));
    modePills[2].addEventListener("click", () => switchMode("reflex", modePills, 2));
  }

  const startButton = document.getElementById("startBtn");
  if (startButton) {
    startButton.onclick = startAssessment;
  }
});

function switchMode(mode, buttons, activeIdx) {
  selectedMode = mode;
  buttons.forEach((btn, i) => {
    if (i === activeIdx) {
      btn.className = "py-1.5 px-2 rounded-xl bg-cyan-500/20 border border-cyan-400/60 text-[10px] font-mono font-semibold text-cyan-200 text-center flex items-center justify-center gap-1.5 shadow-[0_0_14px_rgba(14,165,233,0.3)] transition-all";
    } else {
      btn.className = "py-1.5 px-2 rounded-xl bg-slate-900/50 border border-slate-700/50 text-[10px] font-mono text-slate-400 text-center flex items-center justify-center gap-1.5 hover:text-slate-200 hover:border-slate-600 transition-all";
    }
  });
}

async function startAssessment() {
  // Sensor permissions for mobile browsers
  if (typeof DeviceMotionEvent !== "undefined" && typeof DeviceMotionEvent.requestPermission === "function") {
    try {
      const state = await DeviceMotionEvent.requestPermission();
      if (state !== "granted") {
        alert("Sensor permission denied.");
        return;
      }
    } catch (e) {
      console.warn("Sensor permission request bypassed:", e);
    }
  }

  showRecording();
  samples = [];
  isRecording = true;
  currentVibeState = 0;
  activePulseIndex = -1;
  testStartTime = performance.now();

  window.addEventListener("devicemotion", handleMotion);

  // Execute motor actuation sequence depending on mode
  if (selectedMode === "tremor") {
    // Mode 1: No vibration, hold still for 10s
    await wait(10000);
  } 
  else if (selectedMode === "vibration") {
    // Mode 2: Continuous motor vibration
    if ("vibrate" in navigator) navigator.vibrate(10000);
    currentVibeState = 1;
    await wait(10000);
    if ("vibrate" in navigator) navigator.vibrate(0);
    currentVibeState = 0;
  } 
  else if (selectedMode === "reflex") {
    // Mode 3: Rhythmic pulsed vibration (6 pulses)
    const numPulses = 6;
    for (let i = 0; i < numPulses; i++) {
      activePulseIndex = i;
      currentVibeState = 1;
      if ("vibrate" in navigator) navigator.vibrate(250); // 250ms buzz
      await wait(250);

      currentVibeState = 0;
      if ("vibrate" in navigator) navigator.vibrate(0);
      await wait(1200); // 1.2s delay between pulses
    }
    activePulseIndex = -1;
  }

  isRecording = false;
  window.removeEventListener("devicemotion", handleMotion);

  // Transmit data to bridge endpoint
  await transmitData();
}

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

  if (selectedMode === "vibration") {
    sample.vibration_active = currentVibeState;
  } else if (selectedMode === "reflex") {
    sample.pulse_index = activePulseIndex;
    sample.pulse_active = currentVibeState;
  }

  samples.push(sample);
}

async function transmitData() {
  document.getElementById("statusText").innerText = "Analyzing motor data...";

  try {
    const res = await fetch(`/api/forward/${selectedMode}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ samples: samples })
    });

    const data = await res.json();
    if (data.error) {
      alert("Error: " + data.error);
      resetToInstruction();
      return;
    }

    renderBackendResults(data);
  } catch (err) {
    alert("Connection error while analyzing data.");
    resetToInstruction();
  }
}

function renderBackendResults(data) {
  MOCK_DATA.consult = {
    flag_doctor: data.flag_doctor,
    dominant_freq: data.features?.dominant_freq_hz || 0.0,
    tremor_power_ratio: data.features?.tremor_power_ratio || 0.0,
    rms_amplitude: data.features?.rms || 0.0,
    jerk: data.features?.jerk || 0.0,
    sampling_rate: data.sampling_rate_hz || 100.0,
    filter: "Detrended & Bandpass Filtered (1–15 Hz)",
    reasons: data.reasons || ["Analysis complete."]
  };

  showResults(data.flag_doctor ? "consult" : "normal");
  document.getElementById("resDisclaimer").querySelector("p").innerText = data.disclaimer;
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}