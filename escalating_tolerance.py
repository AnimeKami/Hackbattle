import numpy as np
import pandas as pd

from .signal_utils import dominant_frequency

def run(df: pd.DataFrame, fs: float) -> dict:
    """Analyzes gyro data to find the exact second motor control degrades."""
    mag = np.sqrt(df["gyro_x"]**2 + df["gyro_y"]**2 + df["gyro_z"]**2).to_numpy()
    time = df["time"].to_numpy()

    # Calculate rolling variance using a 0.5-second window
    window = int(fs * 0.5) if fs > 0 else 50 
    if len(mag) < window * 2:
        return {"flag_doctor": False, "features": {"dominant_freq_hz": 0.0}, "reasons": ["Insufficient data window."]}

    rolling_var = pd.Series(mag).rolling(window=window).var().fillna(0).to_numpy()
    
    # Establish a baseline using the first 2 seconds of low-intensity vibration
    baseline_var = np.mean(rolling_var[:int(fs * 2)])
    
    # Set a failure threshold: 3x the baseline variance or a hard minimum threshold
    threshold = max(baseline_var * 3.0, 0.15)

    # Find the first index where rolling variance exceeds the threshold
    failure_indices = np.where(rolling_var > threshold)[0]

    if len(failure_indices) > 0:
        loss_index = failure_indices[0]
        time_of_failure = time[loss_index]
        flag = True
        reasons = [f"Motor control degraded at {time_of_failure:.1f} seconds as vibration intensified."]
    else:
        time_of_failure = 10.0
        flag = False
        reasons = ["Motor control maintained throughout the full 10-second escalating intensity."]

    # Dominant frequency of the hand's rotational response across the trial,
    # computed the same way as the other three tests for consistency.
    dom_freq = dominant_frequency(df, fs)

    return {
        "flag_doctor": flag,
        "features": {
            "time_to_failure_sec": float(round(time_of_failure, 2)),
            "baseline_variance": float(round(baseline_var, 4)),
            "peak_variance": float(round(np.max(rolling_var), 4)),
            "dominant_freq_hz": round(dom_freq, 2)
        },
        "reasons": reasons
    }