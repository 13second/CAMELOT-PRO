/*
===============================================================================
 CAMELOT LIVE LITE - REAL-TIME AUDIO TELEMETRY ENGINE (Max for Live JS)
 High-Performance, Ultra-Low CPU Audio Telemetry Engine for Ableton Live
 Conforming to ITU-R BS.1770-4, EBU R128 & AES-17 Standards
 Full Session Integration: Integrated LUFS, Integrated RMS, Max Peak, Integrated Crest
 ===============================================================================
*/

autowatch = 1;
inlets = 1;
outlets = 8;
// Outlet 0: LUFS Momentary (float LUFS)
// Outlet 1: LUFS Short-Term (float LUFS)
// Outlet 2: LUFS Integrated (float LUFS)
// Outlet 3: True Peak Max Hold (float dBTP)
// Outlet 4: [RMS Integrated (float dBFS), Crest Factor Integrated (float dB), PLR (float dB)]
// Outlet 5: Phase Correlation (-1.00 to +1.00)
// Outlet 6: [% Mid, % Side, M/S ratio dB]
// Outlet 7: Status / Text Alert string

// Constants
var EPSILON = 1e-12;
var SILENCE_THRESHOLD = 1e-8; // ~ -80 dBFS
var TICK_RATE_HZ = 20.0; // 50ms tick
var MOMENTARY_BLOCKS = Math.max(1, Math.round(0.4 * TICK_RATE_HZ)); // 400ms = 8 blocks
var SHORTTERM_BLOCKS = Math.max(1, Math.round(3.0 * TICK_RATE_HZ)); // 3.0s = 60 blocks

// Internal State
var sampleRate = 44100;
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

// Session-Integrated Metrics Accumulators
var rmsAccumEnergy = 0.0;
var rmsAccumCount = 0;
var lastIntegratedRMS = -99.0;
var maxHoldTruePeak = -99.0;
var lastIntegratedCrest = 0.0;
var phaseAccumDot = 0.0;
var phaseAccumEL = 0.0;
var phaseAccumER = 0.0;
var lastIntegratedPhase = 0.0;

// Reset All Telemetry Accumulators
function reset() {
    momentaryWindow = [];
    shorttermWindow = [];
    for (var h = 0; h < HIST_BINS; h++) histBins[h] = 0;
    histTotalCount = 0;
    lastIntegratedLUFS = -99.0;

    rmsAccumEnergy = 0.0;
    rmsAccumCount = 0;
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

function set_sample_rate(sr) {
    if (sr > 0) sampleRate = sr;
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

    // 0. Always capture maximum True Peak hold immediately across all pak inlet bursts
    var cur_tp_lin = Math.max(tp_l || 0.0, tp_r || 0.0, peak_l || 0.0, peak_r || 0.0, EPSILON);
    var cur_tp_db = Math.round(20.0 * (Math.log(cur_tp_lin) / Math.LN10) * 100) / 100;
    if (cur_tp_db > maxHoldTruePeak && cur_tp_lin >= 0.0001) {
        maxHoldTruePeak = cur_tp_db;
    }

    var now = new Date().getTime();
    if (now - lastProcessTime < 25) {
        // Debounce: previene sovracampionamenti multipli generati dai vettori di clock Max pak
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
    // k_pwr_l and k_pwr_r are linear RMS amplitudes from average~ rms in Max.
    // According to ITU-R BS.1770-4, mean square energy z_i = (RMS_i)^2.
    // Channel weighting: G_L = 1.0 (0 dB), G_R = 1.0 (0 dB) -> z = z_L + z_R.
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

    // Integrated LUFS (Dual-Gated Accumulation: Absolute gate at -70.0 LUFS)
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
    // 2. TRUE PEAK (MAX PEAK HOLD ACROSS SESSION)
    // -------------------------------------------------------------------------
    var max_tp_lin = Math.max(tp_l, tp_r, peak_l, peak_r, EPSILON);
    var instant_tp_db = 20.0 * (Math.log(max_tp_lin) / Math.LN10);
    instant_tp_db = Math.round(instant_tp_db * 100) / 100;

    if (instant_tp_db > maxHoldTruePeak) {
        maxHoldTruePeak = instant_tp_db;
    }

    // -------------------------------------------------------------------------
    // 3. RMS (INTEGRATED CUMULATIVE ENERGY AES-17, GATED ABOVE -60 LUFS)
    // -------------------------------------------------------------------------
    var stereo_energy = 0.5 * (rms_energy_l + rms_energy_r) + EPSILON;
    var block_rms_db = 10.0 * (Math.log(stereo_energy) / Math.LN10);
    if (lufs_momentary >= -60.0 && block_rms_db >= -60.0) {
        rmsAccumEnergy += stereo_energy;
        rmsAccumCount++;
    }

    if (rmsAccumCount > 0) {
        var meanEnergy = rmsAccumEnergy / rmsAccumCount;
        var rms_int_db = 10.0 * (Math.log(meanEnergy + EPSILON) / Math.LN10);
        rms_int_db = Math.round(rms_int_db * 10) / 10;
        lastIntegratedRMS = rms_int_db;
    }

    // -------------------------------------------------------------------------
    // 4. CREST FACTOR (INTEGRATED SESSION DYNAMICS: TP_max - RMS_int)
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
    // 5. L/R PHASE CORRELATION (INTEGRATED CUMULATIVE SESSION COHERENCE)
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
    // 6. STEREO WIDTH & MID/SIDE
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
    // 7. OUTPUT ROUTING (INTEGRATED METRICS)
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
