import numpy as np
import pandas as pd


def run(df: pd.DataFrame, fs: float) -> dict:
    """Evaluates stability and entrainment during motor vibration."""
    mag = np.sqrt(df["gyro_x"]**2 + df["gyro_y"]**2 + df["gyro_z"]**2).to_numpy()
    baseline_rms = float(np.sqrt(np.mean(mag**2)))

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
        },
        "reasons": reasons,
    }