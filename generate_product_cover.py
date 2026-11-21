#!/usr/bin/env python3
"""
===============================================================================
 CAMELOT PRO — OFFICIAL PRODUCT COVER GENERATOR (.PNG)
 Generates high-resolution 16:9 (1920x1080) and 1:1 (1600x1600) product covers
 featuring the real Max for Live UI, ambient neon lighting, DSP code preview,
 and AI Report cards.
===============================================================================
"""

import math
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageFont

PROJECT_DIR = Path("/Volumes/Crucial X9/ABLETON/User Library/Presets/Audio Effects/Max Audio Effect/CAMELOT PRO")
UPLOADED_UI_PATH = Path("/Users/simonegaudimonte/.gemini/antigravity/brain/97948956-eeba-428b-995f-78ed16df766e/.user_uploaded/media_1793384992618_26944379.png")
ARTIFACT_DIR = Path("/Users/simonegaudimonte/.gemini/antigravity/brain/97948956-eeba-428b-995f-78ed16df766e")


def load_font(size, bold=False, mono=False):
    if mono:
        candidates = [
            "/System/Library/Fonts/Menlo.ttc",
            "/System/Library/Fonts/Monaco.ttf",
            "/System/Library/Fonts/Courier.dfont",
        ]
    elif bold:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    else:
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/HelveticaNeue.ttc",
            "/System/Library/Fonts/Helvetica.ttc",
        ]
    for path in candidates:
        if Path(path).exists():
            try:
                idx = 1 if (bold and path.endswith("HelveticaNeue.ttc")) else 0
                return ImageFont.truetype(path, size, index=idx)
            except Exception:
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    pass
    return ImageFont.load_default()


def create_background(width, height):
    """Creates a dark studio background with subtle DSP grid and glowing ambient orbs."""
    # Base dark gradient (#05070B -> #0B101B)
    y_grad = np.linspace(0, 1, height)[:, None]
    x_grad = np.linspace(-1, 1, width)[None, :]
    radial = np.sqrt(x_grad**2 + (y_grad - 0.45) ** 2)

    r = np.clip(14 - radial * 8, 5, 18).astype(np.uint8)
    g = np.clip(20 - radial * 10, 7, 25).astype(np.uint8)
    b = np.clip(32 - radial * 14, 12, 40).astype(np.uint8)
    rgb = np.stack([r, g, b], axis=-1)
    bg = Image.fromarray(rgb, mode="RGB").convert("RGBA")

    # Ambient glowing colour orbs matching plugin colors: Cyan, Mid-Green, Side-Gold
    glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    g_draw = ImageDraw.Draw(glow_layer)

    # Top-left Cyan glow (#00B8FF)
    g_draw.ellipse(
        [int(width * 0.05), int(height * 0.08), int(width * 0.48), int(height * 0.62)],
        fill=(0, 185, 255, 42),
    )
    # Center-right Green/Gold glow (#58D62A / #F5B41A)
    g_draw.ellipse(
        [int(width * 0.35), int(height * 0.22), int(width * 0.78), int(height * 0.75)],
        fill=(85, 215, 45, 34),
    )
    g_draw.ellipse(
        [int(width * 0.52), int(height * 0.30), int(width * 0.92), int(height * 0.82)],
        fill=(245, 180, 30, 30),
    )
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=110))
    bg = Image.alpha_composite(bg, glow_layer)

    # Subtle technical perspective/frequency grid
    grid_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    grid_draw = ImageDraw.Draw(grid_layer)
    step = 60
    for x in range(0, width, step):
        alpha = 11 if (x % (step * 4) == 0) else 5
        grid_draw.line([(x, 0), (x, height)], fill=(120, 175, 255, alpha), width=1)
    for y in range(0, height, step):
        alpha = 11 if (y % (step * 4) == 0) else 5
        grid_draw.line([(0, y), (width, y)], fill=(120, 175, 255, alpha), width=1)

    bg = Image.alpha_composite(bg, grid_layer)
    return bg


def enhance_plugin_screenshot(ui_img):
    """
    Adds a subtle, realistic glowing Lissajous stereo trace inside the Vectorscope radar
    so the cover looks alive and dynamic while preserving 100% of the authentic UI.
    """
    ui = ui_img.convert("RGBA").copy()
    w, h = ui.size

    # In the 1024x217 screenshot, the Vectorscope box is centered around x=232, y=111, radius ~48
    cx, cy = 232, 111
    trace_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    t_draw = ImageDraw.Draw(trace_layer)

    # Generate a realistic stereo Lissajous cloud (Mid-focused with rich stereo width)
    np.random.seed(42)
    points = []
    num_pts = 110
    for i in range(num_pts):
        t = i * 0.19
        # Vertical (Mid) dominant, Horizontal (Side) moderate
        mid = math.sin(t * 1.7) * 28.0 + math.cos(t * 3.1) * 10.0
        side = math.cos(t * 2.3 + 0.6) * 14.0 + math.sin(t * 4.7) * 5.0
        px = cx + side
        py = cy + mid
        points.append((px, py))

    # Outer cyan glow
    t_draw.line(points, fill=(0, 240, 225, 95), width=3, joint="curve")
    trace_glow = trace_layer.filter(ImageFilter.GaussianBlur(radius=2.2))

    # Crisp core trace
    core_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    c_draw = ImageDraw.Draw(core_layer)
    c_draw.line(points, fill=(80, 255, 240, 195), width=1)

    ui = Image.alpha_composite(ui, trace_glow)
    ui = Image.alpha_composite(ui, core_layer)
    return ui


def draw_rounded_card(canvas, box, fill, outline, radius=18, width=2, shadow_alpha=120):
    x1, y1, x2, y2 = box
    w, h = canvas.size

    # Drop shadow
    sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sh_draw = ImageDraw.Draw(sh)
    sh_draw.rounded_rectangle(
        [x1 + 4, y1 + 12, x2 + 4, y2 + 16],
        radius=radius,
        fill=(0, 0, 0, shadow_alpha),
    )
    sh = sh.filter(ImageFilter.GaussianBlur(radius=18))
    canvas.alpha_composite(sh)

    # Card body
    card = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    c_draw = ImageDraw.Draw(card)
    c_draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    canvas.alpha_composite(card)


def draw_dsp_code_card(canvas, x1, y1, x2, y2):
    """Draws the lower-left floating card showcasing the Python ITU-R BS.1770-4 & LOM engine."""
    draw_rounded_card(
        canvas,
        (x1, y1, x2, y2),
        fill=(11, 16, 26, 230),
        outline=(0, 195, 255, 95),
        radius=16,
        width=2,
    )
    draw = ImageDraw.Draw(canvas)

    # Window header bar
    draw.rounded_rectangle(
        [x1, y1, x2, y1 + 38],
        radius=16,
        fill=(18, 26, 42, 255),
    )
    draw.rectangle([x1, y1 + 22, x2, y1 + 38], fill=(18, 26, 42, 255))

    # macOS traffic light dots
    for idx, col in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = x1 + 22 + idx * 18
        cy = y1 + 19
        draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], fill=col)

    f_tab = load_font(13, bold=True, mono=True)
    draw.text((x1 + 85, y1 + 11), "camelot.py  •  ITU-R BS.1770-4 DSP Engine", font=f_tab, fill=(150, 185, 225))

    f_code = load_font(14, mono=True)
    code_lines = [
        ("def ", (255, 121, 198), "calculate_true_peak_itu", (80, 250, 123), "(signal_ch):"),
        ("    # 4x Polyphase FIR Oversampling (BS.1770-4)", (110, 135, 170), "", (0, 0, 0), ""),
        ("    y1 = np.abs(signal.lfilter(", (230, 238, 248), "ITU_TP_H1", (0, 215, 255), ", [1.0], ch))"),
        ("    y2 = np.abs(signal.lfilter(", (230, 238, 248), "ITU_TP_H2", (0, 215, 255), ", [1.0], ch))"),
        ("    lufs_i = meter.integrated_loudness(stereo)", (245, 195, 60), "", (0, 0, 0), ""),
        ("    return ", (255, 121, 198), "max(y0, y1, y2, y3), lufs_i", (80, 250, 123), ""),
    ]

    cy = y1 + 52
    for p1, c1, p2, c2, p3 in code_lines:
        cx = x1 + 20
        draw.text((cx, cy), p1, font=f_code, fill=c1)
        w1 = draw.textlength(p1, font=f_code)
        if p2:
            draw.text((cx + w1, cy), p2, font=f_code, fill=c2)
            w2 = draw.textlength(p2, font=f_code)
            if p3:
                draw.text((cx + w1 + w2, cy), p3, font=f_code, fill=(230, 238, 248))
        cy += 24


def draw_ai_report_card(canvas, x1, y1, x2, y2):
    """Draws the lower-right floating card showcasing the HTML Dashboard & AI Session Prompt."""
    draw_rounded_card(
        canvas,
        (x1, y1, x2, y2),
        fill=(11, 16, 26, 230),
        outline=(88, 214, 42, 105),
        radius=16,
        width=2,
    )
    draw = ImageDraw.Draw(canvas)

    # Header bar
    draw.rounded_rectangle([x1, y1, x2, y1 + 38], radius=16, fill=(18, 28, 36, 255))
    draw.rectangle([x1, y1 + 22, x2, y1 + 38], fill=(18, 28, 36, 255))

    f_tab = load_font(13, bold=True)
    draw.ellipse([x1 + 18, y1 + 13, x1 + 30, y1 + 25], fill=(80, 240, 90))
    draw.text(
        (x1 + 40, y1 + 11),
        "HTML MIX REPORT  +  CONTESTO AI (LOM SCANNER)",
        font=f_tab,
        fill=(170, 235, 180),
    )

    f_label = load_font(14, bold=True)
    f_val = load_font(14, mono=True)

    rows = [
        ("LUFS INTEGRATED", "-8.4 LUFS  (Club / Streaming Ready)", (80, 240, 110)),
        ("TRUE PEAK (4x ITU)", "-0.8 dBTP  (Zero Inter-Sample Clip)", (0, 215, 255)),
        ("MULTIBAND BALANCE", "Sub 22% | Low 28% | Mid 29% | High 21%", (245, 185, 45)),
        ("ABLETON LOM SCAN", "Tracks, Groups, Sends & Every Plugin Param", (215, 225, 240)),
        ("AI PROMPT EXPORT", "Contesto_AI.txt -> ChatGPT / Claude / Gemini", (180, 145, 255)),
    ]

    cy = y1 + 50
    for label, val, col in rows:
        draw.rounded_rectangle([x1 + 18, cy, x1 + 190, cy + 24], radius=6, fill=(24, 34, 50, 220))
        draw.text((x1 + 26, cy + 4), label, font=f_label, fill=(160, 185, 215))
        draw.text((x1 + 204, cy + 4), val, font=f_val, fill=col)
        cy += 29


def generate_16x9_cover(ui_enhanced):
    W, H = 1920, 1080
    canvas = create_background(W, H)
    draw = ImageDraw.Draw(canvas)

    # 1. Top Pill Badge
    pill_w, pill_h = 690, 40
    px1 = (W - pill_w) // 2
    py1 = 42
    draw.rounded_rectangle(
        [px1, py1, px1 + pill_w, py1 + pill_h],
        radius=20,
        fill=(12, 25, 44, 220),
        outline=(0, 200, 255, 140),
        width=2,
    )
    f_pill = load_font(15, bold=True)
    pill_text = "ABLETON LIVE (MAX FOR LIVE)   •   PYTHON DSP ENGINE   •   AI MIX ANALYZER"
    tw = draw.textlength(pill_text, font=f_pill)
    draw.text(((W - tw) / 2, py1 + 11), pill_text, font=f_pill, fill=(0, 220, 255))

    # 2. Main Title: CAMELOT PRO
    f_title = load_font(86, bold=True)
    t_part1 = "CAMELOT "
    t_part2 = "PRO"
    w1 = draw.textlength(t_part1, font=f_title)
    w2 = draw.textlength(t_part2, font=f_title)
    total_tw = w1 + w2
    tx = (W - total_tw) / 2
    ty = 98

    # Title glow
    glow_txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gt_draw = ImageDraw.Draw(glow_txt)
    gt_draw.text((tx, ty), t_part1, font=f_title, fill=(0, 200, 255, 95))
    gt_draw.text((tx + w1, ty), t_part2, font=f_title, fill=(90, 255, 70, 95))
    glow_txt = glow_txt.filter(ImageFilter.GaussianBlur(radius=18))
    canvas.alpha_composite(glow_txt)

    draw = ImageDraw.Draw(canvas)
    draw.text((tx, ty), t_part1, font=f_title, fill=(245, 250, 255))
    draw.text((tx + w1, ty), t_part2, font=f_title, fill=(0, 210, 255))

    # 3. Subtitle
    f_sub = load_font(25, bold=True)
    sub_text = "Real-Time ITU-R Telemetry  •  60 FPS Vectorscope  •  Mid/Side Spectrum  •  1-Click AI Session Report"
    stw = draw.textlength(sub_text, font=f_sub)
    draw.text(((W - stw) / 2, 198), sub_text, font=f_sub, fill=(180, 200, 225))

    # 4. Hero Plugin UI Screenshot (Scaled to 1680px wide)
    target_w = 1680
    scale = target_w / ui_enhanced.width
    target_h = int(ui_enhanced.height * scale)
    ui_resized = ui_enhanced.resize((target_w, target_h), Image.Resampling.LANCZOS)

    ux = (W - target_w) // 2
    uy = 258

    # Multi-layered neon glow + deep shadow behind the Max for Live device
    shadow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    s_draw.rounded_rectangle(
        [ux - 10, uy - 6, ux + target_w + 10, uy + target_h + 18],
        radius=20,
        fill=(0, 190, 255, 70),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=30))
    canvas.alpha_composite(shadow_layer)

    deep_shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds_draw = ImageDraw.Draw(deep_shadow)
    ds_draw.rounded_rectangle(
        [ux, uy + 18, ux + target_w, uy + target_h + 36],
        radius=18,
        fill=(0, 0, 0, 200),
    )
    deep_shadow = deep_shadow.filter(ImageFilter.GaussianBlur(radius=25))
    canvas.alpha_composite(deep_shadow)

    # Sleek metallic frame around the device
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [ux - 6, uy - 6, ux + target_w + 6, uy + target_h + 6],
        radius=14,
        fill=(22, 26, 32, 255),
        outline=(0, 205, 255, 180),
        width=2,
    )
    canvas.alpha_composite(ui_resized, (ux, uy))

    # 5. Two Bottom Cards (DSP Code + AI Session Report)
    cards_y1 = uy + target_h + 36
    cards_y2 = cards_y1 + 208
    gap = 32
    card_w = (target_w - gap) // 2

    draw_dsp_code_card(canvas, ux, cards_y1, ux + card_w, cards_y2)
    draw_ai_report_card(canvas, ux + card_w + gap, cards_y1, ux + target_w, cards_y2)

    # 6. Bottom Feature Badges Bar
    badges = [
        ("LUFS & TRUE PEAK", "ITU-R BS.1770-4 / EBU R128", (0, 210, 255)),
        ("STEREO GONIOMETER", "60 FPS Lissajous + Phase", (80, 240, 110)),
        ("M/S SPECTRUM", "20 Hz – 20 kHz Real-Time", (245, 185, 40)),
        ("AI SESSION BRIDGE", "Full Ableton LOM + HTML Report", (190, 140, 255)),
    ]
    bw = (target_w - 3 * 24) // 4
    by1 = cards_y2 + 28
    by2 = by1 + 66
    f_btitle = load_font(15, bold=True)
    f_bsub = load_font(14)

    draw = ImageDraw.Draw(canvas)
    for i, (b_title, b_sub, b_col) in enumerate(badges):
        bx1 = ux + i * (bw + 24)
        bx2 = bx1 + bw
        draw.rounded_rectangle(
            [bx1, by1, bx2, by2],
            radius=12,
            fill=(14, 20, 32, 220),
            outline=(b_col[0], b_col[1], b_col[2], 110),
            width=1,
        )
        # Left accent bar
        draw.rounded_rectangle([bx1 + 10, by1 + 12, bx1 + 16, by2 - 12], radius=3, fill=b_col)
        draw.text((bx1 + 28, by1 + 12), b_title, font=f_btitle, fill=b_col)
        draw.text((bx1 + 28, by1 + 35), b_sub, font=f_bsub, fill=(200, 215, 235))

    return canvas.convert("RGB")


def generate_square_cover(ui_enhanced):
    """Generates a 1600x1600 1:1 Square Product Cover for Gumroad thumbnails & Socials."""
    W, H = 1600, 1600
    canvas = create_background(W, H)
    draw = ImageDraw.Draw(canvas)

    # 1. Top Badge
    pill_w, pill_h = 680, 44
    px1 = (W - pill_w) // 2
    py1 = 68
    draw.rounded_rectangle(
        [px1, py1, px1 + pill_w, py1 + pill_h],
        radius=22,
        fill=(12, 25, 44, 220),
        outline=(0, 200, 255, 150),
        width=2,
    )
    f_pill = load_font(16, bold=True)
    pill_text = "MAX FOR LIVE DEVICE   •   PYTHON DSP   •   AI MIX ENGINE"
    tw = draw.textlength(pill_text, font=f_pill)
    draw.text(((W - tw) / 2, py1 + 12), pill_text, font=f_pill, fill=(0, 220, 255))

    # 2. Title
    f_title = load_font(104, bold=True)
    t_part1 = "CAMELOT "
    t_part2 = "PRO"
    w1 = draw.textlength(t_part1, font=f_title)
    w2 = draw.textlength(t_part2, font=f_title)
    tx = (W - (w1 + w2)) / 2
    ty = 140

    glow_txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gt_draw = ImageDraw.Draw(glow_txt)
    gt_draw.text((tx, ty), t_part1, font=f_title, fill=(0, 200, 255, 95))
    gt_draw.text((tx + w1, ty), t_part2, font=f_title, fill=(90, 255, 70, 95))
    glow_txt = glow_txt.filter(ImageFilter.GaussianBlur(radius=20))
    canvas.alpha_composite(glow_txt)

    draw = ImageDraw.Draw(canvas)
    draw.text((tx, ty), t_part1, font=f_title, fill=(245, 250, 255))
    draw.text((tx + w1, ty), t_part2, font=f_title, fill=(0, 210, 255))

    f_sub = load_font(27, bold=True)
    sub_text = "TELEMETRIA AUDIO, VECTORSCOPE 60 FPS & REPORT AI PER ABLETON LIVE"
    stw = draw.textlength(sub_text, font=f_sub)
    draw.text(((W - stw) / 2, 268), sub_text, font=f_sub, fill=(185, 205, 230))

    # 3. Main Device UI (Full width 1460px)
    target_w = 1460
    scale = target_w / ui_enhanced.width
    target_h = int(ui_enhanced.height * scale)
    ui_resized = ui_enhanced.resize((target_w, target_h), Image.Resampling.LANCZOS)

    ux = (W - target_w) // 2
    uy = 350

    shadow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    s_draw = ImageDraw.Draw(shadow_layer)
    s_draw.rounded_rectangle(
        [ux - 12, uy - 8, ux + target_w + 12, uy + target_h + 20],
        radius=22,
        fill=(0, 195, 255, 80),
    )
    shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=35))
    canvas.alpha_composite(shadow_layer)

    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [ux - 6, uy - 6, ux + target_w + 6, uy + target_h + 6],
        radius=14,
        fill=(22, 26, 32, 255),
        outline=(0, 205, 255, 190),
        width=2,
    )
    canvas.alpha_composite(ui_resized, (ux, uy))

    # 4. Stacked Cards below UI
    c1_y1 = uy + target_h + 50
    c1_y2 = c1_y1 + 215
    draw_dsp_code_card(canvas, ux, c1_y1, ux + 710, c1_y2)
    draw_ai_report_card(canvas, ux + 750, c1_y1, ux + target_w, c1_y2)

    # 5. 2x2 Big Feature Grid at the Bottom
    features = [
        ("ITU-R BS.1770-4 & EBU R128", "LUFS Integrated, RMS, Crest Factor & 4x Oversampled True Peak", (0, 215, 255)),
        ("STEREO VECTORSCOPE 60 FPS", "Real-Time Lissajous Radar + Correlazione di Fase (-1 / +1)", (80, 240, 110)),
        ("SPETTRO MID / SIDE (20Hz-20kHz)", "Analisi separata Mid (Verde) e Side (Oro) in tempo reale", (245, 185, 40)),
        ("OFFLINE HTML & AI MIX REPORT", "Scansione completa plugin Ableton + Contesto AI per ChatGPT/Claude", (195, 145, 255)),
    ]

    grid_y1 = c1_y2 + 44
    box_w = (target_w - 30) // 2
    box_h = 115
    f_ft = load_font(21, bold=True)
    f_fs = load_font(17)

    draw = ImageDraw.Draw(canvas)
    for idx, (ft, fs_txt, col) in enumerate(features):
        row = idx // 2
        col_idx = idx % 2
        bx1 = ux + col_idx * (box_w + 30)
        by1 = grid_y1 + row * (box_h + 24)
        bx2 = bx1 + box_w
        by2 = by1 + box_h

        draw.rounded_rectangle(
            [bx1, by1, bx2, by2],
            radius=16,
            fill=(14, 21, 34, 230),
            outline=(col[0], col[1], col[2], 125),
            width=2,
        )
        draw.rounded_rectangle([bx1 + 16, by1 + 20, bx1 + 24, by2 - 20], radius=4, fill=col)
        draw.text((bx1 + 40, by1 + 22), ft, font=f_ft, fill=col)
        draw.text((bx1 + 40, by1 + 60), fs_txt, font=f_fs, fill=(210, 222, 240))

    return canvas.convert("RGB")


def main():
    ui_raw = Image.open(UPLOADED_UI_PATH)
    ui_enhanced = enhance_plugin_screenshot(ui_raw)

    cover_16x9 = generate_16x9_cover(ui_enhanced)
    cover_square = generate_square_cover(ui_enhanced)

    out_16x9 = PROJECT_DIR / "Camelot_Pro_Cover.png"
    out_square = PROJECT_DIR / "Camelot_Pro_Cover_Square.png"

    cover_16x9.save(out_16x9, format="PNG", optimize=True)
    cover_square.save(out_square, format="PNG", optimize=True)

    # Also save copies to artifact dir so we can preview/embed if needed
    cover_16x9.save(ARTIFACT_DIR / "Camelot_Pro_Cover.png", format="PNG")
    cover_square.save(ARTIFACT_DIR / "Camelot_Pro_Cover_Square.png", format="PNG")

    print(f"✅ Creato: {out_16x9} ({out_16x9.stat().st_size / 1024:.1f} KB)")
    print(f"✅ Creato: {out_square} ({out_square.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
