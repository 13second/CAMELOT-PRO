#!/bin/bash
# ==============================================================================
#  CAMELOT PRO — ONE-CLICK INSTALLER FOR macOS (Ableton Live / Max for Live)
# ==============================================================================

clear
echo "======================================================================"
echo " 🗡️  CAMELOT PRO — INSTALLER AUTOMATICO (macOS)"
echo "     Real-Time Audio Telemetry, Vectorscope & AI Session Analyzer"
echo "======================================================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

# 1. Rimuove eventuali attributi di quarantena macOS (Gatekeeper) e file ._
echo "🔧 [1/4] Pulizia attributi di sicurezza macOS (xattr) e file temporanei..."
xattr -cr "$SCRIPT_DIR" 2>/dev/null
find "$SCRIPT_DIR" -name "._*" -delete 2>/dev/null
echo "   ✅ Attributi verificati."
echo ""

# 2. Individua esattamente il Python 3 usato da camelot_pro_runner.js
echo "🐍 [2/4] Ricerca di Python 3 compatibile con Max for Live..."
CANDIDATE_PYTHONS=(
    "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
    "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
    "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3"
    "/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
    "$(command -v python3)"
)

SELECTED_PYTHON=""
for py in "${CANDIDATE_PYTHONS[@]}"; do
    if [ -n "$py" ] && [ -x "$py" ]; then
        SELECTED_PYTHON="$py"
        break
    fi
done

if [ -z "$SELECTED_PYTHON" ]; then
    echo "❌ ERRORE: Python 3 non trovato sul tuo Mac."
    echo "👉 Scarica e installa Python 3 da: https://www.python.org/downloads/macos/"
    echo "   Poi fai nuovamente doppio clic su Install_Camelot_Pro.command."
    echo ""
    read -n 1 -s -r -p "Premi un tasto qualsiasi per chiudere..."
    exit 1
fi

PY_VERSION=$("$SELECTED_PYTHON" --version 2>&1)
echo "   ✅ Trovato: $PY_VERSION ($SELECTED_PYTHON)"
echo ""

# 3. Installazione librerie DSP (numpy, scipy, soundfile, pyloudnorm)
echo "📦 [3/4] Installazione librerie DSP (numpy, scipy, soundfile, pyloudnorm)..."
"$SELECTED_PYTHON" -m pip install --upgrade pip --quiet 2>/dev/null

if ! "$SELECTED_PYTHON" -m pip install -r "$SCRIPT_DIR/requirements.txt" --quiet 2>/dev/null; then
    # Fallback per Python 3.12+ (PEP 668 externally-managed-environment su Homebrew)
    "$SELECTED_PYTHON" -m pip install --user --break-system-packages -r "$SCRIPT_DIR/requirements.txt" || \
    "$SELECTED_PYTHON" -m pip install --break-system-packages -r "$SCRIPT_DIR/requirements.txt"
fi

# Verifica importazione librerie
if "$SELECTED_PYTHON" -c "import numpy, scipy, soundfile, pyloudnorm" 2>/dev/null; then
    echo "   ✅ Tutte le librerie DSP sono installate e funzionanti!"
else
    echo "   ⚠️ Attenzione: Impossibile verificare alcune librerie Python. Controlla la connessione internet."
fi
echo ""

# 4. Installazione nella User Library di Ableton Live (se non si trova già lì)
echo "🎹 [4/4] Configurazione cartella Ableton Live User Library..."
mkdir -p "$SCRIPT_DIR/MIX ANALYSIS"

DEFAULT_ABLETON_DIR="$HOME/Music/Ableton/User Library/Presets/Audio Effects/Max Audio Effect"
TARGET_DIR="$DEFAULT_ABLETON_DIR/CAMELOT PRO"

if [[ "$SCRIPT_DIR" == *"Max Audio Effect"* ]]; then
    echo "   ✅ CAMELOT PRO si trova già dentro la tua cartella Max Audio Effect:"
    echo "      $SCRIPT_DIR"
elif [ -d "$HOME/Music/Ableton/User Library" ]; then
    mkdir -p "$TARGET_DIR/MIX ANALYSIS"
    cp -f "$SCRIPT_DIR/Camelot_Pro.amxd" "$TARGET_DIR/" 2>/dev/null
    cp -f "$SCRIPT_DIR/camelot.py" "$TARGET_DIR/" 2>/dev/null
    cp -f "$SCRIPT_DIR/camelot_live_lite.js" "$TARGET_DIR/" 2>/dev/null
    cp -f "$SCRIPT_DIR/camelot_pro_m4l.js" "$TARGET_DIR/" 2>/dev/null
    cp -f "$SCRIPT_DIR/camelot_pro_runner.js" "$TARGET_DIR/" 2>/dev/null
    cp -f "$SCRIPT_DIR/vectorscope.js" "$TARGET_DIR/" 2>/dev/null
    cp -f "$SCRIPT_DIR/requirements.txt" "$TARGET_DIR/" 2>/dev/null
    cp -f "$SCRIPT_DIR/README.txt" "$TARGET_DIR/" 2>/dev/null
    xattr -cr "$TARGET_DIR" 2>/dev/null
    echo "   ✅ CAMELOT PRO copiato automaticamente nella tua User Library di Ableton:"
    echo "      $TARGET_DIR"
else
    echo "   ℹ️ Cartella standard '$HOME/Music/Ableton/User Library' non trovata."
    echo "   👉 Se usi una User Library su disco esterno, copia l'intera cartella"
    echo "      'CAMELOT PRO' dentro: User Library/Presets/Audio Effects/Max Audio Effect/"
fi

echo ""
echo "======================================================================"
echo " 🎉 INSTALLAZIONE COMPLETATA CON SUCCESSO!"
echo "======================================================================"
echo " Come usare CAMELOT PRO in Ableton Live:"
echo "  1. Apri Ableton Live e vai in: User Library > Presets > Audio Effects > Max Audio Effect > CAMELOT PRO"
echo "  2. Trascina 'Camelot_Pro.amxd' sul canale MASTER."
echo "  3. Riproduci la traccia per usare la Telemetria Real-Time (LUFS, True Peak, Vectorscope 60fps)."
echo "  4. Clicca su 'SCAN & ANALYZE' per esportare e generare la Dashboard HTML + Contesto AI!"
echo "======================================================================"
echo ""
read -n 1 -s -r -p "Premi un tasto qualsiasi per chiudere questa finestra..."
echo ""

