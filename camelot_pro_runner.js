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

const { exec } = require('child_process');
const path = require('path');
const fs = require('fs');

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

// Find Python 3 binary with required DSP libraries
function getPythonBinary() {
    const candidatePaths = [
        '/Library/Frameworks/Python.framework/Versions/3.14/bin/python3',
        '/Library/Frameworks/Python.framework/Versions/3.13/bin/python3',
        '/Library/Frameworks/Python.framework/Versions/3.12/bin/python3',
        '/Library/Frameworks/Python.framework/Versions/3.11/bin/python3',
        '/opt/homebrew/bin/python3',
        '/usr/local/bin/python3',
        'python3'
    ];
    for (const p of candidatePaths) {
        if (p === 'python3' || fs.existsSync(p)) {
            return p;
        }
    }
    return 'python3';
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

// AppleScript automation: Bring Ableton Live frontmost and simulate Cmd + Shift + R
function triggerAppleScriptExport() {
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
    exec(`osascript -e '${appleScript.replace(/'/g, "'\\''")}'`, (err) => {
        if (err) {
            Max.post(`⚠️ Avviso AppleScript (${err.message}). Se la finestra non compare, usa Cmd+Shift+R in Live.`);
        } else {
            Max.post(`🎹 Finestra Esporta Audio/Video richiamata con successo su Ableton Live!`);
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
    triggerAppleScriptExport();

    let candidateFile = null;
    let candidateLastSize = -1;
    let candidateStableCount = 0;
    let ticks = 0;
    const MAX_TICKS = 850; // ~10 minutes timeout (850 * 700ms ≈ 600s)

    watcherInterval = setInterval(() => {
        ticks++;
        const currentFiles = getAudioFilesSnapshot();

        // Phase A: Detect new or modified audio file being written
        if (!candidateFile) {
            for (const [fPath, info] of Object.entries(currentFiles)) {
                const initial = initialFiles[fPath];
                // Case 1: Newly created file
                // Case 2: File modified after render trigger with size/mtime change
                if (!initial || info.mtime >= (renderStartTime - 1000) || (info.size !== initial.size && info.mtime > renderStartTime)) {
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
                    // Require 3 consecutive identical sizes (~2.1 seconds stable)
                    if (candidateStableCount >= 3) {
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

// Execute camelot.py DSP analysis and generate HTML + TXT reports
function executePythonAnalysis(audioPath, jsonPath) {
    isAnalyzing = true;
    const pyBin = getPythonBinary();

    let cmd = `"${pyBin}" "${pythonScript}" --out-dir "${mixAnalysisDir}"`;
    if (audioPath && fs.existsSync(audioPath)) {
        cmd += ` --audio "${audioPath}"`;
        Max.post(`🎧 File Audio selezionato per analisi: ${path.basename(audioPath)}`);
    } else {
        Max.post(`ℹ️ Nessun file audio: Generazione report da telemetria sessione Ableton`);
    }

    if (jsonPath && fs.existsSync(jsonPath)) {
        cmd += ` --json "${jsonPath}"`;
        Max.post(`📋 Sessione caricata da: ${jsonPath}`);
    }

    Max.post(`🚀 Avvio Motore Camelot Pro: ${cmd}`);

    exec(cmd, { maxBuffer: 1024 * 1024 * 10 }, (error, stdout, stderr) => {
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
            Max.post(`✅ Report Camelot Pro generati con successo!`);
            updateStatus("REPORT PRONTO ✅");
            openResults(audioPath);
        }
    });
}

// Automatically open HTML report in default browser and folder in Finder
function openResults(audioPath) {
    // 1. Open generated HTML report in default browser
    let baseName = "Camelot_Session";
    if (audioPath) {
        let clean = path.basename(audioPath, path.extname(audioPath));
        while (clean.startsWith('Report_') || clean.startsWith('Contesto_AI_')) {
            if (clean.startsWith('Report_')) clean = clean.substring(7);
            else if (clean.startsWith('Contesto_AI_')) clean = clean.substring(12);
        }
        baseName = clean;
    }
    const htmlReportPath = path.join(mixAnalysisDir, `Report_${baseName}.html`);

    if (fs.existsSync(htmlReportPath)) {
        exec(`open "${htmlReportPath}"`, (err) => {
            if (!err) Max.post(`🌐 Dashboard HTML aperta nel browser: ${path.basename(htmlReportPath)}`);
        });
    }

    // 2. Open MIX ANALYSIS folder in macOS Finder
    exec(`open "${mixAnalysisDir}"`, (err) => {
        if (!err) Max.post(`📂 Cartella MIX ANALYSIS aperta nel Finder: ${mixAnalysisDir}`);
    });
}

function openReportFolder() {
    exec(`open "${mixAnalysisDir}"`, (err) => {
        if (!err) {
            Max.post(`📂 Cartella report aperta: ${mixAnalysisDir}`);
        }
    });
}

// Max Event Handlers
Max.addHandler('bang', () => {
    startRenderAndWatch();
});

Max.addHandler('start', () => {
    startRenderAndWatch();
});

Max.addHandler('anything', (...args) => {
    startRenderAndWatch();
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
    openResults(fallbackAudio);
});

Max.addHandler('open_folder', () => {
    openReportFolder();
});

updateStatus("PRONTO");
Max.post("🗡️ Camelot Pro Runner Inizializzato con Successo");
