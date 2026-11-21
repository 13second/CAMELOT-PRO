/*
 ===============================================================================
 CAMELOT LIVE LITE - STEREO VECTORSCOPE / GONIOMETER (JSUI)
 Real-time 60 FPS Lissajous & Polar Stereo Field Visualizer
 ===============================================================================
*/

mgraphics.init();
mgraphics.autofill = 0;
mgraphics.relative_coords = 0;

var buf = new Buffer("vscope_buf");
var currentPhase = 0.0;
var currentWidth = 0.0;
var currentEnergy = 0.0;

// Handle stereo metadata updates from engine
function set_stereo(phase, width, energy) {
    currentPhase = phase;
    currentWidth = width;
    currentEnergy = energy;
    mgraphics.redraw();
}

function paint() {
    var width = box.rect[2] - box.rect[0];
    var height = box.rect[3] - box.rect[1];
    var cx = width * 0.5;
    var cy = height * 0.5;
    var radius = Math.min(cx, cy) - 9;
    if (radius <= 2) return;

    // 1. Background
    mgraphics.set_source_rgba(0.06, 0.08, 0.12, 1.0);
    mgraphics.rectangle(0, 0, width, height);
    mgraphics.fill();

    // 2. Graticule / Radar Grid
    mgraphics.set_line_width(1.0);
    mgraphics.set_source_rgba(0.18, 0.23, 0.33, 0.7);

    // Outer circle
    mgraphics.arc(cx, cy, radius, 0, 2 * Math.PI);
    mgraphics.stroke();

    // Inner circle (-6 dB)
    mgraphics.arc(cx, cy, radius * 0.5, 0, 2 * Math.PI);
    mgraphics.stroke();

    // Vertical M axis (Mid / Center)
    mgraphics.move_to(cx, cy - radius);
    mgraphics.line_to(cx, cy + radius);
    mgraphics.stroke();

    // Horizontal S axis (Side / Width)
    mgraphics.move_to(cx - radius, cy);
    mgraphics.line_to(cx + radius, cy);
    mgraphics.stroke();

    // Diagonal L / R axes (45 deg)
    var diag = radius * 0.7071;
    mgraphics.set_source_rgba(0.22, 0.28, 0.38, 0.4);
    mgraphics.move_to(cx - diag, cy - diag);
    mgraphics.line_to(cx + diag, cy + diag);
    mgraphics.stroke();
    mgraphics.move_to(cx + diag, cy - diag);
    mgraphics.line_to(cx - diag, cy + diag);
    mgraphics.stroke();

    // Labels
    mgraphics.select_font_face("Arial");
    mgraphics.set_font_size(9);

    // M label
    mgraphics.set_source_rgba(0.7, 0.75, 0.82, 0.85);
    mgraphics.move_to(cx - 4, cy - radius + 11);
    mgraphics.text_path("M");
    mgraphics.fill();

    // +S label
    mgraphics.move_to(cx + radius - 14, cy + 3);
    mgraphics.text_path("+S");
    mgraphics.fill();

    // -S label
    mgraphics.move_to(cx - radius + 2, cy + 3);
    mgraphics.text_path("-S");
    mgraphics.fill();

    // L label (Cyan)
    mgraphics.set_source_rgba(0.22, 0.74, 0.97, 0.9);
    mgraphics.move_to(cx - diag + 4, cy - diag + 10);
    mgraphics.text_path("L");
    mgraphics.fill();

    // R label (Orange)
    mgraphics.set_source_rgba(0.98, 0.55, 0.20, 0.9);
    mgraphics.move_to(cx + diag - 10, cy - diag + 10);
    mgraphics.text_path("R");
    mgraphics.fill();

    // 3. Audio Lissajous Vector Trace
    var traceDrawn = false;

    if (buf && buf.framecount() > 0) {
        var numSamples = Math.min(256, buf.framecount());
        var left = buf.peek(1, 0, numSamples);
        var right = buf.peek(2, 0, numSamples);

        if (left && right && left.length > 0) {
            var energy = 0.0;
            for (var k = 0; k < left.length; k++) {
                energy += (left[k] * left[k]) + (right[k] * right[k]);
            }

            if (energy > 0.00005) {
                traceDrawn = true;
                mgraphics.set_line_width(1.5);
                mgraphics.set_source_rgba(0.22, 0.95, 0.85, 0.75); // Glowing neon cyan

                for (var i = 0; i < left.length; i++) {
                    var l = left[i];
                    var r = right[i];

                    // 45 degree stereo rotation:
                    // Side = (L - R) * 0.7071
                    // Mid  = (L + R) * 0.7071
                    var x_s = (l - r) * 0.7071;
                    var y_m = (l + r) * 0.7071;

                    var px = cx + (x_s * radius);
                    var py = cy - (y_m * radius);

                    if (i === 0) {
                        mgraphics.move_to(px, py);
                    } else {
                        mgraphics.line_to(px, py);
                    }
                }
                mgraphics.stroke();
            }
        }
    }

    // Fallback: If buffer is syncing or empty but audio energy is present, draw the live stereo envelope ellipse!
    if (!traceDrawn && currentEnergy > 0.0001) {
        var amp = Math.min(1.0, Math.sqrt(currentEnergy) * 1.5);
        var semiMajor = radius * amp;
        var semiMinor = radius * amp * Math.max(0.08, (1.0 - Math.abs(currentPhase)) * (currentWidth / 100.0));

        mgraphics.save();
        mgraphics.translate(cx, cy);
        // Tilt slightly towards phase correlation
        var tiltAngle = (1.0 - currentPhase) * 0.35;
        mgraphics.rotate(tiltAngle);

        mgraphics.set_line_width(1.5);
        mgraphics.set_source_rgba(0.22, 0.95, 0.85, 0.7);
        mgraphics.scale(semiMinor / radius, semiMajor / radius);
        mgraphics.arc(0, 0, radius, 0, 2 * Math.PI);
        mgraphics.stroke();
        mgraphics.restore();
    }
}

function bang() {
    mgraphics.redraw();
}
