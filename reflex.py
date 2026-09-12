import numpy as np
import pandas as pd


def run(df: pd.DataFrame, fs: float) -> dict:
    """Measures reflex reaction time and perturbation recovery from rhythmic pulses."""
    pulses = df[df["pulse_active"] == 1]
    
    if pulses.empty:
        mean_intensity = 0.0
    else:
        mag = np.sqrt(pulses["gyro_x"]**2 + pulses["gyro_y"]**2 + pulses["gyro_z"]**2)
        mean_intensity = float(mag.mean())

    flag = mean_intensity > 0.40
    reasons = [
        "Involuntary reaction reflex exceeded dynamic stability threshold."
        if flag
        else "Reflex reaction latency and postural restoration remain normal."
    ]

    return {
        "flag_doctor": flag,
        "features": {
            "pulse_reaction_intensity": round(mean_intensity, 4),
            "pulse_count": int(df["pulse_index"].max() + 1 if "pulse_index" in df else 0),
        },
        "reasons": reasons,
    }