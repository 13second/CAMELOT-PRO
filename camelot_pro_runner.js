let Max;
try {
    Max = require('max-api');
} catch (e) {
    Max = {
        post: (msg) => console.log(msg),
        outlet: (out, ...args) => console.log(`[Outlet ${out}]`, ...args),
        addHandler: () => {}
    };
}

const { execFile, execFileSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const IS_MAC = process.platform === 'darwin';
const IS_WIN = process.platform === 'win32';

const scratchDir = __dirname;
const pythonScript = path.join(scratchDir, 'camelot.py');
const mixAnalysisDir = path.join(scratchDir, 'MIX ANALYSIS');

if (!fs.existsSync(mixAnalysisDir)) {
    fs.mkdirSync(mixAnalysisDir, { recursive: true });
}

function updateStatus(statusText) {
    Max.post(`[CAMELOT PRO] ${statusText}`);
    Max.outlet(0, statusText);
}

let cachedPythonBinary = null;

function pythonHasDspDeps(pyBin) {
    try {
        execFileSync(pyBin, ['-c', 'import numpy, scipy, soundfile, pyloudnorm'], {
            stdio: 'ignore',
            timeout: 5000,
            windowsHide: true
        });
        return true;
    } catch (e) {
        return false;
    }
}

// Find Python 3 binary with required DSP libraries across macOS, Windows, and Linux
function getPythonBinary() {
    if (cachedPythonBinary) return cachedPythonBinary;

    const candidatePaths = IS_WIN
        ? ['python', 'py', 'python3']
        : [
            '/Library/Frameworks/Python.framework/Versions/3.14/bin/python3',
            '/Library/Frameworks/Python.framework/Versions/3.13/bin/python3',
            '/Library/Frameworks/Python.framework/Versions/3.12/bin/python3',
            '/Library/Frameworks/Python.framework/Versions/3.11/bin/python3',
            '/opt/homebrew/bin/python3',
            '/usr/local/bin/python3',
            'python3'
        ];

    const existingCandidates = candidatePaths.filter(
        (p) => !p.includes('/') || fs.existsSync(p)
    );

    // 1. Prefer the first candidate that actually has all required DSP packages installed
    for (const p of existingCandidates) {
        if (pythonHasDspDeps(p)) {
            cachedPythonBinary = p;
            return p;
        }
    }

    // 2. Fallback to first existing binary
    cachedPythonBinary = existingCandidates[0] || (IS_WIN ? 'python' : 'python3');
    return cachedPythonBinary;
}

const SUPPORTED_EXTS = [
    '.wav', '.aif', '.aiff', '.flac', '.mp3', '.ogg', '.oga',
    '.m4a', '.aac', '.opus', '.wma', '.caf', '.alac', '.w64'
];

function isAudioFile(filename) {
    if (!filename || filename.startsWith('.') || filename.startsWith('._')) return false;
    const ext = path.extname(filename).toLowerCase();
    return SUPPORTED_EXTS.includes(ext);
}

let cachedSessionJsonPath = null;
let isAnalyzing = false;
let watcherInterval = null;

// Resolve camelot_session.json across known locations
function resolveSessionJson(hintPath) {
    const parentDir = path.dirname(scratchDir);
    const searchCandidates = [
        hintPath,
        cachedSessionJsonPath,
        path.join(scratchDir, 'camelot_session.json'),
        path.join(parentDir, 'camelot_session.json'),
        path.join(parentDir, 'CAMELOT ANALYSIS', 'camelot_session.json'),
        path.join(mixAnalysisDir, 'camelot_session.json')
    ];

    for (const p of searchCandidates) {
        if (p && fs.existsSync(p)) {
            return p;
        }
    }
    return null;
}

// Monitored search directories for audio files
function getSearchDirs() {
    const parentDir = path.dirname(scratchDir);
    return [
        mixAnalysisDir,
        scratchDir,
        path.join(parentDir, 'CAMELOT ANALYSIS', 'MIX ANALYSIS'),
        parentDir
    ];
}

// Snapshot of existing audio files across monitored directories
function getAudioFilesSnapshot() {
    const map = {};
    const dirs = getSearchDirs();
    for (const dir of dirs) {
        if (!fs.existsSync(dir)) continue;
        try {
            const items = fs.readdirSync(dir);
            for (const item of items) {
                if (isAudioFile(item)) {
                    const full = path.join(dir, item);
                    try {
                        const st = fs.statSync(full);
                        map[full] = { size: st.size, mtime: st.mtimeMs };
                    } catch (e) {}
                }
            }
        } catch (e) {}
    }
    return map;
}

// Find latest existing audio file (for fallback or manual run)
function findBestAudioFile() {
    const current = getAudioFilesSnapshot();
    let newestFile = null;
    let newestMtime = -1;

    for (const [full, info] of Object.entries(current)) {
        if (info.mtime > newestMtime) {
            newestMtime = info.mtime;
            newestFile = full;
        }
    }
    return newestFile;
}

// Cross-platform OS opener (uses execFile, no shell interpolation)
function openPathInOS(targetPath, label) {
    if (!targetPath || !fs.existsSync(targetPath)) return;
    if (IS_MAC) {
        execFile('open', [targetPath], (err) => {
            if (!err && label) Max.post(label);
        });
    } else if (IS_WIN) {
        execFile('cmd.exe', ['/c', 'start', '', targetPath], { windowsHide: true }, (err) => {
            if (!err && label) Max.post(label);
        });
    } else {
        execFile('xdg-open', [targetPath], (err) => {
            if (!err && label) Max.post(label);
        });
    }
}

// Trigger Ableton Live Export dialog (macOS AppleScript; guidance on Windows/Linux)
function triggerLiveExport() {
    if (!IS_MAC) {
        Max.post("🎹 Premi Ctrl+Shift+R in Ableton Live per esportare il brano dentro la cartella MIX ANALYSIS.");
        return;
    }

    const appleScript = `
tell application "System Events"
    set liveProc to first process whose name is "Live" or name contains "Ableton Live"
    if exists liveProc then
        set frontmost of liveProc to true
        delay 0.1
        try
            tell liveProc to keystroke "r" using {command down, shift down}
        on error
            try
                tell liveProc
                    set fileMenu to menu "File" of menu bar 1
                    set exportItem to first menu item of fileMenu whose (name starts with "Esporta Audio" or name starts with "Export Audio")
                    click exportItem
                end tell
            end try
        end try
    end if
end tell
`;
    execFile('osascript', ['-e', appleScript], (err) => {
        if (err) {
            Max.post(`⚠️ Avviso AppleScript (${err.message}). Se la finestra non compare, usa Cmd+Shift+R in Live.`);
        } else {
            Max.post("🎹 Finestra Esporta Audio/Video richiamata con successo su Ableton Live!");
        }
    });
}

// Start render watcher and trigger export
function startRenderAndWatch() {
    if (isAnalyzing) {
        Max.post("⚠️ Analisi o rendering già in corso...");
        return;
    }

    if (watcherInterval) {
        clearInterval(watcherInterval);
        watcherInterval = null;
    }

    updateStatus("ATTESA RENDER ⏳");
    Max.post("🚀 Avvio automazione di export e attivazione File Watcher...");

    // 1. Snapshot initial state of files before triggering export
    const initialFiles = getAudioFilesSnapshot();
    const renderStartTime = Date.now();

    // 2. Trigger Ableton Live's native Export dialog
    triggerLiveExport();

    let candidateFile = null;
    let candidateLastSize = -1;
    let candidateStableCount = 0;
    let ticks = 0;
    const MAX_TICKS = 850; // ~10 minutes timeout (850 * 700ms ≈ 600s)

    watcherInterval = setInterval(() => {
        ticks++;
        const currentFiles = getAudioFilesSnapshot();

        // Phase A: Detect new or modified audio file being written AFTER render trigger
        if (!candidateFile) {
            for (const [fPath, info] of Object.entries(currentFiles)) {
                const initial = initialFiles[fPath];
                const isNewFile = !initial;
                const isModifiedAfterStart = initial && (
                    (info.mtime > initial.mtime && info.mtime >= renderStartTime) ||
                    (info.size !== initial.size && info.mtime >= renderStartTime)
                );
                if (isNewFile || isModifiedAfterStart) {
                    candidateFile = fPath;
                    candidateLastSize = info.size;
                    candidateStableCount = 0;
                    const sizeMb = (info.size / (1024 * 1024)).toFixed(1);
                    updateStatus(`RENDERING... (${sizeMb} MB) 🎧`);
                    Max.post(`🔍 Rilevato file render in scrittura: ${path.basename(candidateFile)}`);
                    break;
                }
            }
        } else {
            // Phase B: Monitor candidateFile for write completion (file size stabilization)
            if (fs.existsSync(candidateFile)) {
                let curSize = 0;
                try {
                    curSize = fs.statSync(candidateFile).size;
                } catch (e) {
                    return;
                }

                if (curSize === candidateLastSize && curSize > 1024) {
                    candidateStableCount++;
                    // Require 4 consecutive identical sizes (~2.8 seconds stable)
                    if (candidateStableCount >= 4) {
                        clearInterval(watcherInterval);
                        watcherInterval = null;
                        const finalMb = (curSize / (1024 * 1024)).toFixed(2);
                        Max.post(`✅ Render completato con successo: ${path.basename(candidateFile)} (${finalMb} MB)`);
                        updateStatus("ANALISI DSP... 🚀");

                        const jsonPath = resolveSessionJson();
                        executePythonAnalysis(candidateFile, jsonPath);
                        return;
                    }
                } else {
                    candidateLastSize = curSize;
                    candidateStableCount = 0;
                    const sizeMb = (curSize / (1024 * 1024)).toFixed(1);
                    updateStatus(`RENDERING... (${sizeMb} MB) 🎧`);
                }
            }
        }

        // Phase C: Timeout handling
        if (ticks >= MAX_TICKS) {
            clearInterval(watcherInterval);
            watcherInterval = null;
            Max.post("⏱️ Timeout attesa render raggiunto (10 min).");
            const fallbackAudio = findBestAudioFile();
            if (fallbackAudio) {
                Max.post(`ℹ️ Analizzo file audio più recente disponibile: ${path.basename(fallbackAudio)}`);
                updateStatus("ANALISI DSP... 🚀");
                executePythonAnalysis(fallbackAudio, resolveSessionJson());
            } else {
                updateStatus("PRONTO");
            }
        }
    }, 700);
}

// Compute report base name with exact parity with camelot.py
function computeReportBaseName(audioPath, jsonPath) {
    let rawName = 'Camelot_Session';
    if (audioPath && fs.existsSync(audioPath)) {
        rawName = path.basename(audioPath, path.extname(audioPath));
    } else if (jsonPath && fs.existsSync(jsonPath)) {
        rawName = path.basename(jsonPath, path.extname(jsonPath));
    }

    let clean = rawName;
    while (clean.startsWith('Report_') || clean.startsWith('Contesto_AI_')) {
        if (clean.startsWith('Report_')) clean = clean.substring(7);
        else if (clean.startsWith('Contesto_AI_')) clean = clean.substring(12);
    }
    return clean || rawName;
}

// Execute camelot.py DSP analysis and generate HTML + TXT reports (via execFile, no shell)
function executePythonAnalysis(audioPath, jsonPath) {
    isAnalyzing = true;
    const pyBin = getPythonBinary();

    const args = [pythonScript, '--out-dir', mixAnalysisDir];
    if (audioPath && fs.existsSync(audioPath)) {
        args.push('--audio', audioPath);
        Max.post(`🎧 File Audio selezionato per analisi: ${path.basename(audioPath)}`);
    } else {
        Max.post("ℹ️ Nessun file audio: Generazione report da telemetria sessione Ableton");
    }

    if (jsonPath && fs.existsSync(jsonPath)) {
        args.push('--json', jsonPath);
        Max.post(`📋 Sessione caricata da: ${jsonPath}`);
    }

    Max.post(`🚀 Avvio Motore Camelot Pro: ${pyBin} ${args.join(' ')}`);

    execFile(pyBin, args, { maxBuffer: 1024 * 1024 * 10, windowsHide: true }, (error, stdout, stderr) => {
        isAnalyzing = false;
        if (stdout) {
            stdout.split('\n').forEach(line => {
                if (line.trim()) Max.post(`[Python] ${line}`);
            });
        }
        if (stderr) {
            stderr.split('\n').forEach(line => {
                if (line.trim()) Max.post(`[Python Err] ${line}`);
            });
        }

        if (error) {
            Max.post(`❌ Errore durante l'analisi Camelot: ${error.message}`);
            updateStatus("ERRORE ANALISI ❌");
        } else {
            Max.post("✅ Report Camelot Pro generati con successo!");
            updateStatus("REPORT PRONTO ✅");
            openResults(audioPath, jsonPath);
        }
    });
}

// Automatically open HTML report in default browser and folder in Finder/Explorer
function openResults(audioPath, jsonPath) {
    const baseName = computeReportBaseName(audioPath, jsonPath || resolveSessionJson());
    const htmlReportPath = path.join(mixAnalysisDir, `Report_${baseName}.html`);

    if (fs.existsSync(htmlReportPath)) {
        openPathInOS(htmlReportPath, `🌐 Dashboard HTML aperta nel browser: ${path.basename(htmlReportPath)}`);
    }

    openPathInOS(mixAnalysisDir, `📂 Cartella MIX ANALYSIS aperta: ${mixAnalysisDir}`);
}

function openReportFolder() {
    openPathInOS(mixAnalysisDir, `📂 Cartella report aperta: ${mixAnalysisDir}`);
}

// Max Event Handlers
Max.addHandler('bang', () => {
    startRenderAndWatch();
});

Max.addHandler('start', () => {
    startRenderAndWatch();
});

Max.addHandler('anything', (...args) => {
    Max.post(`ℹ️ Messaggio non riconosciuto ignorato dal runner: ${args.join(' ')}`);
});

Max.addHandler('session_file', (filePath) => {
    if (filePath) {
        cachedSessionJsonPath = filePath;
        Max.post(`📎 Percorso sessione registrato: ${filePath}`);
    }
});

Max.addHandler('audio', (audioPath) => {
    if (audioPath && fs.existsSync(audioPath)) {
        updateStatus("ANALISI DSP... 🚀");
        executePythonAnalysis(audioPath, resolveSessionJson());
    }
});

Max.addHandler('open_report', () => {
    const fallbackAudio = findBestAudioFile();
    openResults(fallbackAudio, resolveSessionJson());
});

Max.addHandler('open_folder', () => {
    openReportFolder();
});

updateStatus("PRONTO");
Max.post("🗡️ Camelot Pro Runner Inizializzato con Successo");

if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        getPythonBinary,
        isAudioFile,
        computeReportBaseName,
        resolveSessionJson
    };
}
