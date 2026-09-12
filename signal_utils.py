import numpy as np
import pandas as pd
from scipy.signal import welch

REQUIRED_COLS = ["time", "gyro_x", "gyro_y", "gyro_z"]
NUMERIC_COLS = ["time", "gyro_x", "gyro_y", "gyro_z", "accel_x", "accel_y", "accel_z"]

# Physically plausible bounds for a phone gyroscope (rad/s). Real devices
# rarely exceed ~20 rad/s (~1150 deg/s) even during a fast flick; anything
# beyond that is almost certainly a bad reading (sensor glitch, unit
# mismatch, spoofed payload) rather than a real motor signal.
MAX_PLAUSIBLE_GYRO_RAD_S = 20.0


def dataframe_from_samples(samples: list) -> pd.DataFrame:
    """Converts raw JSON samples list into a validated pandas DataFrame.

    Raises ValueError with a specific, user-facing reason for any data
    quality problem — missing fields, non-numeric values, NaN/inf readings,
    or physically implausible sensor values — instead of letting them
    silently flow into the signal-processing pipeline and come back as a
    falsely reassuring "flag_doctor: false".
    """
    df = pd.DataFrame(samples)

    for col in REQUIRED_COLS:
        if col not in df.columns:
            raise ValueError(f"Missing required sensor field: '{col}'")

    # Coerce every numeric column we understand. Anything that fails to
    # parse becomes NaN, which lets us point at exactly which rows are bad
    # instead of leaking a raw Python TypeError to the client.
    present_numeric_cols = [c for c in NUMERIC_COLS if c in df.columns]
    for col in present_numeric_cols:
        coerced = pd.to_numeric(df[col], errors="coerce")
        bad_rows = df.index[coerced.isna() & df[col].notna()].tolist()
        if bad_rows:
            preview = bad_rows[:5]
            more = "..." if len(bad_rows) > 5 else ""
            raise ValueError(
                f"Field '{col}' contains non-numeric value(s) at row(s) {preview}{more}."
            )
        df[col] = coerced

    # Reject missing (NaN) values in required fields — e.g. a dropped key
    # in a single sample, which pandas would otherwise silently NaN-fill.
    required_block = df[REQUIRED_COLS]
    if required_block.isna().any().any():
        bad_cols = required_block.columns[required_block.isna().any()].tolist()
        raise ValueError(f"Missing/NaN readings found in field(s): {bad_cols}.")

    # Reject non-finite values (inf/-inf) that would otherwise poison
    # every downstream statistic (mean, RMS, PSD) with silent NaNs.
    if not np.isfinite(required_block.to_numpy()).all():
        raise ValueError("Non-finite (inf) readings found in required sensor fields.")

    # Reject physically implausible gyro readings rather than analyzing
    # obviously corrupted data as if it were a real motor signal.
    gyro_cols = [c for c in ["gyro_x", "gyro_y", "gyro_z"] if c in df.columns]
    gyro_block = df[gyro_cols].to_numpy()
    if (np.abs(gyro_block) > MAX_PLAUSIBLE_GYRO_RAD_S).any():
        raise ValueError(
            f"Gyro reading(s) exceed plausible sensor range "
            f"(±{MAX_PLAUSIBLE_GYRO_RAD_S} rad/s) — data looks corrupted."
        )

    return df.sort_values("time").reset_index(drop=True)


def estimate_sampling_rate(df: pd.DataFrame) -> float:
    """Estimates the average sampling frequency (Hz) from timestamp diffs."""
    time_deltas = df["time"].diff().dropna()
    valid_deltas = time_deltas[time_deltas > 0]
    if valid_deltas.empty:
        return 100.0
    mean_dt = valid_deltas.mean()
    return float(1.0 / mean_dt) if mean_dt > 0 else 100.0


def combined_psd(df: pd.DataFrame, fs: float):
    """Welch PSD summed across the three gyro axes.

    Critically, this runs Welch on each *signed* axis signal separately —
    NOT on the rectified vector magnitude sqrt(gx^2+gy^2+gz^2). Taking the
    magnitude first full-wave-rectifies an oscillating signal: negative
    half-cycles fold onto positive ones, which doubles the apparent
    frequency (a clean 5 Hz oscillation reads back as ~10 Hz, and a 7 Hz
    oscillation reads back as ~14 Hz — pushing it out of whichever band a
    caller is checking for entirely).

    Power is additive across orthogonal axes, so summing the three
    per-axis PSDs gives a magnitude-free, frequency-accurate combined
    spectrum without that distortion. Shared by tremor.py and
    vibration_response.py so both use the same, correctly-derived
    frequency estimate rather than duplicating (and risking diverging)
    the same math.
    """
    total_psd = None
    freqs = None
    for axis in ("gyro_x", "gyro_y", "gyro_z"):
        sig = df[axis].to_numpy()
        sig = sig - np.mean(sig)
        nperseg = min(len(sig), int(fs * 2)) or 1
        f, p = welch(sig, fs=fs, nperseg=nperseg)
        if total_psd is None:
            freqs, total_psd = f, p
        else:
            total_psd = total_psd + p
    return freqs, total_psd


def dominant_frequency(df: pd.DataFrame, fs: float, band=(1.0, 15.0)) -> float:
    """Returns the dominant frequency (Hz) within `band`, or 0.0 if the
    signal carries no meaningful power there (e.g. a flat/held-still trace).
    """
    freqs, psd = combined_psd(df, fs)
    band_mask = (freqs >= band[0]) & (freqs <= band[1])
    band_freqs = freqs[band_mask]
    band_psd = psd[band_mask]

    if len(band_psd) > 0 and np.sum(band_psd) > 0:
        dom_idx = np.argmax(band_psd)
        return float(band_freqs[dom_idx])
    return 0.0
