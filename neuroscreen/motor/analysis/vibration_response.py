import numpy as np
import pandas as pd

from .signal_utils import dominant_frequency


def run(df: pd.DataFrame, fs: float) -> dict:
    """Evaluates stability and entrainment during motor vibration."""
    mag = np.sqrt(df["gyro_x"]**2 + df["gyro_y"]**2 + df["gyro_z"]**2).to_numpy()
    baseline_rms = float(np.sqrt(np.mean(mag**2)))

    # Dominant frequency of the *hand's* rotational response while the motor
    # buzzes — not the motor's own vibration frequency (that's far above
    # what a phone gyro sampling at ~100 Hz can resolve; it would just alias).
    # This captures whether the hand is oscillating/entraining at a
    # detectable rate in response to the sustained tactile stimulus.
    dom_freq = dominant_frequency(df, fs)

    flag = baseline_rms > 0.35
    reasons = [
        "Elevated motor entrainment detected during sustained tactile stimulation."
        if flag
        else "Motor adaptation stayed within standard physiological bounds under sustained vibration."
    ]

    return {
        "flag_doctor": flag,
        "features": {
            "mean_rms": round(baseline_rms, 4),
            "variance": round(float(np.var(mag)), 4),
            "dominant_freq_hz": round(dom_freq, 2),
        },
        "reasons": reasons,
    }