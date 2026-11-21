<p align="center">
  <img src="Camelot_Pro_Icon.png" alt="CAMELOT PRO Logo" width="160" height="160" />
</p>

<h1 align="center">CAMELOT PRO</h1>

<p align="center">
  <strong>Real-Time Audio Telemetry, 60 FPS Vectorscope &amp; AI Session Analyzer for Ableton Live (Max for Live + Python DSP)</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Ableton%20Live-Max%20for%20Live-00d4ff?style=flat-square" alt="Ableton Live Max for Live" />
  <img src="https://img.shields.io/badge/DSP-ITU--R%20BS.1770--4%20%7C%20EBU%20R128-818cf8?style=flat-square" alt="ITU-R BS.1770-4" />
  <img src="https://img.shields.io/badge/Python-3.11%2B-34d399?style=flat-square" alt="Python 3.11+" />
  <img src="https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-c084fc?style=flat-square" alt="macOS & Windows" />
  <img src="https://img.shields.io/badge/License-MIT-f43f5e?style=flat-square" alt="MIT License" />
</p>

---

## Panoramica

**CAMELOT PRO** è una suite di analisi audio e telemetria per **Ableton Live** (Max for Live + Node for Max + Python DSP) progettata per il Mix & Mastering moderno:

1. **Telemetria Audio Real-Time (Ultra-Low CPU)**
   - Conformità **ITU-R BS.1770-4**, **EBU R128** e **AES-17** con adattamento dinamico a qualsiasi sample rate (`44.1` / `48` / `88.2` / `96+ kHz` tramite `dspstate~`).
   - **LUFS** Momentary, Short-Term e Integrated con dual-gating (`-70 LUFS` assoluto, `-10 LU` relativo).
   - **True Peak 4x Oversampling** (`gen~` polyphase FIR) + **RMS Dual-Gated**, **Crest Factor**, **Correlazione di Fase L/R** e **Mid/Side**.
2. **Vectorscope / Goniometro Stereo a 60 FPS (`vectorscope.js`)**
   - Tracciamento Lissajous neon-cyan su griglia polare Mid/Side (`M`, `+S`, `-S`, `L`, `R`).
3. **Ableton Live LOM Session Scanner (`camelot_pro_m4l.js`)**
   - Estrae BPM, Time Signature, gerarchia completa di **Master, Gruppi, Sotto-Gruppi, Tracce e Ritorni**, Volumi, Pan, Sends, stato di bypass, parametri dei plugin e flag di automazione (`⚡`).
4. **Dashboard HTML Interattiva & Contesto AI (`camelot.py`)**
   - Analizza qualsiasi formato audio (`WAV`, `AIFF`, `FLAC`, `MP3`, `M4A`, `OGG`, `OPUS`, ecc.) e genera:
     - `Report_<Brano>.html` — dashboard glassmorphism con Mix/Master Advisor, spettro 5 bande e albero ricercabile della sessione.
     - `Contesto_AI_<Brano>.txt` — riepilogo compatto pronto da incollare su ChatGPT / Claude / Gemini per diagnosi chirurgiche di mix & mastering.

---

## Installazione Rapida (1-Clic)

### macOS
1. Scarica o clona il repository.
2. Fai doppio clic su **`Install_Camelot_Pro.command`** *(la prima volta: Clic Destro → Apri)*.
3. Lo script installa le librerie DSP Python, applica le icone di CAMELOT PRO e copia il device nella tua User Library di Ableton Live.

### Windows
1. Scarica o clona il repository.
2. Fai doppio clic su **`Install_Camelot_Pro_Windows.bat`**.
3. Lo script rileva Python 3, installa e verifica le librerie DSP (`numpy`, `scipy`, `soundfile`, `pyloudnorm>=0.2.0`), configura l'icona della cartella e installa il device nella User Library di Ableton Live.

### Installazione Manuale Dipendenze Python
```bash
pip install -r requirements.txt
```

---

## Utilizzo in Ableton Live

1. Trascina **`Camelot_Pro.amxd`** sulla traccia **Master** di Ableton Live.
2. Premi **Play** per monitorare in tempo reale LUFS, True Peak, RMS, Crest Factor, Fase e Vectorscope.
3. Avvia la scansione dal device ed esporta il file audio della sessione dentro la sottocartella **`MIX ANALYSIS`**: al termine del render, CAMELOT PRO genera e apre automaticamente la Dashboard HTML e il file `Contesto_AI_<Brano>.txt`.

### Utilizzo da CLI (Standalone)
```bash
python3 camelot.py --audio "percorso/al/brano.wav" --json "camelot_session.json" --out-dir "./MIX ANALYSIS"
```

---

## Struttura del Repository

| File | Descrizione |
| --- | --- |
| `Camelot_Pro.amxd` | Device Max for Live (DSP `gen~` 4x True Peak, K-weighting adattivo, UI & Vectorscope) |
| `camelot.py` | Motore DSP offline (ITU-R BS.1770-4, EBU R128, STFT 5 bande), generatore HTML Report & AI Context |
| `camelot_live_lite.js` | Motore telemetria real-time M4L (LUFS/RMS dual-gated, coefficienti K-weighting dinamici) |
| `camelot_pro_m4l.js` | Scanner LOM Ableton Live (tracce, gruppi, plugin, parametri e automazioni) |
| `camelot_pro_runner.js` | Orchestratore Node for Max (file watcher render, esecuzione sicura `execFile`, apertura cross-platform) |
| `vectorscope.js` | Goniometro stereo Lissajous `jsui` a 60 FPS |
| `Install_Camelot_Pro.command` | Installer 1-clic per macOS |
| `Install_Camelot_Pro_Windows.bat` | Installer 1-clic per Windows |
| `build_release_zip.py` | Builder pulito per il pacchetto ZIP di distribuzione (`DIST/CAMELOT_PRO_v1.0_Release.zip`) |
| `Camelot_Pro_Icon.{png,icns,ico}` | Suite icone ufficiali (Web/HTML, macOS Retina `.icns`, Windows multi-res `.ico`) |

---

## Creazione Pacchetto di Rilascio

```bash
python3 build_release_zip.py
```

Genera un archivio pulito in `DIST/CAMELOT_PRO_v1.0_Release.zip` privo di metadati macOS (`._*`, `.DS_Store`) e con i permessi eseguibili preservati.

---

## Licenza

Distribuito sotto licenza **MIT**. Vedi [LICENSE](LICENSE) per i dettagli.
