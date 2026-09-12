import numpy as np
import pandas as pd
from scipy.signal import welch


def run(df: pd.DataFrame, fs: float) -> dict:
    """Processes tri-axial rotational velocity to assess physiological vs pathological tremor."""
    gx = df["gyro_x"].to_numpy()
    gy = df["gyro_y"].to_numpy()
    gz = df["gyro_z"].to_numpy()
    time = df["time"].to_numpy()

    # Calculate magnitude of angular velocity vector
    mag = np.sqrt(gx**2 + gy**2 + gz**2)
    mag_detrended = mag - np.mean(mag)

    # 1. Spectral Analysis via Welch periodogram
    nperseg = min(len(mag_detrended), int(fs * 2)) or 1
    freqs, psd = welch(mag_detrended, fs=fs, nperseg=nperseg)

    # Filter band of interest (1 to 15 Hz)
    band_mask = (freqs >= 1.0) & (freqs <= 15.0)
    band_freqs = freqs[band_mask]
    band_psd = psd[band_mask]

    if len(band_psd) > 0 and np.sum(band_psd) > 0:
        dom_idx = np.argmax(band_psd)
        dominant_freq = float(band_freqs[dom_idx])
        # Power ratio in tremor band (3.5 - 7.5 Hz) vs entire 1-15 Hz band
        tremor_band_mask = (band_freqs >= 3.5) & (band_freqs <= 7.5)
        tremor_power = np.sum(band_psd[tremor_band_mask])
        total_power = np.sum(band_psd)
        tremor_power_ratio = float(tremor_power / total_power) if total_power > 0 else 0.0
    else:
        dominant_freq = 0.0
        tremor_power_ratio = 0.0

    # 2. Kinematic Metrics: RMS amplitude & Jerk
    rms_amplitude = float(np.sqrt(np.mean(mag_detrended**2)))
    dt = np.diff(time)
    dt[dt == 0] = 1.0 / (fs or 100.0)
    jerk_vals = np.abs(np.diff(mag_detrended) / dt)
    jerk = float(np.mean(jerk_vals)) if len(jerk_vals) > 0 else 0.0

    # Clinical Flag Heuristic (Parkinsonian/essential tremor typically 4-7 Hz with high power concentration)
    reasons = []
    flag_doctor = False

    if 4.0 <= dominant_freq <= 7.0 and tremor_power_ratio > 0.40:
        flag_doctor = True
        reasons.append(
            f"Your hand shook steadily about {dominant_freq:.1f} times every second while holding still."
        )

    if jerk > 4.5:
        flag_doctor = True
        reasons.append("Your hand's movements were also jerky rather than smooth.")

    if not flag_doctor:
        reasons.append("Postural tremor micro-oscillations remain within expected physiological range.")
        reasons.append("Rotational jerk velocity variance indicates stable motor coordination across the trial.")

    return {
        "flag_doctor": flag_doctor,
        "features": {
            "dominant_freq_hz": round(dominant_freq, 2),
            "tremor_power_ratio": round(tremor_power_ratio, 3),
            "rms": round(rms_amplitude, 4),
            "jerk": round(jerk, 4),
        },
        "reasons": reasons,
    }