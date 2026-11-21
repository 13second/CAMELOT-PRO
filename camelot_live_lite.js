/*
===============================================================================
 CAMELOT LIVE LITE - REAL-TIME AUDIO TELEMETRY ENGINE (Max for Live JS)
 High-Performance, Ultra-Low CPU Audio Telemetry Engine for Ableton Live
 Conforming to ITU-R BS.1770-4, EBU R128 & AES-17 Standards
 Full Session Integration: Integrated LUFS, Dual-Gated RMS, Max Peak, Crest
 Dynamic Sample-Rate K-Weighting & Window Adaptation (44.1 / 48 / 88.2 / 96+ kHz)
 ===============================================================================
*/

autowatch = 1;
inlets = 1;
outlets = 9;
// Outlet 0: LUFS Momentary (float LUFS)
// Outlet 1: LUFS Short-Term (float LUFS)
// Outlet 2: LUFS Integrated (float LUFS)
// Outlet 3: True Peak Max Hold (float dBTP)
// Outlet 4: [RMS Integrated (float dBFS), Crest Factor Integrated (float dB), PLR (float dB)]
// Outlet 5: Phase Correlation (-1.00 to +1.00)
// Outlet 6: [% Mid, % Side, M/S ratio dB]
// Outlet 7: Status / Text Alert string
// Outlet 8: DSP Config messages (k_shelf, k_hp, rms_win, k_win, phase_win)

// Constants
var EPSILON = 1e-12;
var SILENCE_THRESHOLD = 1e-8; // ~ -80 dBFS
var TICK_RATE_HZ = 20.0; // 50ms tick
var MOMENTARY_BLOCKS = Math.max(1, Math.round(0.4 * TICK_RATE_HZ)); // 400ms = 8 blocks
var SHORTTERM_BLOCKS = Math.max(1, Math.round(3.0 * TICK_RATE_HZ)); // 3.0s = 60 blocks

// Internal State
var sampleRate = 48000;
var isPlaying = false; // Default to false until Live transport starts!

// Loudness Buffers
var momentaryWindow = [];
var shorttermWindow = [];

// ITU-R BS.1770-4 Dual-Gating Histogram (-70.0 to +10.0 LUFS with 0.1 LU bins)
var HIST_MIN_LUFS = -70.0;
var HIST_BINS = 801;
var histBins = new Array(HIST_BINS);
var binPower = new Array(HIST_BINS);
for (var h = 0; h < HIST_BINS; h++) {
    histBins[h] = 0;
    var lufsV_init = HIST_MIN_LUFS + (h * 0.1);
    binPower[h] = Math.pow(10.0, (lufsV_init + 0.691) / 10.0);
}
var histTotalCount = 0;
var lastIntegratedLUFS = -99.0;
var lastProcessTime = 0;

// Dual-Gated RMS Histogram (-60.0 to +6.0 dBFS with 0.1 dB bins, parity with camelot.py)
var RMS_HIST_MIN_DB = -60.0;
var RMS_HIST_BINS = 661;
var rmsHistBins = new Array(RMS_HIST_BINS);
var rmsBinPower = new Array(RMS_HIST_BINS);
for (var rh = 0; rh < RMS_HIST_BINS; rh++) {
    rmsHistBins[rh] = 0;
    var rmsDbInit = RMS_HIST_MIN_DB + (rh * 0.1);
    rmsBinPower[rh] = Math.pow(10.0, rmsDbInit / 10.0);
}
var rmsHistTotalCount = 0;
var lastIntegratedRMS = -99.0;
var maxHoldTruePeak = -99.0;
var lastIntegratedCrest = 0.0;
var phaseAccumDot = 0.0;
var phaseAccumEL = 0.0;
var phaseAccumER = 0.0;
var lastIntegratedPhase = 0.0;

// Compute exact ITU-R BS.1770-4 K-Weighting biquad coefficients for arbitrary sample rate
// Returns Max biquad~ order: [b0, b1, b2, a1, a2]
function compute_k_weighting_coeffs(fs) {
    var sr = (fs && fs >= 8000) ? fs : 48000;

    // Stage 1: High-Shelf (+3.999843853973347 dB, Q = 0.7071752369554196, fc = 1681.974450955533 Hz)
    var db = 3.999843853973347;
    var f0 = 1681.974450955533;
    var Q = 0.7071752369554196;
    var K = Math.tan(Math.PI * f0 / sr);
    var Vh = Math.pow(10.0, db / 20.0);
    var Vb = Math.pow(Vh, 0.4996667741545416);
    var a0_s = 1.0 + K / Q + K * K;
    var shelf = [
        (Vh + Vb * K / Q + K * K) / a0_s,
        2.0 * (K * K - Vh) / a0_s,
        (Vh - Vb * K / Q + K * K) / a0_s,
        2.0 * (K * K - 1.0) / a0_s,
        (1.0 - K / Q + K * K) / a0_s
    ];

    // Stage 2: High-Pass (Q = 0.5003270373238773, fc = 38.13547087602444 Hz)
    var f0_hp = 38.13547087602444;
    var Q_hp = 0.5003270373238773;
    var K_hp = Math.tan(Math.PI * f0_hp / sr);
    var a0_h = 1.0 + K_hp / Q_hp + K_hp * K_hp;
    var hp = [
        1.0,
        -2.0,
        1.0,
        2.0 * (K_hp * K_hp - 1.0) / a0_h,
        (1.0 - K_hp / Q_hp + K_hp * K_hp) / a0_h
    ];

    return { shelf: shelf, hp: hp };
}

function set_sample_rate(sr) {
    if (!sr || sr < 8000) return;
    sampleRate = sr;
    var coeffs = compute_k_weighting_coeffs(sampleRate);
    var rmsWin = Math.max(64, Math.round(sampleRate * 0.30));    // ~300ms RMS window
    var kWin = Math.max(32, Math.round(sampleRate * 0.10));      // ~100ms K-weighted block
    var phaseWin = Math.max(32, Math.round(sampleRate * 0.05));  // ~50ms phase window

    outlet(8, "k_shelf", coeffs.shelf[0], coeffs.shelf[1], coeffs.shelf[2], coeffs.shelf[3], coeffs.shelf[4]);
    outlet(8, "k_hp", coeffs.hp[0], coeffs.hp[1], coeffs.hp[2], coeffs.hp[3], coeffs.hp[4]);
    outlet(8, "rms_win", rmsWin);
    outlet(8, "k_win", kWin);
    outlet(8, "phase_win", phaseWin);
}

// Reset All Telemetry Accumulators
function reset() {
    momentaryWindow = [];
    shorttermWindow = [];
    for (var h = 0; h < HIST_BINS; h++) histBins[h] = 0;
    histTotalCount = 0;
    lastIntegratedLUFS = -99.0;

    for (var rh = 0; rh < RMS_HIST_BINS; rh++) rmsHistBins[rh] = 0;
    rmsHistTotalCount = 0;
    lastIntegratedRMS = -99.0;
    maxHoldTruePeak = -99.0;
    lastIntegratedCrest = 0.0;
    phaseAccumDot = 0.0;
    phaseAccumEL = 0.0;
    phaseAccumER = 0.0;
    lastIntegratedPhase = 0.0;
    lastProcessTime = 0;

    outlet(0, -99.0);
    outlet(1, -99.0);
    outlet(2, -99.0);
    outlet(3, -99.0);
    outlet(4, [-99.0, 0.0, 0.0]);
    outlet(5, 0.0);
    outlet(6, [0.0, 0.0, 0.0]);
    outlet(7, "Reset telemetria completato");
}

function set_playing(state) {
    isPlaying = (state === 1 || state === true);
    if (!isPlaying) {
        // KEEP ALL 5 INTEGRATED METRICS (INCLUDING PHASE) FROZEN ON DISPLAY WHEN STOPPED!
        outlet(0, -99.0);
        outlet(1, -99.0);
        outlet(2, (histTotalCount > 0) ? lastIntegratedLUFS : -99.0);
        outlet(3, maxHoldTruePeak);
        outlet(4, [lastIntegratedRMS, lastIntegratedCrest, 0.0]);
        outlet(5, lastIntegratedPhase);
        outlet(6, [0.0, 0.0, 0.0]);
        outlet(7, "⏹️ PLAYBACK FERMO (STATISTICHE INTEGRATE CONGELATE)");
    }
}

// Support for both 'is_playing' message from Max live.observer and 'set_playing'
function is_playing(state) {
    set_playing(state);
}

/**
 * Main telemetry process tick called by Max timer (qmetro 50ms = 20Hz)
 */
function process_telemetry(rms_l, rms_r, peak_l, peak_r, k_pwr_l, k_pwr_r, tp_l, tp_r, dot_lr, energy_l, energy_r) {
    if (!isPlaying) {
        return;
    }

    // 0. Capture maximum True Peak hold (guarded against silence floor)
    var cur_tp_lin = Math.max(tp_l || 0.0, tp_r || 0.0, peak_l || 0.0, peak_r || 0.0, EPSILON);
    var cur_tp_db = Math.round(20.0 * (Math.log(cur_tp_lin) / Math.LN10) * 100) / 100;
    if (cur_tp_db > maxHoldTruePeak && cur_tp_lin >= 0.0001) {
        maxHoldTruePeak = cur_tp_db;
    }

    var now = new Date().getTime();
    if (now - lastProcessTime < 25) {
        return;
    }
    lastProcessTime = now;

    var rms_energy_l = (rms_l * rms_l) || energy_l || 0.0;
    var rms_energy_r = (rms_r * rms_r) || energy_r || 0.0;
    var raw_energy = Math.max(energy_l + energy_r, rms_energy_l + rms_energy_r);
    var hasAudio = (raw_energy >= SILENCE_THRESHOLD);

    // Silence guard: hold integrated values on display when silent or stopped
    if (!hasAudio) {
        outlet(0, -99.0);
        outlet(1, -99.0);
        outlet(2, (histTotalCount > 0) ? lastIntegratedLUFS : -99.0);
        outlet(3, maxHoldTruePeak);
        outlet(4, [lastIntegratedRMS, lastIntegratedCrest, 0.0]);
        outlet(5, lastIntegratedPhase);
        outlet(6, [0.0, 0.0, 0.0]);
        outlet(7, isPlaying ? "🟢 IN ATTESA DI SEGNALE AUDIO..." : "⏹️ PLAYBACK FERMO");
        return;
    }

    // -------------------------------------------------------------------------
    // 1. LUFS INTEGRATED CALCULATION (ITU-R BS.1770-4 / EBU R128)
    // -------------------------------------------------------------------------
    var p_k_l = k_pwr_l * k_pwr_l;
    var p_k_r = k_pwr_r * k_pwr_r;
    var p_k = Math.max(p_k_l + p_k_r, EPSILON);

    // Momentary LUFS (400ms)
    momentaryWindow.push(p_k);
    if (momentaryWindow.length > MOMENTARY_BLOCKS) momentaryWindow.shift();
    var sum_m = 0.0;
    for (var m = 0; m < momentaryWindow.length; m++) sum_m += momentaryWindow[m];
    var avg_m = sum_m / momentaryWindow.length;
    var lufs_momentary = -0.691 + 10.0 * (Math.log(avg_m + EPSILON) / Math.LN10);

    // Short-Term LUFS (3.0s)
    shorttermWindow.push(p_k);
    if (shorttermWindow.length > SHORTTERM_BLOCKS) shorttermWindow.shift();
    var sum_st = 0.0;
    for (var s = 0; s < shorttermWindow.length; s++) sum_st += shorttermWindow[s];
    var avg_st = sum_st / shorttermWindow.length;
    var lufs_shortterm = -0.691 + 10.0 * (Math.log(avg_st + EPSILON) / Math.LN10);

    // Integrated LUFS (Dual-Gated Accumulation: Absolute gate -70 LUFS, Relative gate -10 LU)
    if (lufs_momentary >= HIST_MIN_LUFS) {
        var binIdx = Math.round((lufs_momentary - HIST_MIN_LUFS) * 10);
        if (binIdx >= 0) {
            if (binIdx >= HIST_BINS) binIdx = HIST_BINS - 1;
            histBins[binIdx]++;
            histTotalCount++;
        }
    }

    if (histTotalCount > 0) {
        var sumPowerAbs = 0.0;
        var countAbs = 0;
        for (var b = 0; b < HIST_BINS; b++) {
            var count = histBins[b];
            if (count > 0) {
                sumPowerAbs += count * binPower[b];
                countAbs += count;
            }
        }

        if (countAbs > 0) {
            var meanPowerAbs = sumPowerAbs / countAbs;
            var lufsAbsMean = -0.691 + 10.0 * (Math.log(meanPowerAbs + EPSILON) / Math.LN10);
            var relThresholdLUFS = lufsAbsMean - 10.0;
            var relBinStart = Math.max(0, Math.floor((relThresholdLUFS - HIST_MIN_LUFS) * 10) + 1);

            var sumPowerRel = 0.0;
            var countRel = 0;
            for (var rb = relBinStart; rb < HIST_BINS; rb++) {
                var c = histBins[rb];
                if (c > 0) {
                    sumPowerRel += c * binPower[rb];
                    countRel += c;
                }
            }

            if (countRel > 0) {
                var meanPowerRel = sumPowerRel / countRel;
                var lufs_int_calc = -0.691 + 10.0 * (Math.log(meanPowerRel + EPSILON) / Math.LN10);
                lastIntegratedLUFS = Math.round(lufs_int_calc * 10) / 10;
            }
        }
    }

    lufs_momentary = Math.max(-99.0, Math.round(lufs_momentary * 10) / 10);
    lufs_shortterm = Math.max(-99.0, Math.round(lufs_shortterm * 10) / 10);
    var lufs_integrated = (histTotalCount > 0) ? lastIntegratedLUFS : -99.0;

    // -------------------------------------------------------------------------
    // 2. RMS (DUAL-GATED INTEGRATED ENERGY: Abs > -60 dBFS, Rel >= -10 dB)
    //    Exact mathematical parity with camelot.py
    // -------------------------------------------------------------------------
    var stereo_energy = 0.5 * (rms_energy_l + rms_energy_r) + EPSILON;
    var block_rms_db = 10.0 * (Math.log(stereo_energy) / Math.LN10);
    if (block_rms_db >= RMS_HIST_MIN_DB) {
        var rmsBinIdx = Math.round((block_rms_db - RMS_HIST_MIN_DB) * 10);
        if (rmsBinIdx >= 0) {
            if (rmsBinIdx >= RMS_HIST_BINS) rmsBinIdx = RMS_HIST_BINS - 1;
            rmsHistBins[rmsBinIdx]++;
            rmsHistTotalCount++;
        }
    }

    if (rmsHistTotalCount > 0) {
        var rmsSumAbs = 0.0;
        var rmsCntAbs = 0;
        for (var rbi = 0; rbi < RMS_HIST_BINS; rbi++) {
            var rc = rmsHistBins[rbi];
            if (rc > 0) {
                rmsSumAbs += rc * rmsBinPower[rbi];
                rmsCntAbs += rc;
            }
        }
        if (rmsCntAbs > 0) {
            var rmsMeanAbs = rmsSumAbs / rmsCntAbs;
            var rmsAbsDb = 10.0 * (Math.log(rmsMeanAbs + EPSILON) / Math.LN10);
            var rmsRelThreshDb = rmsAbsDb - 10.0;
            var rmsRelStart = Math.max(0, Math.floor((rmsRelThreshDb - RMS_HIST_MIN_DB) * 10));

            var rmsSumRel = 0.0;
            var rmsCntRel = 0;
            for (var rri = rmsRelStart; rri < RMS_HIST_BINS; rri++) {
                var rrc = rmsHistBins[rri];
                if (rrc > 0) {
                    rmsSumRel += rrc * rmsBinPower[rri];
                    rmsCntRel += rrc;
                }
            }
            var finalRmsEnergy = (rmsCntRel > 0) ? (rmsSumRel / rmsCntRel) : rmsMeanAbs;
            var rms_int_db = 10.0 * (Math.log(finalRmsEnergy + EPSILON) / Math.LN10);
            lastIntegratedRMS = Math.round(rms_int_db * 10) / 10;
        }
    }

    // -------------------------------------------------------------------------
    // 3. CREST FACTOR (INTEGRATED SESSION DYNAMICS: TP_max - RMS_int)
    // -------------------------------------------------------------------------
    var integrated_crest = 0.0;
    if (maxHoldTruePeak > -90.0 && lastIntegratedRMS > -90.0) {
        integrated_crest = maxHoldTruePeak - lastIntegratedRMS;
        integrated_crest = Math.max(0.0, Math.round(integrated_crest * 10) / 10);
        lastIntegratedCrest = integrated_crest;
    }

    var plr_shortterm = (lufs_shortterm > -90.0 && maxHoldTruePeak > -90.0) ? (maxHoldTruePeak - lufs_shortterm) : 0.0;
    plr_shortterm = Math.round(plr_shortterm * 10) / 10;

    // -------------------------------------------------------------------------
    // 4. L/R PHASE CORRELATION (INTEGRATED CUMULATIVE SESSION COHERENCE)
    // -------------------------------------------------------------------------
    var norm_l = Math.sqrt(energy_l + EPSILON);
    var norm_r = Math.sqrt(energy_r + EPSILON);
    var phase_corr = lastIntegratedPhase;

    if (norm_l > 0.0001 && norm_r > 0.0001) {
        phaseAccumDot += dot_lr;
        phaseAccumEL += energy_l;
        phaseAccumER += energy_r;
        var int_norm = Math.sqrt((phaseAccumEL + EPSILON) * (phaseAccumER + EPSILON));
        if (int_norm > 0.0001) {
            phase_corr = phaseAccumDot / int_norm;
        } else {
            phase_corr = dot_lr / (norm_l * norm_r);
        }
        phase_corr = Math.max(-1.0, Math.min(1.0, phase_corr));
        phase_corr = Math.round(phase_corr * 100) / 100;
        lastIntegratedPhase = phase_corr;
    }

    // -------------------------------------------------------------------------
    // 5. STEREO WIDTH & MID/SIDE
    // -------------------------------------------------------------------------
    var energy_mid = 0.5 * (energy_l + energy_r + 2.0 * dot_lr);
    var energy_side = 0.5 * (energy_l + energy_r - 2.0 * dot_lr);
    energy_mid = Math.max(0.0, energy_mid);
    energy_side = Math.max(0.0, energy_side);
    var total_ms = energy_mid + energy_side + EPSILON;

    var pct_mid = Math.round((energy_mid / total_ms) * 1000) / 10;
    var pct_side = Math.round((energy_side / total_ms) * 1000) / 10;
    var ms_ratio_db = 10.0 * (Math.log((energy_side + EPSILON) / (energy_mid + EPSILON)) / Math.LN10);
    ms_ratio_db = Math.round(ms_ratio_db * 10) / 10;

    // -------------------------------------------------------------------------
    // 6. OUTPUT ROUTING (INTEGRATED METRICS)
    // -------------------------------------------------------------------------
    outlet(0, lufs_momentary);
    outlet(1, lufs_shortterm);
    outlet(2, lufs_integrated);
    outlet(3, maxHoldTruePeak); // INTEGRATED MAX PEAK HOLD!
    outlet(4, [lastIntegratedRMS, lastIntegratedCrest, plr_shortterm]); // INTEGRATED RMS & CREST!
    outlet(5, phase_corr);
    outlet(6, [pct_mid, pct_side, ms_ratio_db]);

    var status_msg = "OK";
    if (maxHoldTruePeak > 0.0) {
        status_msg = "⚠️ CLIPPING TRUE PEAK! (" + maxHoldTruePeak + " dBTP)";
    } else if (phase_corr < 0.0) {
        status_msg = "⚠️ CONTROFASE GRAVE (" + phase_corr + ")";
    } else if (phase_corr < 0.25) {
        status_msg = "⚠️ ATTENZIONE FASE MONO (" + phase_corr + ")";
    } else if (lufs_integrated > -8.0 && lufs_integrated < 0.0) {
        status_msg = "🔥 MASTER MOLTO CALDO (" + lufs_integrated + " LUFS)";
    } else {
        status_msg = "🟢 TELEMETRIA OTTIMALE | Fase: " + phase_corr;
    }
    outlet(7, status_msg);
}
