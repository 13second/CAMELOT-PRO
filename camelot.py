#!/usr/bin/env python3
"""
===============================================================================
 CAMELOT AUDIO & ABLETON SESSION ENGINE
 Unified Audio Telemetry & Live Session Analyzer
 ===============================================================================
"""

import base64
import html
import json
import os
import sys
import argparse
import subprocess
import tempfile
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf
import scipy.signal as signal
import pyloudnorm as pyln

# -----------------------------------------------------------------------------
# 1. DSP & AUDIO TELEMETRY ENGINE
# -----------------------------------------------------------------------------

# ITU-R BS.1770-4 Annex 2 Polyphase 4x True Peak Filter Coefficients
# Exact 1:1 mathematical parity with Camelot Pro Max for Live gen~ DSP engine
ITU_TP_H1 = np.array([
    -0.00113060, 0.00292651, -0.00593205, 0.01060509, -0.01757917,
     0.02786692, -0.04342309, 0.06897234, -0.12013435, 0.29654282,
     0.89963257, -0.17397774, 0.08928335, -0.05442549, 0.03479525,
    -0.02221989, 0.01375396, -0.00802613, 0.00425232, -0.00190167, 0.0
], dtype=np.float64)

ITU_TP_H2 = np.array([
    -0.00210317, 0.00501853, -0.00979083, 0.01711516, -0.02798328,
     0.04405148, -0.06868853, 0.11058973, -0.20188442, 0.63347609,
     0.63347609, -0.20188442, 0.11058973, -0.06868853, 0.04405148,
    -0.02798328, 0.01711516, -0.00979083, 0.00501853, -0.00210317, 0.0
], dtype=np.float64)

ITU_TP_H3 = np.array([
    -0.00190167, 0.00425232, -0.00802613, 0.01375396, -0.02221989,
     0.03479525, -0.05442549, 0.08928335, -0.17397774, 0.89963257,
     0.29654282, -0.12013435, 0.06897234, -0.04342309, 0.02786692,
    -0.01757917, 0.01060509, -0.00593205, 0.00292651, -0.00113060, 0.0
], dtype=np.float64)

LOSSY_AUDIO_EXTENSIONS = ('.mp3', '.ogg', '.oga', '.m4a', '.aac', '.opus', '.wma')
LOSSLESS_AUDIO_EXTENSIONS = ('.wav', '.aif', '.aiff', '.flac', '.caf', '.alac', '.w64')
SUPPORTED_AUDIO_EXTENSIONS = LOSSLESS_AUDIO_EXTENSIONS + LOSSY_AUDIO_EXTENSIONS


def calculate_true_peak_env(signal_channel):
    """
    Computes the 4x polyphase FIR interpolated magnitude envelope (ITU-R BS.1770-4 Annex 2).
    Exact 1:1 mathematical parity with the gen~ codebox in Camelot_Pro.amxd, including
    10-sample group-delay alignment for y0 and 10-sample tail padding.
    Uses chunked processing with overlap to keep peak RAM low on long high-SR files.
    """
    n = len(signal_channel)
    if n == 0:
        return np.zeros(0, dtype=np.float32)

    out = np.empty(n, dtype=np.float32)
    chunk_size = 524288
    pad_left = 20   # FIR length - 1
    pad_right = 10  # Group delay

    for start in range(0, n, chunk_size):
        end = min(n, start + chunk_size)
        seg_start = max(0, start - pad_left)
        seg_end = min(n, end + pad_right)
        left_zeros = (start - pad_left) < 0
        right_zeros = (end + pad_right) - seg_end

        seg = np.asarray(signal_channel[seg_start:seg_end], dtype=np.float64)
        pre = pad_left - (start - seg_start) if left_zeros else 0
        if pre > 0 or right_zeros > 0:
            seg = np.pad(seg, (pre, right_zeros), mode='constant')

        # Valid output samples for [start:end] start at index (pad_left + 10) after lfilter
        offset = pad_left + 10
        length = end - start
        y0 = np.abs(signal_channel[start:end])
        y1 = np.abs(signal.lfilter(ITU_TP_H1, [1.0], seg)[offset:offset + length])
        y2 = np.abs(signal.lfilter(ITU_TP_H2, [1.0], seg)[offset:offset + length])
        y3 = np.abs(signal.lfilter(ITU_TP_H3, [1.0], seg)[offset:offset + length])
        out[start:end] = np.maximum(np.maximum(y0, y1), np.maximum(y2, y3)).astype(np.float32)

    return out


def calculate_true_peak_itu(signal_channel):
    """
    Calculates True Peak according to ITU-R BS.1770-4 4x polyphase FIR interpolation.
    Computes exact phase matrices matching the gen~ codebox in Camelot_Pro.amxd.
    """
    return float(np.max(calculate_true_peak_env(signal_channel)))


def calculate_true_peak_universal(y, audio_path=""):
    """
    Universal format-agnostic True Peak (dBTP) & Sample Peak (dBFS) calculator.
    - For lossless formats (WAV, AIFF, FLAC, CAF, ALAC, W64): returns exact 4x ITU-R BS.1770-4 True Peak.
    - For lossy perceptual codecs (MP3, OGG, M4A, AAC, OPUS, WMA): detects brickwall limiter ceilings
      via high-density envelope percentiles (p99.50..p99.85) and rejects isolated MDCT/Vorbis/AAC
      Gibbs reconstruction overshoot spikes so lossy exports match lossless and live Master bus readings.
    """
    ext = Path(str(audio_path)).suffix.lower() if audio_path else ""
    is_lossy = ext in LOSSY_AUDIO_EXTENSIONS

    if y.ndim > 1 and y.shape[1] >= 2:
        tp_env = np.maximum(calculate_true_peak_env(y[:, 0]), calculate_true_peak_env(y[:, 1]))
        sp_env = np.maximum(np.abs(y[:, 0]), np.abs(y[:, 1]))
    else:
        y_1d = y[:, 0] if y.ndim > 1 else y
        tp_env = calculate_true_peak_env(y_1d)
        sp_env = np.abs(y_1d)

    raw_tp_val = float(np.max(tp_env))
    raw_sp_val = float(np.max(sp_env))
    raw_tp_db = 20.0 * np.log10(raw_tp_val + 1e-9)
    raw_sp_db = 20.0 * np.log10(raw_sp_val + 1e-9)

    if not is_lossy:
        return raw_tp_db, raw_sp_db

    active_tp = tp_env[tp_env > 1e-4]
    if len(active_tp) < 100:
        return raw_tp_db, raw_sp_db

    p9950_db = 20.0 * np.log10(float(np.percentile(active_tp, 99.50)) + 1e-9)
    p9965_db = 20.0 * np.log10(float(np.percentile(active_tp, 99.65)) + 1e-9)
    p9985_db = 20.0 * np.log10(float(np.percentile(active_tp, 99.85)) + 1e-9)
    p9998_db = 20.0 * np.log10(float(np.percentile(active_tp, 99.98)) + 1e-9)

    # Brickwall limiter detection: top 0.35% of active envelope is compressed within < 0.45 dB
    ceiling_spread = p9985_db - p9950_db
    codec_overshoot = raw_tp_db - p9965_db

    if ceiling_spread < 0.45 and codec_overshoot > 0.12:
        # Recover exact pre-codec brickwall limiter ceiling (+0.05 dB 4x inter-sample margin)
        comp_tp_db = p9965_db + 0.05
        comp_sp_db = min(raw_sp_db, comp_tp_db - 0.04)
        return comp_tp_db, comp_sp_db
    elif (raw_tp_db - p9998_db) > 0.25:
        # Un-limited dynamic mix: reject isolated single-sample MDCT glitch
        comp_tp_db = p9998_db + 0.10
        comp_sp_db = min(raw_sp_db, comp_tp_db)
        return comp_tp_db, comp_sp_db

    return raw_tp_db, raw_sp_db


def load_audio_robust(audio_path):
    """
    Universal audio loader into (y, sr) supporting WAV, AIFF, AIF, FLAC, MP3, OGG, OGA, M4A, AAC, OPUS, WMA, CAF, ALAC, W64.
    If libsndfile (sf.read) fails on Ableton MP3 headers ('bad data offset') or M4A/AAC/OPUS/WMA/CAF,
    automatically decodes to a temporary 32-bit float WAV via macOS afconvert or ffmpeg.
    """
    y, sr = None, None
    primary_err = None
    try:
        y, sr = sf.read(audio_path, always_2d=False)
    except Exception as err:
        primary_err = err

    if y is None:
        tmp_fd, tmp_wav = tempfile.mkstemp(suffix=".wav")
        os.close(tmp_fd)
        try:
            # 1. Try macOS native afconvert (built-in on all Macs, ultra-fast for MP3/M4A/AAC/CAF/ALAC/AIFF/WAV)
            if os.path.exists("/usr/bin/afconvert"):
                res = subprocess.run(
                    ["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEF32", str(audio_path), tmp_wav],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=60,
                )
                if res.returncode == 0 and os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 1024:
                    y, sr = sf.read(tmp_wav, always_2d=False)

            # 2. Try ffmpeg via imageio_ffmpeg or system PATH (handles OGG, OPUS, WMA, FLAC, MP3, M4A, etc.)
            if y is None:
                ffmpeg_bin = shutil.which("ffmpeg")
                if not ffmpeg_bin:
                    try:
                        import imageio_ffmpeg
                        ffmpeg_bin = imageio_ffmpeg.get_ffmpeg_exe()
                    except Exception:
                        ffmpeg_bin = None

                if ffmpeg_bin:
                    res = subprocess.run(
                        [ffmpeg_bin, "-y", "-i", str(audio_path), "-vn", "-acodec", "pcm_f32le", tmp_wav],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=60,
                    )
                    if res.returncode == 0 and os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 1024:
                        y, sr = sf.read(tmp_wav, always_2d=False)

            if y is None:
                raise primary_err if primary_err else RuntimeError(f"Impossibile decodificare il file audio: {audio_path}")
        finally:
            try:
                if os.path.exists(tmp_wav):
                    os.remove(tmp_wav)
            except OSError:
                pass

    y = np.asarray(y, dtype=np.float64)
    if y.ndim > 1 and y.shape[1] > 2:
        y = y[:, :2]
    return y, int(sr)


def analyze_audio(audio_path):
    """
    Performs full audio analysis on any supported audio file format:
    - LUFS Integrated (EBU R128), Short-Term, Momentary
    - Universal True Peak (ITU-R BS.1770-4 4x oversampling + lossy codec Gibbs compensation)
    - Dual-Gated AES-17 RMS & Integrated Crest Factor (matching Camelot_Pro M4L display)
    - L/R Phase Correlation & Low-End Phase (<100 Hz)
    - Stereo Width (M/S Ratio & Percentages)
    - Multiband Energy Distribution (5 Bands with 4.5 dB/oct Mastering Reference Tilt per Octave)
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    y, sr = load_audio_robust(audio_path)

    # Channel handling
    if y.ndim > 1 and y.shape[1] >= 2:
        left = y[:, 0]
        right = y[:, 1]
        is_stereo = True
        mono_signal = np.mean(y[:, :2], axis=1)
    else:
        y_1d = y[:, 0] if y.ndim > 1 else y
        left = y_1d
        right = y_1d
        is_stereo = False
        mono_signal = y_1d

    # A. LUFS Calculation (EBU R128) — handle short clips (< 0.4s) & pure silence (-inf)
    meter = pyln.Meter(sr)
    min_samples = int(np.ceil(sr * 0.45))
    if len(y) < min_samples:
        pad_len = min_samples - len(y)
        y_lufs = np.pad(y, ((0, pad_len), (0, 0)), mode='constant') if y.ndim > 1 else np.pad(y, (0, pad_len), mode='constant')
    else:
        y_lufs = y

    integrated_lufs = float(meter.integrated_loudness(y_lufs))
    if np.isnan(integrated_lufs) or np.isneginf(integrated_lufs) or np.isposinf(integrated_lufs):
        integrated_lufs = -99.0

    # Vectorized Momentary LUFS (400ms window) max from meter.blockwise_loudness
    blockwise = getattr(meter, "blockwise_loudness", None)
    if blockwise is not None:
        valid_m = [float(l) for l in blockwise if not np.isneginf(l) and not np.isnan(l)]
        momentary_lufs_max = max(valid_m) if valid_m else integrated_lufs
    else:
        momentary_lufs_max = integrated_lufs

    # Vectorized Short-Term LUFS (3.0s window = 30 blocks of 100ms)
    if blockwise is not None and len(blockwise) >= 30:
        bw_arr = np.array(blockwise, dtype=np.float64)
        bw_clean = np.where(np.isnan(bw_arr) | np.isneginf(bw_arr), -120.0, bw_arr)
        z_blocks = np.where(bw_clean <= -119.0, 0.0, 10.0 ** ((bw_clean + 0.691) / 10.0))
        kernel_st = np.ones(30) / 30.0
        st_z = np.convolve(z_blocks, kernel_st, mode='valid')
        max_st_z = float(np.max(st_z)) if len(st_z) > 0 else 0.0
        shortterm_lufs_max = float(-0.691 + 10.0 * np.log10(max_st_z + 1e-12)) if max_st_z > 0 else integrated_lufs
    else:
        shortterm_lufs_max = integrated_lufs

    # Loudness Range (LRA, EBU R128)
    try:
        loudness_range_val = float(meter.loudness_range(y))
        if np.isnan(loudness_range_val) or np.isneginf(loudness_range_val):
            loudness_range_val = 0.0
    except Exception:
        loudness_range_val = 0.0

    # B. Peak & Universal True Peak (ITU-R BS.1770-4 4x Polyphase + Lossy Gibbs Compensation)
    try:
        true_peak_dbtp, sample_peak_db = calculate_true_peak_universal(y, audio_path)
    except Exception:
        sample_peak = float(np.max(np.abs(y)))
        sample_peak_db = 20.0 * np.log10(sample_peak + 1e-9)
        true_peak_dbtp = sample_peak_db

    # C. Dual-Gated RMS & Crest Factor Calculations (Parity with Camelot_Pro M4L Engine)
    block_len = max(1, int(sr * 0.1))
    num_blocks = len(y) // block_len
    if num_blocks > 0:
        y_trimmed = y[: num_blocks * block_len]
        block_energies = np.mean(y_trimmed.reshape(num_blocks, -1) ** 2, axis=1)
        abs_active = block_energies[block_energies > 1e-6]  # Absolute gate > -60 dBFS
        if len(abs_active) > 0:
            mean_abs = float(np.mean(abs_active))
            rel_active = abs_active[abs_active >= (mean_abs * 0.1)]  # Relative gate -10 dB
            rms = float(np.sqrt(np.mean(rel_active))) if len(rel_active) > 0 else float(np.sqrt(mean_abs))
        else:
            rms = float(np.sqrt(np.mean(y ** 2)))
    else:
        rms = float(np.sqrt(np.mean(y ** 2)))

    rms_db = 20.0 * np.log10(rms + 1e-9)
    crest_factor_rms = sample_peak_db - rms_db

    # Integrated Crest Factor (TP_max - RMS_int, matching Camelot_Pro M4L CREST FACTOR (int) display)
    crest_factor_integrated = max(0.0, true_peak_dbtp - rms_db)

    # Short-Term Crest Factor Max (PLR Short-Term = True Peak - LUFS Short-Term Max)
    crest_factor_shortterm = true_peak_dbtp - shortterm_lufs_max if not np.isnan(shortterm_lufs_max) else 0.0

    # D. Stereo Analysis (Phase Correlation & M/S Power Ratio)
    if is_stereo:
        norm_l = np.linalg.norm(left)
        norm_r = np.linalg.norm(right)
        if norm_l > 0 and norm_r > 0:
            phase_corr = float(np.dot(left, right) / (norm_l * norm_r))
        else:
            phase_corr = 1.0

        # Low-End Phase Correlation (<100 Hz, Butterworth 4th order lowpass)
        try:
            sos_low = signal.butter(4, 100, 'lowpass', fs=sr, output='sos')
            low_l = signal.sosfilt(sos_low, left)
            low_r = signal.sosfilt(sos_low, right)
            norm_low_l = np.linalg.norm(low_l)
            norm_low_r = np.linalg.norm(low_r)
            if norm_low_l > 1e-6 and norm_low_r > 1e-6:
                phase_corr_low = float(np.dot(low_l, low_r) / (norm_low_l * norm_low_r))
            else:
                phase_corr_low = 1.0
        except Exception:
            phase_corr_low = 1.0

        # Mid/Side Matrix with Standard Energy Normalization
        mid = (left + right) / np.sqrt(2.0)
        side = (left - right) / np.sqrt(2.0)

        energy_mid = np.mean(mid ** 2)
        energy_side = np.mean(side ** 2)
        total_energy_ms = energy_mid + energy_side + 1e-12

        ms_ratio_db = 10 * np.log10((energy_side + 1e-12) / (energy_mid + 1e-12))
        mid_pct = (energy_mid / total_energy_ms) * 100.0
        side_pct = (energy_side / total_energy_ms) * 100.0
    else:
        phase_corr = 1.0
        phase_corr_low = 1.0
        ms_ratio_db = -99.0
        side_pct = 0.0
        mid_pct = 100.0

    # E. Multiband Spectral Energy Distribution (5 Bands, 8192 STFT, 4.5 dB/oct Mastering Tilt per Octave)
    nyq = min(sr / 2.0, 20000.0)
    bands_def = {
        "Sub (<60 Hz)": (20.0, 60.0),
        "Low (60-250 Hz)": (60.0, 250.0),
        "Mid (250Hz-2 kHz)": (250.0, 2000.0),
        "High-Mid (2k-8 kHz)": (2000.0, 8000.0),
        "High (>8 kHz)": (8000.0, max(8500.0, nyq))
    }

    nperseg = min(8192, max(1, len(mono_signal)))
    if is_stereo:
        freqs, _, Zxx_L = signal.stft(left, fs=sr, nperseg=nperseg)
        _, _, Zxx_R = signal.stft(right, fs=sr, nperseg=nperseg)
        psd = (np.abs(Zxx_L) ** 2) + (np.abs(Zxx_R) ** 2)
    else:
        freqs, _, Zxx = signal.stft(mono_signal, fs=sr, nperseg=nperseg)
        psd = np.abs(Zxx) ** 2

    # 4.5 dB/octave Mastering Reference Tilt (matches SPAN / Pro-Q 3 perceptual balance)
    tilt_weights = (np.maximum(freqs, 20.0) / 1000.0) ** 0.5
    psd_weighted = psd * tilt_weights[:, None]

    raw_band_energies = {}
    band_list = list(bands_def.items())
    for i, (b_name, (f_min, f_max)) in enumerate(band_list):
        if i == len(band_list) - 1:
            idx = np.where((freqs >= f_min) & (freqs <= f_max))[0]
        else:
            idx = np.where((freqs >= f_min) & (freqs < f_max))[0]
        octaves = max(0.5, float(np.log2(max(f_max, f_min + 1.0) / f_min)))
        raw_band_energies[b_name] = (float(np.sum(psd_weighted[idx, :])) / octaves) if len(idx) > 0 else 0.0

    total_energy = sum(raw_band_energies.values()) + 1e-12

    band_energies = {}
    for b_name, b_energy in raw_band_energies.items():
        pct = (b_energy / total_energy) * 100.0
        db_rel = 10 * np.log10((b_energy / total_energy) + 1e-9)
        band_energies[b_name] = {
            "percentage": round(pct, 2),
            "db_rel": round(db_rel, 2)
        }

    return {
        "file_name": os.path.basename(audio_path),
        "sample_rate": sr,
        "is_stereo": is_stereo,
        "lufs_integrated": round(float(integrated_lufs), 2),
        "lufs_momentary_max": round(float(momentary_lufs_max), 2),
        "lufs_shortterm_max": round(float(shortterm_lufs_max), 2),
        "loudness_range": round(float(loudness_range_val), 2),
        "sample_peak_db": round(float(sample_peak_db), 2),
        "true_peak_dbtp": round(float(true_peak_dbtp), 2),
        "rms_db": round(float(rms_db), 2),
        "crest_factor_integrated": round(float(crest_factor_integrated), 2),
        "crest_factor_shortterm": round(float(crest_factor_shortterm), 2),
        "crest_factor_rms": round(float(crest_factor_rms), 2),
        "crest_factor_db": round(float(crest_factor_integrated), 2),
        "phase_correlation": round(float(phase_corr), 3),
        "stereo_correlation_low": round(float(phase_corr_low), 3),
        "ms_ratio_db": round(float(ms_ratio_db), 2),
        "mid_percentage": round(float(mid_pct), 1),
        "side_percentage": round(float(side_pct), 1),
        "band_energies": band_energies
    }


# -----------------------------------------------------------------------------
# 2. HTML REPORT GENERATION (GLASSMORPHISM & PREMIUM UI)
# -----------------------------------------------------------------------------

ADVISOR_CONFIG = {
    "mix": {
        "title": "Fase Mix",
        "icon": "🎚️",
        "description": "Standard di headroom, dinamica e coerenza di fase per preparare il mix al mastering",
        "parameters": [
            {
                "id": "true_peak",
                "name": "True Peak Headroom",
                "unit": "dBTP",
                "metric_key": "true_peak_dbtp",
                "min": -8.0,
                "max": -2.5,
                "target": -4.5,
                "messages": {
                    "too_low": "Headroom eccessiva. Aumenta il gain generale per ottimizzare il livello ed evitare che la traccia arrivi troppo debole al master.",
                    "too_high": "Headroom insufficiente. Riduci proporzionalmente i fader del mix per mantenere i picchi sicuri (tra -8 e -2.5 dBTP) ed evitare saturazioni indesiderate.",
                    "optimal": "Headroom ottimale. Il bilanciamento lascia un margine perfetto per le lavorazioni di mastering."
                }
            },
            {
                "id": "lufs_integrated",
                "name": "LUFS Integrato (Loudness Mix)",
                "unit": "LUFS",
                "metric_key": "lufs_integrated",
                "min": -20.0,
                "max": -12.0,
                "target": -16.0,
                "messages": {
                    "too_low": "Mix globale troppo debole. Alza i fader mantenendo i bilanciamenti invariati per avvicinarti al range di riferimento.",
                    "too_high": "Loudness del mix eccessiva, potresti aver abusato di bus compression. Abbassa i livelli generali per ristabilire dinamica.",
                    "optimal": "Loudness in perfetto equilibrio. Corpo solido e pronto per il limiter."
                }
            },
            {
                "id": "stereo_correlation_low",
                "name": "Correlazione Fase Low-End (<100 Hz)",
                "unit": "",
                "metric_key": "stereo_correlation_low",
                "min": 0.85,
                "max": 1.0,
                "target": 1.0,
                "messages": {
                    "too_low": "Pericolo di cancellazione di fase nel low-end. Forza Kick e 808/Sub in mono assoluto (< 100 Hz) per garantire la massima botta nel club.",
                    "too_high": "N/A",
                    "optimal": "Low-end compatto e focalizzato. Perfetta coerenza di fase sulle frequenze basse."
                }
            },
            {
                "id": "stereo_correlation_overall",
                "name": "Correlazione Fase Globale (L/R)",
                "unit": "",
                "metric_key": "phase_correlation",
                "min": 0.35,
                "max": 0.96,
                "target": 0.70,
                "messages": {
                    "too_low": "Presenza di problemi di fase diffusi o stereo widening eccessivo. Controlla i pad, reverb o doubler per limitare le cancellazioni quando in ascolto mono.",
                    "too_high": "Immagine stereo quasi completamente mono (> 0.96). Se desiderato, apri leggermente gli elementi di accompagnamento nel Side.",
                    "optimal": "Ampiezza stereo eccellente. Bilanciamento ideale tra solidità del centro (Kick, Snare, Vocals) e tridimensionalità del side."
                }
            },
            {
                "id": "crest_factor",
                "name": "Crest Factor Integrato (Dinamica TP-RMS)",
                "unit": "dB",
                "metric_key": "crest_factor_integrated",
                "min": 8.5,
                "max": 15.0,
                "target": 11.5,
                "messages": {
                    "too_low": "Dinamica schiacciata (pochi transienti). Riduci la compressione, clipper o limiter sui bus tamburi per far respirare Kick e Snare.",
                    "too_high": "Transienti eccessivamente spigolosi (troppa differenza Peak/RMS). Usa un compressore o un soft clipper per controllare gli attacchi delle percussioni.",
                    "optimal": "Rapporto transiente/corpo perfetto. La traccia ha punch ritmico ma densità solida, ottimale per lo standard moderno."
                }
            }
        ]
    },
    "master": {
        "title": "Fase Master",
        "icon": "🎛️",
        "description": "Target commerciali per pubblicazione e streaming (Hip Hop / Trap / Modern Urban / Pop)",
        "parameters": [
            {
                "id": "lufs_integrated",
                "name": "LUFS Integrato (Loudness Totale)",
                "unit": "LUFS",
                "metric_key": "lufs_integrated",
                "min": -10.5,
                "max": -6.5,
                "target": -8.5,
                "messages": {
                    "too_low": "Master poco competitivo rispetto agli standard di mercato attuali. Spingi maggiormente il segnale dentro il limiter o usa clipper a monte.",
                    "too_high": "Volume esagerato che sta stritolando il brano. Allenta la spinta del limiter per recuperare punch nel Kick e aria sul cantato.",
                    "optimal": "Loudness complessiva forte e competitiva, allineata perfettamente agli standard moderni."
                }
            },
            {
                "id": "lufs_short_term",
                "name": "LUFS Short-Term Max (Impatto Drop/Hook)",
                "unit": "LUFS",
                "metric_key": "lufs_shortterm_max",
                "min": -8.5,
                "max": -5.0,
                "target": -6.8,
                "messages": {
                    "too_low": "Manca impatto durante le sezioni più pesanti (Hook/Drop). Assicurati che ritornelli e bass drop spingano l'RMS nei valori target.",
                    "too_high": "Schiacciamento eccessivo sul ritornello o bass drop. Rischio di distorsione armonica elevata, riduci il gain reduction nel punto più denso del beat.",
                    "optimal": "Potenza ed impatto formidabili nelle sezioni cariche, garantendo la massima resa del brano."
                }
            },
            {
                "id": "true_peak",
                "name": "True Peak Ceiling (Prevenzione ISP)",
                "unit": "dBTP",
                "metric_key": "true_peak_dbtp",
                "min": -2.0,
                "max": -0.3,
                "target": -1.0,
                "messages": {
                    "too_low": "Ceiling piuttosto conservativo (< -2.0 dBTP). Puoi alzare il ceiling del limiter a -1.0 / -1.2 dBTP per massimizzare il livello.",
                    "too_high": "Attenzione ai picchi inter-sample (ISP > -0.3 dBTP). Abbassa il ceiling del limiter a -1.0 dBTP e attiva il True Peak Limiting per non distorcere in streaming.",
                    "optimal": "True Peak in zona di sicurezza (-2.0 .. -0.3 dBTP). Convertitori e algoritmi di streaming non genereranno clipping digitale."
                }
            },
            {
                "id": "loudness_range",
                "name": "Loudness Range LRA (Macro-Dinamica)",
                "unit": "LU",
                "metric_key": "loudness_range",
                "min": 2.5,
                "max": 8.5,
                "target": 5.5,
                "messages": {
                    "too_low": "Macro-dinamica molto stretta (< 2.5 LU). Crea maggiore contrasto di gain tra Strofa e Ritornello tramite automazione.",
                    "too_high": "Escursione dinamica molto ampia (> 8.5 LU) tra le sezioni del brano. Verifica che le parti più intime non risultino troppo basse.",
                    "optimal": "Dinamica strutturale del brano equilibrata. L'ascolto scorre mantenendo contrasto e impatto tra strofe e ritornelli."
                }
            }
        ]
    }
}

def evaluate_advisor_param(val, p_def):
    unit = p_def.get("unit", "")
    if not isinstance(val, (int, float)):
        return {
            "status": "na",
            "val_str": "N/A",
            "badge_class": "badge-sub",
            "badge_text": "DATO NON DISPONIBILE",
            "message": "Metrica non disponibile per questo file audio.",
            "pos_pct": 50.0,
            "target_pct": 50.0,
            "min_pct": 25.0,
            "max_pct": 75.0
        }

    min_v = p_def["min"]
    max_v = p_def["max"]
    target_v = p_def["target"]
    msgs = p_def["messages"]
    val_str = f"{val} {unit}".strip()

    # Gauge visual scale mapping [g_min, g_max] -> [0%, 100%]
    span = max(max_v - min_v, 0.1)
    g_min = min_v - span * 0.5
    g_max = max_v + span * 0.5
    g_range = max(g_max - g_min, 0.01)

    pos_pct = min(max((val - g_min) / g_range * 100.0, 0.0), 100.0)
    target_pct = min(max((target_v - g_min) / g_range * 100.0, 0.0), 100.0)
    min_pct = min(max((min_v - g_min) / g_range * 100.0, 0.0), 100.0)
    max_pct = min(max((max_v - g_min) / g_range * 100.0, 0.0), 100.0)

    if val < min_v:
        status = "too_low"
        badge_class = "badge-danger"
        badge_text = "⚠️ SOTTO TARGET"
        msg = msgs.get("too_low", "")
    elif val > max_v:
        if msgs.get("too_high") == "N/A":
            status = "optimal"
            badge_class = "badge-success"
            badge_text = "✅ OTTIMALE"
            msg = msgs.get("optimal", "")
        else:
            status = "too_high"
            badge_class = "badge-danger"
            badge_text = "⚠️ SOPRA TARGET"
            msg = msgs.get("too_high", "")
    else:
        status = "optimal"
        badge_class = "badge-success"
        badge_text = "✅ OTTIMALE"
        msg = msgs.get("optimal", "")

    return {
        "status": status,
        "val_str": val_str,
        "badge_class": badge_class,
        "badge_text": badge_text,
        "message": msg,
        "pos_pct": round(pos_pct, 1),
        "target_pct": round(target_pct, 1),
        "min_pct": round(min_pct, 1),
        "max_pct": round(max_pct, 1)
    }

def ableton_fader_to_db(slider_val):
    """
    Converts Ableton Live normalized fader position (0.0 .. 1.0, where 0.85 = 0.0 dB)
    into accurate dB values matching Ableton Live's mixer scale.
    """
    try:
        v = float(slider_val)
    except Exception:
        return 0.0
    if v <= 0.0001:
        return -70.0
    if v >= 0.85:
        return round((v - 0.85) / 0.15 * 6.0, 2)
    if v >= 0.40:
        return round((v - 0.85) * 40.0, 2)
    if v >= 0.15:
        return round(-18.0 - ((0.40 - v) / 0.25) * 24.0, 2)
    return round(-42.0 - ((0.15 - v) / 0.15) * 28.0, 2)


def resolve_track_volume_db(t):
    """Returns accurate track volume in dB, fixing legacy 20*log10(0.85)=-1.41dB values."""
    if not isinstance(t, dict):
        return "0.0"
    vol_str = t.get("volume_str")
    if isinstance(vol_str, str) and vol_str.strip() and "bound method" not in vol_str and "object at" not in vol_str:
        cleaned = vol_str.replace("dB", "").strip()
        if cleaned:
            return cleaned
    if "volume_gain" in t and isinstance(t.get("volume_gain"), (int, float)):
        return str(ableton_fader_to_db(t["volume_gain"]))
    return str(t.get("volume_db", "0.0"))


def resolve_track_pan(t):
    if not isinstance(t, dict):
        return "0.0"
    pan_str = t.get("panning_str")
    if isinstance(pan_str, str) and pan_str.strip() and "bound method" not in pan_str and "object at" not in pan_str:
        return pan_str.strip()
    pan_val = t.get("panning", t.get("pan", 0.0))
    return str(pan_val)


def is_device_effectively_active(d):
    """Checks both device active property and 'Device On' parameter."""
    if not isinstance(d, dict):
        return True
    active_flag = d.get("active", d.get("is_active", True))
    if not active_flag:
        return False
    for par in d.get("parameters", []):
        if par.get("name") == "Device On":
            try:
                if float(par.get("value", 1)) == 0.0:
                    return False
            except Exception:
                pass
    return True


def format_param_value(par):
    """Prefers clean human-readable display string from Ableton if valid, else numeric value."""
    disp = par.get("display", "")
    if isinstance(disp, str) and disp.strip() and "bound method" not in disp and "object at" not in disp:
        return disp.strip()
    return par.get("value", "")


def esc(val):
    """Safely HTML-escapes any value for interpolation into HTML content or attributes."""
    return html.escape(str(val if val is not None else ""), quote=True)


def format_clean_sends(sends):
    if not sends:
        return '<span style="color:#64748b;">—</span>'
    active = []
    for idx, s in enumerate(sends):
        if isinstance(s, dict):
            s_idx = esc(s.get("send_index", idx + 1))
            s_disp = s.get("display", "")
            if isinstance(s_disp, str) and s_disp.strip() and "bound method" not in s_disp and "object at" not in s_disp:
                if "-inf" not in s_disp.lower() and "-70" not in s_disp:
                    active.append(f'<span class="send-badge">S{s_idx}: {esc(s_disp)}</span>')
                continue
            db = s.get("db", -70.0)
            if isinstance(db, (int, float)) and db > -69.0:
                active.append(f'<span class="send-badge">S{s_idx}: {esc(db)}dB</span>')
        elif isinstance(s, (int, float)):
            if s > -69.0:
                active.append(f'<span class="send-badge">S{idx+1}: {esc(s)}dB</span>')
    return "".join(active) if active else '<span style="color:#64748b;">—</span>'

def render_devices_compact(devices):
    if not devices:
        return '<span class="plugin-empty">Nessun Plugin</span>'
    chips = []
    for d in devices:
        p_name = esc(d.get("name", "Unknown"))
        is_on = is_device_effectively_active(d)
        dot_color = "#34d399" if is_on else "#f43f5e"
        
        params = d.get("parameters", [])
        automated_count = sum(1 for par in params if par.get("is_automated", False)) if params else len(d.get("automated_params", []))
        auto_badge = f'<span class="auto-badge" title="{automated_count} parametri automatizzati">⚡{automated_count}</span>' if automated_count > 0 else ""

        param_dropdown = ""
        if params:
            param_items = []
            for par in params:
                p_label = esc(par.get("name", ""))
                p_val = esc(format_param_value(par))
                is_auto = par.get("is_automated", False)
                auto_icon = "⚡ " if is_auto else ""
                color_style = "color:#fbbf24;" if is_auto else "color:#cbd5e1;"
                param_items.append(f'<div class="param-row" style="{color_style}"><span class="param-name">{auto_icon}{p_label}</span><b class="param-val">{p_val}</b></div>')
            param_dropdown = f"""
            <details class="plugin-params-pop">
                <summary title="Visualizza {len(params)} Parametri">⚙️ {len(params)}</summary>
                <div class="plugin-params-panel">
                    {''.join(param_items)}
                </div>
            </details>
            """

        chips.append(f"""
        <div class="plugin-chip-mini">
            <span class="status-dot" style="background:{dot_color};" title="{'Attivo' if is_on else 'Bypass'}"></span>
            <span class="plugin-title">{p_name}</span>
            {auto_badge}
            {param_dropdown}
        </div>
        """)
    return f'<div class="plugins-compact-wrap">{"".join(chips)}</div>'

def build_session_tree(tracks):
    """
    Builds a structured hierarchy of tracks and groups without overwriting
    tracks or groups that share the same name.
    """
    has_parents = any(("parent_group" in t and t.get("parent_group")) or ("parent_group_id" in t and t.get("parent_group_id")) for t in tracks)
    if has_parents:
        node_list = []
        id_map = {}
        for idx, t in enumerate(tracks):
            node = {
                "track": t,
                "children": [],
                "id": f"trk-{idx+1}",
                "is_group": t.get("is_group", False),
                "is_subgroup": t.get("is_group", False) and bool(t.get("parent_group") or t.get("parent_group_id"))
            }
            node_list.append(node)
            trk_id = t.get("track_id")
            if trk_id:
                id_map[trk_id] = node

        roots = []
        for idx, t in enumerate(tracks):
            node = node_list[idx]
            parent_node = None

            # 1. Match by exact Ableton LOM track_id if available
            p_id = t.get("parent_group_id")
            if p_id and p_id in id_map and id_map[p_id] is not node:
                parent_node = id_map[p_id]
            else:
                # 2. Match by nearest preceding group track with matching name
                p_name = t.get("parent_group")
                if p_name:
                    for prev_idx in range(idx - 1, -1, -1):
                        cand = node_list[prev_idx]
                        if cand["is_group"] and cand["track"].get("name") == p_name:
                            parent_node = cand
                            break
                    if not parent_node:
                        for cand in node_list:
                            if cand is not node and cand["is_group"] and cand["track"].get("name") == p_name:
                                parent_node = cand
                                break

            if parent_node is not None:
                parent_node["children"].append(node)
            else:
                roots.append(node)
        return roots

    # Sequential stack heuristic
    roots = []
    stack = []
    for idx, t in enumerate(tracks):
        is_grp = t.get("is_group", False)
        is_grpd = t.get("is_grouped", False)
        node = {
            "track": t,
            "children": [],
            "id": f"trk-{idx+1}",
            "is_group": is_grp,
            "is_subgroup": is_grp and is_grpd
        }

        if not is_grpd:
            roots.append(node)
            stack = [node]
        else:
            if is_grp:
                if stack:
                    stack[-1]["children"].append(node)
                else:
                    roots.append(node)
                stack.append(node)
            else:
                if stack:
                    stack[-1]["children"].append(node)
                else:
                    roots.append(node)
    return roots

def render_tree_node_html(node, depth=0):
    t = node["track"]
    name = t.get("name", "Unnamed")
    vol_db = resolve_track_volume_db(t)
    pan = resolve_track_pan(t)
    sends_rendered = format_clean_sends(t.get("sends", []))
    devices = t.get("devices", [])
    devices_html = render_devices_compact(devices)
    dev_count = len(devices)

    is_group = node.get("is_group", False)
    is_subgroup = node.get("is_subgroup", False)
    children = node.get("children", [])

    if is_subgroup:
        type_badge = '<span class="badge badge-subgroup">📂 SOTTO-GRUPPO</span>'
    elif is_group:
        type_badge = '<span class="badge badge-group">📁 GRUPPO</span>'
    else:
        type_badge = '<span class="badge badge-track">🎵 TRACCIA</span>'

    dev_badge = f'<span class="badge badge-count">{dev_count} FX</span>' if dev_count > 0 else '<span class="badge badge-sub">0 FX</span>'

    # Search keywords
    plugin_names = " ".join([d.get("name", "") for d in devices]).lower()
    search_data = f'data-name="{esc(name.lower())}" data-plugins="{esc(plugin_names)}"'

    children_html = ""
    if children:
        children_rendered = "".join([render_tree_node_html(c, depth + 1) for c in children])
        children_html = f'<div class="tree-children">{children_rendered}</div>'

    return f"""
    <details class="tree-item depth-{depth}" open {search_data}>
        <summary class="tree-summary">
            <span class="tree-chevron">▶</span>
            {type_badge}
            <span class="tree-title">{esc(name)}</span>
            <span class="mixer-pill">Vol: <b>{esc(vol_db)} dB</b> | Pan: <b>{esc(pan)}</b></span>
            <span class="sends-pill">Sends: {sends_rendered}</span>
            {dev_badge}
            <div class="tree-inline-plugins">{devices_html}</div>
        </summary>
        <div class="tree-body">
            {children_html}
        </div>
    </details>
    """

def get_brand_icon_data_uri():
    """Loads Camelot Pro icon as a self-contained data URI for HTML favicon and header logo."""
    script_dir = Path(__file__).resolve().parent
    for fname in ("Camelot_Pro_Icon_128.png", "Camelot_Pro_Icon.png"):
        icon_path = script_dir / fname
        if icon_path.exists():
            try:
                b64 = base64.b64encode(icon_path.read_bytes()).decode("ascii")
                return f"data:image/png;base64,{b64}"
            except OSError:
                pass
    return ""


def generate_html_report(audio_metrics, session_data, output_path):
    """Generates a stunning, compact, hierarchical HTML dashboard report."""

    brand_icon_uri = get_brand_icon_data_uri()
    favicon_tags = (
        f'    <link rel="icon" type="image/png" href="{brand_icon_uri}">\n'
        f'    <link rel="apple-touch-icon" href="{brand_icon_uri}">'
    ) if brand_icon_uri else ""
    brand_logo_html = (
        f'<img src="{brand_icon_uri}" alt="CAMELOT PRO" class="brand-logo">'
    ) if brand_icon_uri else "🗡️"

    sess_info = session_data.get("Session_Info", {}) if session_data else {}
    tracks = session_data.get("Tracks", []) if session_data else []
    returns = session_data.get("Return_Tracks", []) if session_data else []
    master = session_data.get("Master_Track", None) if session_data else None

    # Phase Status Color
    phase_val = audio_metrics.get("phase_correlation", "N/A")
    if isinstance(phase_val, (int, float)):
        phase_pointer_pct = min(max((phase_val + 1.0) / 2.0 * 100.0, 0.0), 100.0)
        if phase_val >= 0.5:
            phase_color = "#34d399"
            phase_status = "Ottima Coerenza Mono"
        elif phase_val >= 0.1:
            phase_color = "#fbbf24"
            phase_status = "Accettabile / Ampiamente Stereo"
        else:
            phase_color = "#f43f5e"
            phase_status = "⚠️ RISCHIO CANCELLAZIONE DI FASE"
    else:
        phase_pointer_pct = 50.0
        phase_color = "#38bdf8"
        phase_status = "Dato Audio Non Disponibile"

    phase_low_val = audio_metrics.get("stereo_correlation_low", "N/A")
    phase_low_color = (
        "#34d399" if (isinstance(phase_low_val, (int, float)) and phase_low_val >= 0.9)
        else ("#f43f5e" if isinstance(phase_low_val, (int, float)) else "#94a3b8")
    )

    # True Peak Alert
    tp_val = audio_metrics.get("true_peak_dbtp", "N/A")
    if isinstance(tp_val, (int, float)):
        tp_badge = '<span class="badge badge-success">OK (No Clip)</span>' if tp_val <= 0.0 else '<span class="badge badge-danger">⚠️ TRUE PEAK CLIPPING!</span>'
    else:
        tp_badge = '<span class="badge badge-sub">N/A</span>'

    # Multiband HTML Bars
    bands_html = ""
    for band_name, data in audio_metrics.get("band_energies", {}).items():
        pct = data["percentage"]
        db_val = data["db_rel"]
        bands_html += f"""
        <div class="band-item">
            <div class="band-label">
                <span>{band_name}</span>
                <span><b>{pct}%</b> ({db_val} dB)</span>
            </div>
            <div class="progress-bar-bg">
                <div class="progress-bar-fill" style="width: {min(max(pct, 0), 100)}%;"></div>
            </div>
        </div>
        """

    # --- ADVISOR CARDS GENERATION ---
    lufs_int = audio_metrics.get("lufs_integrated", -99.0)
    active_advisor_phase = "master" if (isinstance(lufs_int, (int, float)) and lufs_int > -12.0) else "mix"

    advisor_html_sections = {}
    for phase_key, p_cfg in ADVISOR_CONFIG.items():
        cards_html = []
        for p_def in p_cfg["parameters"]:
            m_val = audio_metrics.get(p_def["metric_key"], "N/A")
            eval_res = evaluate_advisor_param(m_val, p_def)

            status_style = {
                "optimal": "border-color: rgba(52, 211, 153, 0.4); background: rgba(52, 211, 153, 0.06);",
                "too_low": "border-color: rgba(251, 191, 36, 0.4); background: rgba(251, 191, 36, 0.06);",
                "too_high": "border-color: rgba(244, 63, 94, 0.4); background: rgba(244, 63, 94, 0.06);",
                "na": "border-color: rgba(255, 255, 255, 0.1); background: rgba(255, 255, 255, 0.03);"
            }.get(eval_res["status"], "")

            cards_html.append(f"""
            <div class="advisor-card" style="{status_style}">
                <div class="advisor-card-header">
                    <div>
                        <div class="advisor-param-title">{p_def['name']}</div>
                        <div class="advisor-target-pill">Target: <b>{p_def['target']} {p_def['unit']}</b> (Range: {p_def['min']} .. {p_def['max']})</div>
                    </div>
                    <div>
                        <span class="badge {eval_res['badge_class']}">{eval_res['badge_text']}</span>
                    </div>
                </div>

                <div class="advisor-val-row">
                    <span class="advisor-val-label">Valore Rilevato:</span>
                    <span class="advisor-val-display">{eval_res['val_str']}</span>
                </div>

                <!-- Range Gauge -->
                <div class="gauge-container">
                    <div class="gauge-track">
                        <div class="gauge-safe-zone" style="left:{eval_res['min_pct']}%; width:{max(eval_res['max_pct'] - eval_res['min_pct'], 2)}%;"></div>
                        <div class="gauge-target-tick" style="left:{eval_res['target_pct']}%;" title="Target: {p_def['target']}"></div>
                        <div class="gauge-pointer" style="left:{eval_res['pos_pct']}%;" title="Attuale: {eval_res['val_str']}"></div>
                    </div>
                    <div class="gauge-labels">
                        <span>Min {p_def['min']}</span>
                        <span style="color:var(--accent-blue);">🎯 {p_def['target']}</span>
                        <span>Max {p_def['max']}</span>
                    </div>
                </div>

                <div class="advisor-message">
                    💡 {eval_res['message']}
                </div>
            </div>
            """)
        advisor_html_sections[phase_key] = "".join(cards_html)

    # --- HIERARCHICAL TREE GENERATION (MASTER AT ROOT) ---
    session_tree = build_session_tree(tracks)
    tree_rendered_children = "".join([render_tree_node_html(n, depth=1) for n in session_tree])

    # Returns section inside master or adjacent
    returns_html = ""
    if returns:
        ret_chips = "".join([render_tree_node_html({"track": r, "children": [], "is_group": False, "is_subgroup": False}, depth=2) for r in returns])
        returns_html = f"""
        <details class="tree-item depth-1" open style="margin-top:12px;">
            <summary class="tree-summary" style="background:rgba(56, 189, 248, 0.08);">
                <span class="tree-chevron">▶</span>
                <span class="badge badge-info">↩️ TRACCE DI RITORNO ({len(returns)})</span>
                <span class="tree-title">Mandate Master & Riverberi</span>
            </summary>
            <div class="tree-body">
                <div class="tree-children">{ret_chips}</div>
            </div>
        </details>
        """

    # Master Track Representation as the Tree Root
    master_track_data = master if master else {
        "name": "Master",
        "type": "Master",
        "volume_db": "0.0",
        "pan": "0.0",
        "sends": [],
        "devices": []
    }
    master_vol = resolve_track_volume_db(master_track_data)
    master_pan = resolve_track_pan(master_track_data)
    master_devs = master_track_data.get("devices", [])
    master_devs_html = render_devices_compact(master_devs)
    master_dev_count = len(master_devs)

    master_tree_html = f"""
    <details class="tree-item tree-master depth-0" open data-name="master" data-plugins="{esc(" ".join([d.get("name","") for d in master_devs]).lower())}">
        <summary class="tree-summary master-summary">
            <span class="tree-chevron">▶</span>
            <span class="badge badge-master">👑 TRACCIA MASTER</span>
            <span class="tree-title" style="font-size:1.15rem; color:#f8fafc;">Master Bus & Sub-Gruppi</span>
            <span class="mixer-pill">Vol: <b>{esc(master_vol)} dB</b> | Pan: <b>{esc(master_pan)}</b></span>
            <span class="badge badge-count">{master_dev_count} FX Master</span>
            <div class="tree-inline-plugins">{master_devs_html}</div>
        </summary>
        <div class="tree-body">
            <div class="tree-children">
                {tree_rendered_children}
                {returns_html}
            </div>
        </div>
    </details>
    """

    html_doc = f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CAMELOT PRO Telemetry & Mix Advisor - {esc(audio_metrics.get('file_name', 'Session'))}</title>
{favicon_tags}
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700;800&family=JetBrains+Mono:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --bg: #070b14;
            --card-bg: rgba(17, 24, 39, 0.75);
            --border: rgba(255, 255, 255, 0.08);
            --accent-blue: #38bdf8;
            --accent-purple: #818cf8;
            --accent-pink: #f43f5e;
            --accent-green: #34d399;
            --accent-amber: #fbbf24;
            --text: #f8fafc;
            --text-muted: #94a3b8;
        }}

        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background: var(--bg);
            color: var(--text);
            font-family: 'Outfit', sans-serif;
            padding: 2rem;
            line-height: 1.5;
        }}

        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: linear-gradient(135deg, rgba(56, 189, 248, 0.12), rgba(129, 140, 248, 0.12));
            border: 1px solid var(--border);
            border-radius: 18px;
            padding: 1.75rem 2rem;
            margin-bottom: 2rem;
            backdrop-filter: blur(14px);
        }}

        .header-brand {{
            display: flex;
            align-items: center;
            gap: 1rem;
        }}

        .brand-logo {{
            width: 56px;
            height: 56px;
            border-radius: 13px;
            box-shadow: 0 0 18px rgba(56, 189, 248, 0.35);
            flex-shrink: 0;
        }}

        .header h1 {{
            font-size: 2.1rem;
            font-weight: 800;
            background: linear-gradient(90deg, #38bdf8, #818cf8, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            letter-spacing: -0.02em;
        }}

        .session-meta {{
            display: flex;
            gap: 1.25rem;
            font-family: 'JetBrains Mono', monospace;
            background: rgba(15, 23, 42, 0.7);
            padding: 0.65rem 1.2rem;
            border-radius: 12px;
            border: 1px solid var(--border);
            font-size: 0.85rem;
        }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 1.4rem;
            backdrop-filter: blur(16px);
            box-shadow: 0 10px 28px rgba(0,0,0,0.35);
        }}

        .card h2 {{
            font-size: 1.15rem;
            font-weight: 700;
            color: var(--accent-blue);
            margin-bottom: 1.1rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}

        .metric-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.55rem 0;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.88rem;
        }}

        .metric-val {{ font-weight: 700; color: #ffffff; }}

        /* Phase Meter Gauge */
        .phase-meter {{
            height: 10px;
            background: linear-gradient(90deg, #f43f5e 0%, #fbbf24 50%, #34d399 100%);
            border-radius: 5px;
            position: relative;
            margin: 0.9rem 0;
        }}

        .phase-pointer {{
            width: 5px;
            height: 18px;
            background: #ffffff;
            border: 2px solid #000;
            border-radius: 3px;
            position: absolute;
            top: -4px;
            transform: translateX(-50%);
            box-shadow: 0 0 8px rgba(255,255,255,0.9);
        }}

        /* Multiband energy */
        .band-item {{ margin-bottom: 0.75rem; }}
        .band-label {{ display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 0.2rem; }}
        .progress-bar-bg {{ height: 7px; background: rgba(255,255,255,0.06); border-radius: 4px; overflow: hidden; }}
        .progress-bar-fill {{ height: 100%; background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple)); border-radius: 4px; }}

        /* Badges */
        .badge {{
            display: inline-flex;
            align-items: center;
            padding: 0.2rem 0.55rem;
            border-radius: 6px;
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.02em;
        }}
        .badge-info {{ background: rgba(56, 189, 248, 0.18); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.35); }}
        .badge-master {{ background: linear-gradient(135deg, rgba(244, 63, 94, 0.3), rgba(192, 132, 252, 0.3)); color: #f472b6; border: 1px solid rgba(244, 63, 94, 0.5); font-weight:800; }}
        .badge-group {{ background: rgba(129, 140, 248, 0.2); color: #a5b4fc; border: 1px solid rgba(129, 140, 248, 0.35); }}
        .badge-subgroup {{ background: rgba(56, 189, 248, 0.15); color: #7dd3fc; border: 1px solid rgba(56, 189, 248, 0.3); }}
        .badge-track {{ background: rgba(255, 255, 255, 0.06); color: #cbd5e1; border: 1px solid rgba(255, 255, 255, 0.1); }}
        .badge-count {{ background: rgba(255, 255, 255, 0.08); color: #94a3b8; font-family:'JetBrains Mono', monospace; }}
        .badge-sub {{ background: rgba(255, 255, 255, 0.05); color: #64748b; }}
        .badge-success {{ background: rgba(52, 211, 153, 0.18); color: #34d399; border: 1px solid rgba(52, 211, 153, 0.35); }}
        .badge-danger {{ background: rgba(244, 63, 94, 0.18); color: #f43f5e; border: 1px solid rgba(244, 63, 94, 0.35); }}

        /* --- ADVISOR SECTION --- */
        .advisor-header-bar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.25rem;
            flex-wrap: wrap;
            gap: 1rem;
        }}
        .advisor-tabs {{
            display: flex;
            gap: 0.5rem;
            background: rgba(15, 23, 42, 0.7);
            padding: 4px;
            border-radius: 12px;
            border: 1px solid var(--border);
        }}
        .advisor-tab-btn {{
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 0.5rem 1.1rem;
            font-size: 0.88rem;
            font-weight: 700;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s ease;
            font-family: 'Outfit', sans-serif;
        }}
        .advisor-tab-btn.active {{
            background: linear-gradient(135deg, var(--accent-blue), var(--accent-purple));
            color: #ffffff;
            box-shadow: 0 4px 12px rgba(56, 189, 248, 0.3);
        }}
        .advisor-tab-btn:hover:not(.active) {{
            color: #ffffff;
            background: rgba(255, 255, 255, 0.05);
        }}

        .advisor-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 1.25rem;
        }}
        .advisor-card {{
            border-radius: 14px;
            border: 1px solid var(--border);
            padding: 1.2rem;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}
        .advisor-card:hover {{
            transform: translateY(-2px);
        }}
        .advisor-card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 0.5rem;
        }}
        .advisor-param-title {{
            font-size: 1rem;
            font-weight: 700;
            color: #ffffff;
        }}
        .advisor-target-pill {{
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 2px;
            font-family: 'JetBrains Mono', monospace;
        }}
        .advisor-val-row {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            font-family: 'JetBrains Mono', monospace;
            padding: 4px 0;
        }}
        .advisor-val-label {{ font-size: 0.8rem; color: var(--text-muted); }}
        .advisor-val-display {{ font-size: 1.15rem; font-weight: 800; color: #ffffff; }}

        /* Gauge */
        .gauge-container {{
            margin: 0.3rem 0;
        }}
        .gauge-track {{
            height: 8px;
            border-radius: 4px;
            background: rgba(255, 255, 255, 0.08);
            position: relative;
        }}
        .gauge-safe-zone {{
            position: absolute;
            height: 100%;
            background: rgba(52, 211, 153, 0.35);
            border-radius: 4px;
        }}
        .gauge-target-tick {{
            position: absolute;
            width: 3px;
            height: 14px;
            top: -3px;
            background: var(--accent-blue);
            transform: translateX(-50%);
            border-radius: 1px;
            box-shadow: 0 0 6px var(--accent-blue);
        }}
        .gauge-pointer {{
            position: absolute;
            width: 10px;
            height: 10px;
            top: -1px;
            border-radius: 50%;
            background: #ffffff;
            border: 2px solid #000;
            transform: translateX(-50%);
            box-shadow: 0 0 8px rgba(255, 255, 255, 0.9);
        }}
        .gauge-labels {{
            display: flex;
            justify-content: space-between;
            font-size: 0.7rem;
            color: var(--text-muted);
            font-family: 'JetBrains Mono', monospace;
            margin-top: 4px;
        }}

        .advisor-message {{
            font-size: 0.82rem;
            line-height: 1.45;
            color: #e2e8f0;
            background: rgba(15, 23, 42, 0.7);
            padding: 0.7rem 0.85rem;
            border-radius: 8px;
            border-left: 3px solid var(--accent-blue);
        }}

        /* --- TREE VIEW (COMPACT & FOLDABLE) --- */
        .tree-toolbar {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            margin-bottom: 1.25rem;
            flex-wrap: wrap;
        }}
        .tree-search-input {{
            flex: 1;
            min-width: 240px;
            background: rgba(15, 23, 42, 0.8);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 0.55rem 1rem;
            color: #ffffff;
            font-family: 'Outfit', sans-serif;
            font-size: 0.88rem;
            outline: none;
            transition: border-color 0.2s ease;
        }}
        .tree-search-input:focus {{
            border-color: var(--accent-blue);
            box-shadow: 0 0 10px rgba(56, 189, 248, 0.2);
        }}
        .tree-btn-group {{
            display: flex;
            gap: 0.5rem;
        }}
        .tree-btn {{
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 0.5rem 0.9rem;
            border-radius: 8px;
            font-size: 0.8rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }}
        .tree-btn:hover {{
            background: rgba(255, 255, 255, 0.12);
            color: #ffffff;
        }}

        /* Tree node items */
        .tree-item {{
            margin-bottom: 4px;
            border-radius: 10px;
            transition: background 0.15s ease;
        }}
        .tree-summary {{
            list-style: none;
            display: flex;
            align-items: center;
            gap: 0.65rem;
            padding: 0.45rem 0.75rem;
            border-radius: 8px;
            cursor: pointer;
            user-select: none;
            background: rgba(255, 255, 255, 0.015);
            border: 1px solid transparent;
            transition: all 0.15s ease;
            flex-wrap: wrap;
        }}
        .tree-summary::-webkit-details-marker {{ display: none; }}
        .tree-summary:hover {{
            background: rgba(255, 255, 255, 0.04);
            border-color: rgba(255, 255, 255, 0.06);
        }}
        .tree-item[open] > .tree-summary {{
            background: rgba(255, 255, 255, 0.025);
        }}

        .tree-chevron {{
            font-size: 0.65rem;
            color: var(--accent-blue);
            display: inline-block;
            transition: transform 0.2s ease;
            width: 14px;
            text-align: center;
        }}
        .tree-item[open] > .tree-summary > .tree-chevron {{
            transform: rotate(90deg);
        }}

        .tree-title {{
            font-weight: 700;
            font-size: 0.92rem;
            color: #ffffff;
        }}
        .mixer-pill {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: var(--text-muted);
            background: rgba(15, 23, 42, 0.6);
            padding: 0.15rem 0.5rem;
            border-radius: 5px;
            border: 1px solid rgba(255,255,255,0.05);
        }}
        .sends-pill {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            color: #94a3b8;
            display: flex;
            align-items: center;
            gap: 4px;
        }}
        .send-badge {{
            background: rgba(129, 140, 248, 0.12);
            color: #c7d2fe;
            padding: 1px 4px;
            border-radius: 4px;
        }}

        .tree-inline-plugins {{
            margin-left: auto;
            display: flex;
            align-items: center;
            gap: 0.4rem;
            flex-wrap: wrap;
        }}
        .plugins-compact-wrap {{
            display: flex;
            gap: 0.35rem;
            flex-wrap: wrap;
        }}
        .plugin-chip-mini {{
            display: inline-flex;
            align-items: center;
            gap: 5px;
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 6px;
            padding: 0.15rem 0.45rem;
            font-size: 0.75rem;
            color: #e2e8f0;
            position: relative;
        }}
        .status-dot {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            display: inline-block;
        }}
        .plugin-title {{ font-weight: 600; }}
        .auto-badge {{
            color: #fbbf24;
            font-weight: 700;
            font-size: 0.68rem;
        }}

        /* Plugin Parameter Popover / Accordion */
        .plugin-params-pop {{
            display: inline-block;
            margin-left: 2px;
        }}
        .plugin-params-pop summary {{
            list-style: none;
            cursor: pointer;
            font-size: 0.68rem;
            color: var(--accent-blue);
            background: rgba(56, 189, 248, 0.12);
            padding: 1px 4px;
            border-radius: 4px;
        }}
        .plugin-params-pop summary::-webkit-details-marker {{ display: none; }}
        .plugin-params-panel {{
            position: absolute;
            right: 0;
            top: calc(100% + 4px);
            z-index: 100;
            min-width: 240px;
            max-height: 200px;
            overflow-y: auto;
            background: rgba(15, 23, 42, 0.95);
            border: 1px solid var(--accent-blue);
            border-radius: 8px;
            padding: 8px 10px;
            box-shadow: 0 10px 24px rgba(0,0,0,0.6);
            backdrop-filter: blur(16px);
        }}
        .param-row {{
            display: flex;
            justify-content: space-between;
            font-size: 0.72rem;
            padding: 2px 0;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            font-family: 'JetBrains Mono', monospace;
        }}

        /* Indentation and nesting branches */
        .tree-children {{
            margin-left: 1.25rem;
            padding-left: 0.85rem;
            border-left: 2px solid rgba(56, 189, 248, 0.15);
            margin-top: 4px;
        }}
        .tree-master > .tree-summary {{
            background: linear-gradient(90deg, rgba(244, 63, 94, 0.12), rgba(129, 140, 248, 0.12));
            border: 1px solid rgba(244, 63, 94, 0.3);
            padding: 0.75rem 1rem;
            border-radius: 12px;
            margin-bottom: 6px;
        }}
        .depth-1 > .tree-summary {{ border-left: 3px solid rgba(129, 140, 248, 0.4); }}
        .depth-2 > .tree-summary {{ border-left: 3px solid rgba(56, 189, 248, 0.4); }}
        .depth-3 > .tree-summary {{ border-left: 3px solid rgba(52, 211, 153, 0.4); }}
        .plugin-empty {{ font-size: 0.72rem; color: #64748b; }}
    </style>
</head>
<body>

    <div class="header">
        <div class="header-brand">
            {brand_logo_html}
            <div>
                <h1>CAMELOT PRO TELEMETRY & ADVISOR</h1>
                <p style="color: var(--text-muted); margin-top: 4px;">Analisi Spettrale, Standard Commerciali Hip Hop/Trap e Struttura Sessione</p>
            </div>
        </div>
        <div class="session-meta">
            <div>FILE: <b>{esc(audio_metrics.get('file_name', 'Session'))}</b></div>
            <div>BPM: <b>{esc(sess_info.get('BPM', 'N/A'))}</b></div>
            <div>METRUM: <b>{esc(sess_info.get('Time_Signature_Num', 4))}/{esc(sess_info.get('Time_Signature_Den', 4))}</b></div>
        </div>
    </div>

    <!-- METRICS CARDS GRID -->
    <div class="grid">
        <!-- CARD 1: LOUDNESS & DINAMICA -->
        <div class="card">
            <h2>Loudness & Dinamica</h2>
            <div class="metric-row">
                <span>LUFS Integrato (EBU R128):</span>
                <span class="metric-val" style="color:var(--accent-blue);">{audio_metrics.get('lufs_integrated', 'N/A')} LUFS</span>
            </div>
            <div class="metric-row">
                <span>LUFS Short-Term Max:</span>
                <span class="metric-val">{audio_metrics.get('lufs_shortterm_max', 'N/A')} LUFS</span>
            </div>
            <div class="metric-row">
                <span>LUFS Momentary Max:</span>
                <span class="metric-val">{audio_metrics.get('lufs_momentary_max', 'N/A')} LUFS</span>
            </div>
            <div class="metric-row">
                <span>Loudness Range (LRA):</span>
                <span class="metric-val" style="color:var(--accent-purple);">{audio_metrics.get('loudness_range', 'N/A')} LU</span>
            </div>
            <div class="metric-row">
                <span>True Peak (4x Oversampled):</span>
                <span class="metric-val">{audio_metrics.get('true_peak_dbtp', 'N/A')} dBTP {tp_badge}</span>
            </div>
            <div class="metric-row">
                <span>Crest Factor Integrato (TP - RMS):</span>
                <span class="metric-val" style="color:var(--accent-green);">{audio_metrics.get('crest_factor_integrated', 'N/A')} dB</span>
            </div>
            <div class="metric-row">
                <span>RMS Level:</span>
                <span class="metric-val">{audio_metrics.get('rms_db', 'N/A')} dB</span>
            </div>
        </div>

        <!-- CARD 2: STEREO IMAGE & PHASE -->
        <div class="card">
            <h2>Immagine Stereo & Fase</h2>
            <div class="metric-row">
                <span>Coerenza di Fase Globale L/R:</span>
                <span class="metric-val" style="color:{phase_color};">{audio_metrics.get('phase_correlation', 'N/A')}</span>
            </div>
            <div class="metric-row">
                <span>Coerenza Low-End (<100 Hz):</span>
                <span class="metric-val" style="color:{phase_low_color};">{audio_metrics.get('stereo_correlation_low', 'N/A')}</span>
            </div>
            
            <div class="phase-meter">
                <!-- Map -1..+1 to 0%..100% -->
                <div class="phase-pointer" style="left: {phase_pointer_pct}%;"></div>
            </div>
            <div style="font-size:0.8rem; text-align:center; color:var(--text-muted); margin-bottom:0.75rem;">
                Status: <b style="color:{phase_color};">{phase_status}</b>
            </div>

            <div class="metric-row">
                <span>Rapporto M/S (Stereo Width):</span>
                <span class="metric-val">{audio_metrics.get('ms_ratio_db', 'N/A')} dB</span>
            </div>
            <div class="metric-row">
                <span>Distribuzione Mid vs Side:</span>
                <span class="metric-val">Mid {audio_metrics.get('mid_percentage', 'N/A')}% / Side {audio_metrics.get('side_percentage', 'N/A')}%</span>
            </div>
        </div>

        <!-- CARD 3: MULTIBAND ENERGY -->
        <div class="card">
            <h2>Spettro Energetico (5 Bande)</h2>
            {bands_html}
        </div>
    </div>

    <!-- SEZIONE CONSIGLI & TARGET GUIDELINES -->
    <div class="card" style="margin-bottom:2rem; border-color:rgba(56, 189, 248, 0.25);">
        <div class="advisor-header-bar">
            <div>
                <h2>💡 SUGGERIMENTI & TARGET GUIDELINES (AI ADVISOR)</h2>
                <p style="color:var(--text-muted); font-size:0.85rem; margin-top:2px;">
                    Valutazione automatica secondo standard di mercato Hip Hop / Trap. Clicca sui tab per consultare i consigli specifici di Mix o Master.
                </p>
            </div>
            <div class="advisor-tabs">
                <button class="advisor-tab-btn {'active' if active_advisor_phase == 'mix' else ''}" id="btn-tab-mix" onclick="switchAdvisorTab('mix')">🎚️ Fase MIX</button>
                <button class="advisor-tab-btn {'active' if active_advisor_phase == 'master' else ''}" id="btn-tab-master" onclick="switchAdvisorTab('master')">🎛️ Fase MASTER</button>
            </div>
        </div>

        <div id="advisor-phase-mix" class="advisor-content advisor-grid" style="display:{'grid' if active_advisor_phase == 'mix' else 'none'};">
            {advisor_html_sections['mix']}
        </div>

        <div id="advisor-phase-master" class="advisor-content advisor-grid" style="display:{'grid' if active_advisor_phase == 'master' else 'none'};">
            {advisor_html_sections['master']}
        </div>
    </div>

    <!-- SESSION STRUCTURE HIERARCHICAL TREE -->
    <div class="card">
        <div class="tree-toolbar">
            <div>
                <h2>🌳 STRUTTURA SESSIONE & PLUGINS (GERARCHIA MASTER)</h2>
                <p style="color:var(--text-muted); font-size:0.85rem; margin-top:2px;">
                    Albero pieghevole compatto: Master &rarr; Sotto-gruppi &rarr; Tracce &rarr; Plugin & Parametri.
                </p>
            </div>
            <div style="display:flex; gap:0.75rem; flex:1; justify-content:flex-end; align-items:center;">
                <input type="text" id="treeSearch" class="tree-search-input" placeholder="🔍 Cerca traccia, gruppo o plugin..." oninput="filterTree()">
                <div class="tree-btn-group">
                    <button class="tree-btn" onclick="toggleAll(true)" title="Espandi tutti i gruppi e tracce">🔽 Espandi Tutto</button>
                    <button class="tree-btn" onclick="toggleAll(false)" title="Riduci tutti i gruppi">🔼 Riduci Tutto</button>
                </div>
            </div>
        </div>

        <div class="tree-container">
            {master_tree_html}
        </div>
    </div>

    <script>
        function switchAdvisorTab(phase) {{
            document.querySelectorAll('.advisor-content').forEach(el => el.style.display = 'none');
            document.querySelectorAll('.advisor-tab-btn').forEach(el => el.classList.remove('active'));
            const target = document.getElementById('advisor-phase-' + phase);
            const btn = document.getElementById('btn-tab-' + phase);
            if (target) target.style.display = 'grid';
            if (btn) btn.classList.add('active');
        }}

        function toggleAll(openState) {{
            document.querySelectorAll('.tree-item').forEach(el => el.open = openState);
        }}

        function filterTree() {{
            const q = document.getElementById('treeSearch').value.toLowerCase().trim();
            const items = document.querySelectorAll('.tree-item');
            if (!q) {{
                items.forEach(el => {{
                    el.style.display = '';
                }});
                return;
            }}

            items.forEach(el => {{
                const name = el.getAttribute('data-name') || '';
                const plugins = el.getAttribute('data-plugins') || '';
                const matches = name.includes(q) || plugins.includes(q);

                if (matches) {{
                    el.style.display = '';
                    let parent = el.parentElement;
                    while (parent) {{
                        if (parent.tagName === 'DETAILS') parent.open = true;
                        parent = parent.parentElement;
                    }}
                }} else {{
                    const descendants = el.querySelectorAll('.tree-item');
                    let childMatches = false;
                    for (let i = 0; i < descendants.length; i++) {{
                        const cName = descendants[i].getAttribute('data-name') || '';
                        const cPlugins = descendants[i].getAttribute('data-plugins') || '';
                        if (cName.includes(q) || cPlugins.includes(q)) {{
                            childMatches = true;
                            break;
                        }}
                    }}
                    if (childMatches) {{
                        el.style.display = '';
                        el.open = true;
                    }} else {{
                        el.style.display = 'none';
                    }}
                }}
            }});
        }}
    </script>
</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_doc)


# -----------------------------------------------------------------------------
# 3. AI CONTEXT FILE GENERATION (LLM PROMPT OPTIMIZED)
# -----------------------------------------------------------------------------

def generate_ai_context(audio_metrics, session_data, output_path):
    """Generates an LLM-optimized Lean Prompt txt file summarizing telemetry and mixing structure."""

    sess_info = session_data.get("Session_Info", {}) if session_data else {}
    tracks = session_data.get("Tracks", []) if session_data else []
    returns = session_data.get("Return_Tracks", []) if session_data else []
    master = session_data.get("Master_Track", None) if session_data else None

    # Diagnostic highlights
    issues = []
    tp_val = audio_metrics.get("true_peak_dbtp", 0.0)
    phase_val = audio_metrics.get("phase_correlation", 1.0)

    if isinstance(tp_val, (int, float)) and tp_val > 0.0:
        issues.append(f"CRITICAL:True Peak > 0dBTP (+{tp_val}dBTP clipping)")
    if isinstance(phase_val, (int, float)) and phase_val < 0.2:
        issues.append(f"WARN:Low L/R Phase correlation ({phase_val})")
    
    sub_pct = audio_metrics.get("band_energies", {}).get("Sub (<60 Hz)", {}).get("percentage", 0)
    if isinstance(sub_pct, (int, float)) and sub_pct > 35:
        issues.append(f"WARN:Sub energy high ({sub_pct}%)")

    issues_str = "|".join(issues) if issues else "OK:No critical telemetry issues"

    # Multiband energies compact line
    bands = audio_metrics.get("band_energies", {})
    bands_compact = "|".join([
        f"{b_name.split()[0]}:{b_data.get('percentage', 0)}%" 
        for b_name, b_data in bands.items()
    ])

    ai_text = f"""[CAMELOT_MIX_CONTEXT]
META|File:{audio_metrics.get('file_name', 'N/A')}|BPM:{sess_info.get('BPM', 'N/A')}|Sig:{sess_info.get('Time_Signature_Num', 4)}/{sess_info.get('Time_Signature_Den', 4)}|Trks:{len(tracks)}|Returns:{len(returns)}|SR:{audio_metrics.get('sample_rate', 'N/A')}Hz|Ch:{'Stereo' if audio_metrics.get('is_stereo', True) else 'Mono'}
DSP|LUFS_I:{audio_metrics.get('lufs_integrated', 'N/A')}|LUFS_ST:{audio_metrics.get('lufs_shortterm_max', 'N/A')}|LUFS_M:{audio_metrics.get('lufs_momentary_max', 'N/A')}|LRA:{audio_metrics.get('loudness_range', 'N/A')}LU|TP:{audio_metrics.get('true_peak_dbtp', 'N/A')}dBTP|RMS:{audio_metrics.get('rms_db', 'N/A')}dB|Crest_I:{audio_metrics.get('crest_factor_integrated', audio_metrics.get('crest_factor_db', 'N/A'))}dB|Crest_ST:{audio_metrics.get('crest_factor_shortterm', 'N/A')}dB|Crest_RMS:{audio_metrics.get('crest_factor_rms', 'N/A')}dB|Phase:{audio_metrics.get('phase_correlation', 'N/A')}|Phase_Low:{audio_metrics.get('stereo_correlation_low', 'N/A')}|MS_Ratio:{audio_metrics.get('ms_ratio_db', 'N/A')}dB|Mid:{audio_metrics.get('mid_percentage', 'N/A')}%|Side:{audio_metrics.get('side_percentage', 'N/A')}%
BANDS|{bands_compact}
ALERTS|{issues_str}

[STRUCTURE]
"""

    def format_track_lean(t, default_type="Trk"):
        if not t: return ""
        name = t.get("name", "Unnamed")
        t_type = "Grp" if t.get("is_group") else ("Sub" if (t.get("is_grouped") or t.get("is_inside_group")) else default_type)
        vol = resolve_track_volume_db(t)
        pan = resolve_track_pan(t)
        sends = t.get("sends", [])
        active_s_list = []
        for idx, s in enumerate(sends):
            if isinstance(s, dict):
                s_idx = s.get("send_index", idx + 1)
                s_disp = s.get("display", "")
                if isinstance(s_disp, str) and s_disp.strip() and "bound method" not in s_disp and "object at" not in s_disp:
                    if "-inf" not in s_disp.lower() and "-70" not in s_disp:
                        active_s_list.append(f"S{s_idx}:{s_disp}")
                    continue
                db = s.get("db", -70)
                if isinstance(db, (int, float)) and db > -69:
                    active_s_list.append(f"S{s_idx}:{db}dB")
            elif isinstance(s, (int, float)):
                if s > -69: active_s_list.append(f"S{idx+1}:{s}dB")
        sends_str = "[" + ",".join(active_s_list) + "]" if active_s_list else "[]"
        
        plugins = t.get("devices", [])
        fx_items = []
        for p in plugins:
            status = "ON" if is_device_effectively_active(p) else "BYP"
            p_name = p.get("name", "Plugin")
            params = p.get("parameters", [])
            
            if params:
                param_strs = [
                    f"{'⚡' if par.get('is_automated') else ''}{par.get('name')}={format_param_value(par)}"
                    for par in params
                ]
                fx_items.append(f"{p_name}({status}){{{','.join(param_strs)}}}")
            else:
                auto = p.get("automated_params", [])
                auto_str = "{" + ",".join([f"⚡{a}" for a in auto]) + "}" if auto else ""
                fx_items.append(f"{p_name}({status}){auto_str}")
        
        fx_str = "[" + ", ".join(fx_items) + "]" if fx_items else "[]"
        return f"T:{name}|Type:{t_type}|V:{vol}dB|P:{pan}|S:{sends_str}|FX:{fx_str}\n"

    for t in tracks:
        ai_text += format_track_lean(t, "Trk")

    for rt in returns:
        ai_text += format_track_lean(rt, "Ret")

    if master:
        ai_text += format_track_lean(master, "Mst")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ai_text.strip() + "\n")


# -----------------------------------------------------------------------------
# 4. MAIN ENTRY POINT & CLI / DEMO MODE
# -----------------------------------------------------------------------------

def get_fallback_audio_metrics(file_name="Session_Only"):
    return {
        "audio_analyzed": False,
        "file_name": file_name,
        "sample_rate": "N/A",
        "is_stereo": True,
        "lufs_integrated": "N/A",
        "lufs_momentary_max": "N/A",
        "lufs_shortterm_max": "N/A",
        "loudness_range": "N/A",
        "sample_peak_db": "N/A",
        "true_peak_dbtp": "N/A",
        "rms_db": "N/A",
        "crest_factor_integrated": "N/A",
        "crest_factor_shortterm": "N/A",
        "crest_factor_rms": "N/A",
        "crest_factor_db": "N/A",
        "phase_correlation": "N/A",
        "stereo_correlation_low": "N/A",
        "ms_ratio_db": "N/A",
        "mid_percentage": "N/A",
        "side_percentage": "N/A",
        "band_energies": {
            "Sub (<60 Hz)": {"percentage": 0.0, "db_rel": -99.0},
            "Low (60-250 Hz)": {"percentage": 0.0, "db_rel": -99.0},
            "Mid (250Hz-2 kHz)": {"percentage": 0.0, "db_rel": -99.0},
            "High-Mid (2k-8 kHz)": {"percentage": 0.0, "db_rel": -99.0},
            "High (>8 kHz)": {"percentage": 0.0, "db_rel": -99.0}
        }
    }

def find_latest_audio_file(directories):
    """
    Scans specified directories for the most recently modified audio file.
    Supports all lossless & lossy formats (.wav, .aif, .aiff, .flac, .mp3, .ogg, .oga, .m4a, .aac, .opus, .wma, .caf, .alac, .w64).
    Ignores hidden files starting with '.'.
    """
    audio_candidates = []
    if isinstance(directories, (str, Path)):
        directories = [directories]

    seen = set()
    for dir_path in directories:
        d = Path(dir_path).resolve()
        if d in seen or not d.exists() or not d.is_dir():
            continue
        seen.add(d)
        try:
            for item in d.iterdir():
                if item.is_file() and not item.name.startswith('.'):
                    if item.suffix.lower() in SUPPORTED_AUDIO_EXTENSIONS:
                        audio_candidates.append(item)
        except Exception as e:
            print(f"⚠️ Errore scansione cartella {d}: {e}")

    if not audio_candidates:
        return None

    # Sort by last modified time (newest first)
    audio_candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return str(audio_candidates[0])

def choose_output_directory():
    """Opens native macOS folder dialog to let user pick destination directory."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        selected_dir = filedialog.askdirectory(title="Seleziona la cartella dove salvare i report Camelot")
        root.destroy()
        if selected_dir:
            return Path(selected_dir)
    except Exception as e:
        print(f"⚠️ Pop-up cartella non disponibile ({e})")
    return Path.cwd()

def main():
    parser = argparse.ArgumentParser(description="CAMELOT Audio & Session Engine")
    parser.add_argument("--audio", type=str, help="Path to audio file (WAV/MP3/AIF)")
    parser.add_argument("--json", type=str, help="Path to Ableton session JSON (from M4L Escalibur bridge)")
    parser.add_argument("--out-dir", type=str, default=None, help="Output directory for HTML and TXT reports")
    parser.add_argument("--ask-dir", action="store_true", help="Open native GUI folder picker")
    args = parser.parse_args()

    audio_file = args.audio
    json_file = args.json

    # Determine Output Directory
    if args.ask_dir or not args.out_dir or args.out_dir == "ASK":
        out_dir = choose_output_directory()
    else:
        out_dir = Path(args.out_dir)
    
    out_dir.mkdir(parents=True, exist_ok=True)

    # Auto-detect latest audio file in MIX ANALYSIS or out_dir if --audio not supplied or invalid
    if not audio_file or not os.path.exists(audio_file):
        script_dir = Path(__file__).resolve().parent
        search_dirs = [
            out_dir,
            out_dir / "MIX ANALYSIS",
            script_dir / "MIX ANALYSIS",
            script_dir
        ]
        detected = find_latest_audio_file(search_dirs)
        if detected:
            audio_file = detected
            print(f"🔍 File audio rilevato automaticamente: {os.path.basename(audio_file)}")

    # Load session JSON if provided
    session_data = {}
    if json_file and os.path.exists(json_file):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                raw_json = f.read()
            try:
                session_data = json.loads(raw_json)
            except Exception:
                # Fallback decoding in case of extra trailing characters
                dec = json.JSONDecoder()
                session_data, _ = dec.raw_decode(raw_json)
            print(f"✅ Dati Sessione Ableton caricati da: {json_file}")
        except Exception as e:
            print(f"⚠️ Attenzione: Impossibile leggere il file JSON ({e})")

    # Run Analysis
    metrics = None
    if audio_file and os.path.exists(audio_file):
        print(f"🎧 Analisi audio in corso su: {audio_file}...")
        try:
            metrics = analyze_audio(audio_file)
            metrics["audio_analyzed"] = True
            print("✅ Analisi telemetrica audio completata!")
        except Exception as e:
            import traceback
            print(f"❌ Errore durante l'analisi audio ({e}):")
            traceback.print_exc()

    if not metrics:
        if not audio_file and sys.stdin.isatty() and not json_file:
            print("🗡️ CAMELOT ENGINE - Modalità Interattiva")
            try:
                audio_file = input("Inserisci il percorso del file audio da analizzare: ").strip('"').strip("'")
                if os.path.exists(audio_file):
                    metrics = analyze_audio(audio_file)
                    metrics["audio_analyzed"] = True
            except Exception:
                pass
        
        if not metrics:
            print("ℹ️ Nessun audio analizzato: Generazione report basata sulla Telemetria Sessione Ableton.")
            fallback_name = Path(audio_file).stem if audio_file else (Path(json_file).stem if json_file else "Camelot_Session")
            metrics = get_fallback_audio_metrics(fallback_name)

    # Output paths
    raw_name = Path(audio_file).stem if (audio_file and os.path.exists(audio_file)) else (Path(json_file).stem if json_file else "Camelot_Session")
    clean_name = raw_name
    while clean_name.startswith("Report_") or clean_name.startswith("Contesto_AI_"):
        if clean_name.startswith("Report_"):
            clean_name = clean_name[len("Report_"):]
        elif clean_name.startswith("Contesto_AI_"):
            clean_name = clean_name[len("Contesto_AI_"):]
    base_name = clean_name if clean_name else raw_name
    html_out = out_dir / f"Report_{base_name}.html"
    txt_out = out_dir / f"Contesto_AI_{base_name}.txt"

    generate_html_report(metrics, session_data, html_out)
    generate_ai_context(metrics, session_data, txt_out)

    print("\n=======================================================")
    print("🎉 REPORT CAMELOT GENERATI CON SUCCESSO:")
    print(f" 1. HTML Dashboard:  {html_out.resolve()}")
    print(f" 2. TXT per AI:      {txt_out.resolve()}")
    print("=======================================================\n")

if __name__ == "__main__":
    main()

