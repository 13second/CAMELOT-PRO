/*
===============================================================================
 CAMELOT_PRO_M4L.JS - LOM Telemetry Extractor for CAMELOT PRO
 Extracts full Ableton Live session telemetry cleanly without LOM API errors.
 ===============================================================================
*/

autowatch = 1;
outlets = 2; // Outlet 0: bang to runner | Outlet 1: Status string

var session_json_path = "";

function bang() {
    scan_and_execute();
}

function scan_and_execute() {
    outlet(1, "SCANNING LOM...");
    var set_api = new LiveAPI("live_set");
    if (!set_api || set_api.id == 0) {
        post("❌ Errore Camelot Pro: Impossibile connettersi a live_set\n");
        outlet(1, "ERRORE LIVE_SET");
        return;
    }

    var exact_bpm = Math.round(parseFloat(set_api.get("tempo")) * 100) / 100;
    var sig_num = parseInt(set_api.get("signature_numerator"));
    var sig_den = parseInt(set_api.get("signature_denominator"));

    var result = {
        "Session_Info": {
            "BPM": exact_bpm,
            "Time_Signature_Num": sig_num,
            "Time_Signature_Den": sig_den
        },
        "Tracks": [],
        "Return_Tracks": [],
        "Master_Track": null
    };

    // 1. Tracks & Groups
    var num_tracks = set_api.getcount("tracks");
    for (var i = 0; i < num_tracks; i++) {
        var t_data = process_track("live_set tracks " + i, "Track", i + 1);
        if (t_data) result["Tracks"].push(t_data);
    }

    // 2. Returns
    var num_returns = set_api.getcount("return_tracks");
    for (var j = 0; j < num_returns; j++) {
        var r_data = process_track("live_set return_tracks " + j, "Return", j + 1);
        if (r_data) result["Return_Tracks"].push(r_data);
    }

    // 3. Master Track
    result["Master_Track"] = process_track("live_set master_track", "Master", 1);

    // Save to file dynamically in device folder (normalize separators for macOS/Windows)
    var raw_fp = (this.patcher && this.patcher.filepath) ? this.patcher.filepath.replace(/\\/g, "/") : "";
    var folder = raw_fp ? raw_fp.substring(0, raw_fp.lastIndexOf("/")) : ".";
    session_json_path = folder + "/camelot_session.json";
    
    var json_str = JSON.stringify(result, null, 2);
    function write_json(path_to_write) {
        try {
            var f = new File(path_to_write, "write");
            if (f.isopen) {
                f.eof = 0;
                var chunkSize = 4000;
                for (var k = 0; k < json_str.length; k += chunkSize) {
                    f.writestring(json_str.substring(k, k + chunkSize));
                }
                f.close();
                post("✅ Camelot Pro: Sessione salvata in " + path_to_write + "\n");
                return true;
            }
        } catch (e) {}
        return false;
    }

    write_json(session_json_path);
    if (folder.indexOf("CAMELOT PRO") === -1) {
        write_json(folder + "/CAMELOT PRO/camelot_session.json");
    }

    outlet(0, "session_file", session_json_path);
    outlet(0, "bang");
    outlet(1, "LOM SCAN OK ✅");
}

function safe_str_for_value(api_obj, val) {
    if (!api_obj || api_obj.id == 0) return "";
    try {
        var res = api_obj.call("str_for_value", val);
        if (res !== undefined && res !== null) {
            var s = Array.isArray(res) ? res.join(" ") : res.toString();
            s = s.replace(/^["']|["']$/g, "").trim();
            if (s && s.indexOf("bound method") === -1 && s.indexOf("object at") === -1) {
                return s;
            }
        }
    } catch (e) {}
    return "";
}

function process_track(track_path, track_type_label, index) {
    var trk = new LiveAPI(track_path);
    if (!trk || trk.id == 0) return null;

    var trk_id = parseInt(trk.id) || 0;
    var name = trk.get("name").toString();
    var is_foldable = parseInt(trk.get("is_foldable")) === 1;
    var is_grouped = parseInt(trk.get("is_grouped")) === 1;

    // Detect Parent Group (both ID and Name to support duplicate track/group names)
    var parent_group_name = null;
    var parent_group_id = null;
    try {
        var grp_id = trk.get("group_track");
        if (grp_id && grp_id.length >= 2 && grp_id[1] != 0) {
            parent_group_id = parseInt(grp_id[1]) || null;
            var grp_api = new LiveAPI(grp_id);
            if (grp_api && grp_api.id != 0) {
                parent_group_name = grp_api.get("name").toString();
            }
        }
    } catch (e) {}

    // Volume & Pan via child LiveAPI objects
    var vol_api = new LiveAPI(track_path + " mixer_device volume");
    var vol_val = (vol_api && vol_api.id != 0) ? parseFloat(vol_api.get("value")) : 0.85;
    var vol_str = safe_str_for_value(vol_api, vol_val);
    var vol_db = round_val(ableton_fader_to_db(vol_val));

    var pan_api = new LiveAPI(track_path + " mixer_device panning");
    var pan_val = (pan_api && pan_api.id != 0) ? round_val(parseFloat(pan_api.get("value"))) : 0.0;
    var pan_str = safe_str_for_value(pan_api, pan_val);

    // Sends via mixer_device
    var sends_list = [];
    var mixer_api = new LiveAPI(track_path + " mixer_device");
    if (mixer_api && mixer_api.id != 0) {
        var sends_count = mixer_api.getcount("sends");
        for (var s = 0; s < sends_count; s++) {
            var snd_api = new LiveAPI(track_path + " mixer_device sends " + s);
            if (snd_api && snd_api.id != 0) {
                var s_val = parseFloat(snd_api.get("value"));
                var s_str = safe_str_for_value(snd_api, s_val);
                sends_list.push({
                    "send_index": s + 1,
                    "value": round_val(s_val),
                    "db": round_val(send_knob_to_db(s_val)),
                    "display": s_str
                });
            }
        }
    }

    // Devices & Parameters
    var devices_list = [];
    var num_devices = trk.getcount("devices");
    for (var d = 0; d < num_devices; d++) {
        var dev_path = track_path + " devices " + d;
        var dev = new LiveAPI(dev_path);
        if (!dev || dev.id == 0) continue;

        var dev_name = dev.get("name").toString();
        var dev_class = dev.get("class_name").toString();
        var is_active = parseInt(dev.get("is_active")) === 1;

        var params_list = [];
        var automated_params = [];
        var num_params = dev.getcount("parameters");
        var MAX_PARAMS_PER_DEVICE = 96;
        var param_limit = Math.min(num_params, MAX_PARAMS_PER_DEVICE);
        for (var p = 0; p < param_limit; p++) {
            var p_path = dev_path + " parameters " + p;
            var param = new LiveAPI(p_path);
            if (!param || param.id == 0) continue;

            var p_name = param.get("name").toString();
            var p_val = parseFloat(param.get("value"));
            var p_str = safe_str_for_value(param, p_val);
            var p_min = parseFloat(param.get("min"));
            var p_max = parseFloat(param.get("max"));
            var p_auto_state = 0;
            try {
                p_auto_state = parseInt(param.get("automation_state")) || 0;
            } catch (e) {}
            var is_automated = p_auto_state > 0;

            if (p_name === "Device On" && p_val === 0) {
                is_active = false;
            }
            if (is_automated) {
                automated_params.push(p_name);
            }

            params_list.push({
                "name": p_name,
                "value": round_val(p_val),
                "display": p_str || round_val(p_val).toString(),
                "min": round_val(p_min),
                "max": round_val(p_max),
                "is_automated": is_automated
            });
        }

        var dev_obj = {
            "name": dev_name,
            "class": dev_class,
            "active": is_active,
            "is_active": is_active,
            "automated_params": automated_params,
            "parameters": params_list
        };
        if (num_params > MAX_PARAMS_PER_DEVICE) {
            dev_obj["parameters_truncated"] = num_params - MAX_PARAMS_PER_DEVICE;
        }
        devices_list.push(dev_obj);
    }

    return {
        "index": index,
        "track_id": trk_id,
        "type": track_type_label,
        "name": name,
        "is_group": is_foldable,
        "is_grouped": is_grouped,
        "parent_group": parent_group_name,
        "parent_group_id": parent_group_id,
        "volume_gain": vol_val,
        "volume_db": vol_db,
        "volume_str": vol_str,
        "panning": pan_val,
        "pan": pan_val,
        "panning_str": pan_str,
        "sends": sends_list,
        "devices": devices_list
    };
}

// Ableton Live fader curve: 0.85 = 0.0 dB (Unity), 1.0 = +6.0 dB
function ableton_fader_to_db(v) {
    if (v <= 0.0001) return -70.0;
    if (v >= 0.85) return ((v - 0.85) / 0.15) * 6.0;
    if (v >= 0.40) return (v - 0.85) * 40.0;
    if (v >= 0.15) return -18.0 - ((0.40 - v) / 0.25) * 24.0;
    return -42.0 - ((0.15 - v) / 0.15) * 28.0;
}

// Ableton Live send knob curve: 1.0 = 0.0 dB, 0.0 = -70.0 dB
function send_knob_to_db(v) {
    if (v <= 0.0001) return -70.0;
    return 20.0 * (Math.log(v) / Math.LN10);
}

function round_val(v) {
    return Math.round(v * 100) / 100;
}
