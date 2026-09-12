import numpy as np
import pandas as pd


def dataframe_from_samples(samples: list) -> pd.DataFrame:
    """Converts raw JSON samples list into a pandas DataFrame."""
    df = pd.DataFrame(samples)
    required_cols = ["time", "gyro_x", "gyro_y", "gyro_z"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required sensor field: '{col}'")
    return df.sort_values("time").reset_index(drop=True)


def estimate_sampling_rate(df: pd.DataFrame) -> float:
    """Estimates the average sampling frequency (Hz) from timestamp diffs."""
    time_deltas = df["time"].diff().dropna()
    valid_deltas = time_deltas[time_deltas > 0]
    if valid_deltas.empty:
        return 100.0
    mean_dt = valid_deltas.mean()
    return float(1.0 / mean_dt) if mean_dt > 0 else 100.0