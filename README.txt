===============================================================================
 🗡️ CAMELOT PRO — Audio Telemetry, 60 FPS Vectorscope & AI Session Analyzer
    Guida di Installazione e Utilizzo per Ableton Live (Max for Live)
===============================================================================

CAMELOT PRO è una suite avanzata per Ableton Live (Max for Live + Python DSP)
che unisce:
1. Telemetria Audio Real-Time a Bassissima CPU conforme agli standard broadcast
   ITU-R BS.1770-4, EBU R128 e AES-17 (LUFS Momentary, Short-Term, Integrated
   con Dual-Gating, True Peak 4x Oversampling, RMS, Crest Factor, Correlazione
   di Fase e bilanciamento Mid/Side).
2. Vectorscope / Goniometro Stereo a 60 FPS (vectorscope.js) con tracciamento
   Lissajous al neon e griglia polare Mid/Side.
3. Scanner Completo della Sessione Ableton (camelot_pro_m4l.js) che legge BPM,
   Tracce, Gruppi, Ritorni, Catena Master, Volumi, Pan, Send e tutti i parametri
   di ogni singolo plugin attivo.
4. Generatore Automatico di Dashboard HTML & Prompt AI (camelot.py): analizza
   il file audio esportato insieme alla struttura del progetto Ableton e genera
   una Dashboard HTML interattiva + un file Contesto_AI_.txt pronto da incollare
   su ChatGPT / Claude / Gemini per una diagnosi chirurgica di Mix & Mastering.


===============================================================================
 1. INSTALLAZIONE AUTOMATICA IN 1 CLIC (CONSIGLIATA)
===============================================================================

🍎 SU macOS:
1. Fai doppio clic su "Install_Camelot_Pro.command".
   (Nota: se macOS mostra un avviso di sicurezza la prima volta, fai Clic Destro
   oppure Ctrl+Clic su "Install_Camelot_Pro.command" -> seleziona "Apri").
2. Lo script installerà automaticamente le librerie Python necessarie e copierà
   la cartella CAMELOT PRO nella tua User Library di Ableton Live.

🪟 SU WINDOWS:
1. Fai doppio clic su "Install_Camelot_Pro_Windows.bat".


===============================================================================
 2. COMANDI DA TERMINALE PER INSTALLARE PYTHON E LE LIBRERIE MANUALMENTE
===============================================================================

Se non hai ancora Python 3 installato sul computer o preferisci installare
tutto direttamente da Terminale (macOS) o Prompt dei Comandi / PowerShell (Windows),
usa queste linee di comando:

-------------------------------------------------------------------------------
 A) COME INSTALLARE PYTHON 3 DA TERMINALE (macOS)
-------------------------------------------------------------------------------
Apri l'app "Terminale" (Cmd + Spazio -> scrivi "Terminale") e incolla uno di
questi comandi:

• Metodo 1 — Tramite Installer Ufficiale Python (senza bisogno di Homebrew):
  curl -L https://www.python.org/ftp/python/3.12.8/python-3.12.8-macos11.pkg -o /tmp/python3.pkg && sudo installer -pkg /tmp/python3.pkg -target /

• Metodo 2 — Tramite Homebrew (se hai già brew installato):
  brew install python

  (Se non hai Homebrew e vuoi installarlo su macOS):
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  brew install python

• Verifica che Python 3 sia installato:
  python3 --version

-------------------------------------------------------------------------------
 B) COME INSTALLARE LE LIBRERIE DI CAMELOT PRO DA TERMINALE (macOS)
-------------------------------------------------------------------------------
Una volta installato Python 3, incolla questo comando nel Terminale per
installare le librerie matematiche DSP (numpy, scipy, soundfile, pyloudnorm):

  python3 -m pip install --upgrade pip && python3 -m pip install numpy scipy soundfile pyloudnorm

(Nota: se usi Python di Homebrew e ricevi l'avviso "externally-managed-environment",
usa invece questo comando):

  python3 -m pip install --break-system-packages numpy scipy soundfile pyloudnorm

-------------------------------------------------------------------------------
 C) COME INSTALLARE PYTHON 3 E LE LIBRERIE DA TERMINALE (WINDOWS)
-------------------------------------------------------------------------------
Apri PowerShell o il Prompt dei Comandi (cmd) e incolla:

• 1. Installa Python 3 tramite Winget (incluso in Windows 10/11):
  winget install -e --id Python.Python.3.12

• 2. Installa le librerie DSP di CAMELOT PRO:
  python -m pip install --upgrade pip
  python -m pip install numpy scipy soundfile pyloudnorm


===============================================================================
 3. DOVE POSIZIONARE LA CARTELLA IN ABLETON LIVE
===============================================================================

Copia l'intera cartella "CAMELOT PRO" dentro la tua User Library di Ableton:
  User Library -> Presets -> Audio Effects -> Max Audio Effect -> CAMELOT PRO

• Percorso predefinito macOS:
  ~/Music/Ableton/User Library/Presets/Audio Effects/Max Audio Effect/CAMELOT PRO

• Percorso predefinito Windows:
  C:\Users\<TuoNome>\Documents\Ableton\User Library\Presets\Audio Effects\Max Audio Effect\CAMELOT PRO


===============================================================================
 4. COME USARE CAMELOT PRO IN ABLETON LIVE
===============================================================================

1. Apri Ableton Live e trascina "Camelot_Pro.amxd" sulla traccia MASTER.
2. Premi Play in Ableton per visualizzare in tempo reale:
   - LUFS (Momentary, Short-Term, Integrated)
   - True Peak (dBTP 4x Oversampling ITU-R BS.1770-4)
   - RMS, Crest Factor, Correlazione di Fase e Vectorscope Stereo a 60 FPS.
3. Per generare il Report completo del Mix + Contesto AI:
   - Avvia la scansione dal device ed esporta il file WAV della tua sessione
     dentro la sottocartella "MIX ANALYSIS".
   - Al termine dell'esportazione, CAMELOT PRO aprirà automaticamente nel tuo
     browser il report "Report_<Brano>.html" e genererà il file
     "Contesto_AI_<Brano>.txt" pronto da incollare su ChatGPT o Claude!
===============================================================================

