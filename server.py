"""
Song Chest — local server
Run: ./start.sh  or  python server.py
Open: http://localhost:5000
"""

import json, os, shutil, uuid, time, re
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, abort

app = Flask(__name__, static_folder=".")

BASE_DIR    = Path(__file__).parent
DATA_FILE   = BASE_DIR / "data.json"
CONFIG_FILE = BASE_DIR / "config.json"

AUDIO_EXT  = {".m4a", ".mp3", ".wav", ".aiff", ".ogg", ".flac"}
LYRICS_EXT = {".txt", ".md", ".rtf"}

# ── config ────────────────────────────────────────────────────

def load_config():
    defaults = {
        "audio_folder":  str(BASE_DIR / "audio"),
        "lyrics_folder": str(BASE_DIR / "lyrics"),
    }
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k in defaults:
            cfg[k] = str(Path(cfg.get(k, defaults[k])).expanduser().resolve())
        return cfg
    save_config(defaults)
    return defaults

def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)

CONFIG = load_config()
def audio_dir():  return Path(CONFIG["audio_folder"])
def lyrics_dir(): return Path(CONFIG["lyrics_folder"])

# ── data ──────────────────────────────────────────────────────

def load_data():
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
        except (json.JSONDecodeError, IOError):
            print("  ⚠️  data.json unreadable — starting fresh")
            return {"projects": [], "ideas": [], "move_history": []}
        d.setdefault("projects", [])
        d.setdefault("ideas", [])
        d.setdefault("move_history", [])
        return d
    return {"projects": [], "ideas": [], "move_history": []}

def save_data(data):
    tmp = DATA_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(DATA_FILE)

def new_id():  return str(uuid.uuid4())[:8]
def now_ms():  return int(time.time() * 1000)

# ── filesystem helpers ────────────────────────────────────────

def scan_files():
    result = {"audio": [], "lyrics": []}
    for kind, root, exts in [("audio", audio_dir(), AUDIO_EXT),
                              ("lyrics", lyrics_dir(), LYRICS_EXT)]:
        if root.exists():
            for p in sorted(root.rglob("*")):
                if p.suffix.lower() in exts:
                    rel   = str(p.relative_to(root))
                    parts = Path(rel).parts
                    result[kind].append({
                        "path":   rel,
                        "name":   p.name,
                        "folder": parts[0] if len(parts) > 1 else "",
                        "size":   p.stat().st_size,
                        "mtime":  int(p.stat().st_mtime * 1000)
                    })
    return result

def safe_path(root, rel):
    # Normalize without resolving symlinks to avoid macOS /private/var issues
    full = Path(os.path.normpath(root / rel))
    root_norm = str(os.path.normpath(root)) + os.sep
    if not str(full).startswith(root_norm):
        raise ValueError("Path traversal")
    return full

def folder_name_for(name):
    s = re.sub(r"[^\w\s-]", "", name.strip().lower())
    s = re.sub(r"[\s_]+", "-", s)
    return s.strip("-") or "untitled"

def title_from_filename(filename):
    stem = Path(filename).stem
    stem = re.sub(r"[-_]", " ", stem)
    return stem.strip().capitalize()

# ── sync: auto-import new files ───────────────────────────────

def sync_files(data):
    """
    Compare files on disk with ideas in data.json.
    Create a bare idea for every file that has no existing idea pointing at it.
    Returns list of newly created ideas.
    """
    scanned = scan_files()
    existing_audio  = {i["audiofile"] for i in data["ideas"] if i.get("audiofile")}
    existing_lyrics = {i["lyricfile"]  for i in data["ideas"] if i.get("lyricfile")}

    new_ideas = []

    for f in scanned["audio"]:
        if f["path"] not in existing_audio:
            # find matching project by folder name
            proj = next((p for p in data["projects"] if p.get("folder") == f["folder"]), None)
            idea = {
                "id": new_id(), "type": "audio",
                "title": title_from_filename(f["name"]),
                "content": "", "audiofile": f["path"], "lyricfile": "",
                "project": proj["id"] if proj else None,
                "tags": [], "links": [], "notes": "",
                "created": f["mtime"], "updated": now_ms(),
                "auto_imported": True
            }
            new_ideas.append(idea)

    for f in scanned["lyrics"]:
        if f["path"] not in existing_lyrics:
            proj = next((p for p in data["projects"] if p.get("folder") == f["folder"]), None)
            idea = {
                "id": new_id(), "type": "lyric",
                "title": title_from_filename(f["name"]),
                "content": "", "audiofile": "", "lyricfile": f["path"],
                "project": proj["id"] if proj else None,
                "tags": [], "links": [], "notes": "",
                "created": f["mtime"], "updated": now_ms(),
                "auto_imported": True
            }
            new_ideas.append(idea)

    if new_ideas:
        data["ideas"] = new_ideas + data["ideas"]
        save_data(data)

    return new_ideas

# ── config API ────────────────────────────────────────────────

@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify({**CONFIG,
                    "audio_exists":  audio_dir().exists(),
                    "lyrics_exists": lyrics_dir().exists()})

@app.route("/api/config", methods=["POST"])
def update_config():
    global CONFIG
    body = request.json
    for k in ("audio_folder", "lyrics_folder"):
        if body.get(k):
            CONFIG[k] = str(Path(body[k]).expanduser().resolve())
    save_config(CONFIG)
    audio_dir().mkdir(parents=True, exist_ok=True)
    lyrics_dir().mkdir(parents=True, exist_ok=True)
    return jsonify({**CONFIG,
                    "audio_exists":  audio_dir().exists(),
                    "lyrics_exists": lyrics_dir().exists()})

# ── scan & sync ───────────────────────────────────────────────

@app.route("/api/scan")
def api_scan():
    return jsonify(scan_files())

@app.route("/api/sync", methods=["POST"])
def api_sync():
    data     = load_data()
    new_ones = sync_files(data)
    return jsonify({"imported": len(new_ones), "new_ideas": new_ones})

# ── data ──────────────────────────────────────────────────────

@app.route("/api/data")
def api_data():
    return jsonify(load_data())

# ── projects ──────────────────────────────────────────────────

@app.route("/api/projects", methods=["POST"])
def create_project():
    data = load_data()
    body = request.json
    if not body.get("name","").strip():
        return jsonify({"error": "name required"}), 400
    fn   = folder_name_for(body["name"])
    (audio_dir()  / fn).mkdir(parents=True, exist_ok=True)
    (lyrics_dir() / fn).mkdir(parents=True, exist_ok=True)
    p = {"id": new_id(), "name": body["name"], "type": body.get("type","EP"),
         "color": body.get("color","#DAA520"), "folder": fn, "created": now_ms()}
    data["projects"].append(p)
    save_data(data)
    return jsonify(p), 201

@app.route("/api/projects/<pid>", methods=["PUT"])
def update_project(pid):
    data = load_data()
    p = next((x for x in data["projects"] if x["id"]==pid), None)
    if not p: abort(404)
    for k in ("name","type","color"):
        if k in request.json: p[k] = request.json[k]
    save_data(data); return jsonify(p)

@app.route("/api/projects/<pid>", methods=["DELETE"])
def delete_project(pid):
    data = load_data()
    data["projects"] = [x for x in data["projects"] if x["id"]!=pid]
    for idea in data["ideas"]:
        if idea.get("project")==pid: idea["project"]=None
    save_data(data); return jsonify({"ok":True})

# ── ideas ─────────────────────────────────────────────────────

@app.route("/api/ideas", methods=["POST"])
def create_idea():
    data = load_data()
    body = request.json
    if not body.get("type") or not body.get("title","").strip():
        return jsonify({"error": "type and title required"}), 400
    idea = {"id": new_id(), "type": body["type"], "title": body["title"],
            "content": body.get("content",""), "audiofile": body.get("audiofile",""),
            "lyricfile": body.get("lyricfile",""), "project": body.get("project") or None,
            "tags": body.get("tags",[]), "links": body.get("links",[]),
            "notes": body.get("notes",""), "created": now_ms(), "updated": now_ms()}
    for lid in idea["links"]:
        other = next((x for x in data["ideas"] if x["id"]==lid), None)
        if other and idea["id"] not in other["links"]: other["links"].append(idea["id"])
    data["ideas"].insert(0, idea)
    save_data(data); return jsonify(idea), 201

@app.route("/api/ideas/<iid>", methods=["PUT"])
def update_idea(iid):
    data = load_data()
    idea = next((x for x in data["ideas"] if x["id"]==iid), None)
    if not idea: abort(404)
    old_links = set(idea.get("links",[]))
    body = request.json
    for k in ("type","title","content","audiofile","lyricfile","project","tags","links","notes"):
        if k in body: idea[k] = body[k]
    idea["updated"] = now_ms()
    idea["project"] = idea.get("project") or None
    # clear auto_imported flag once user edits
    idea.pop("auto_imported", None)
    new_links = set(idea["links"])
    for lid in new_links-old_links:
        other = next((x for x in data["ideas"] if x["id"]==lid), None)
        if other and iid not in other["links"]: other["links"].append(iid)
    for lid in old_links-new_links:
        other = next((x for x in data["ideas"] if x["id"]==lid), None)
        if other: other["links"] = [l for l in other["links"] if l!=iid]
    save_data(data); return jsonify(idea)

@app.route("/api/ideas/<iid>", methods=["DELETE"])
def delete_idea(iid):
    data = load_data()
    data["ideas"] = [x for x in data["ideas"] if x["id"]!=iid]
    for idea in data["ideas"]: idea["links"] = [l for l in idea["links"] if l!=iid]
    save_data(data); return jsonify({"ok":True})

@app.route("/api/ideas/<iid>/notes", methods=["PATCH"])
def patch_notes(iid):
    data = load_data()
    idea = next((x for x in data["ideas"] if x["id"]==iid), None)
    if not idea: abort(404)
    idea["notes"] = request.json.get("notes","")
    idea["updated"] = now_ms()
    save_data(data); return jsonify({"ok":True})

# ── move: preview ─────────────────────────────────────────────

@app.route("/api/move/preview", methods=["POST"])
def preview_move():
    data = load_data()
    body = request.json
    idea = next((x for x in data["ideas"] if x["id"]==body["idea_id"]), None)
    if not idea: abort(404)
    target_pid  = body.get("target_project_id")
    target_proj = next((p for p in data["projects"] if p["id"]==target_pid), None) if target_pid else None
    tfolder     = target_proj["folder"] if target_proj else ""
    moves = []
    for kind, field, root in [("audio","audiofile",audio_dir()),
                               ("lyrics","lyricfile",lyrics_dir())]:
        src = idea.get(field,"")
        if not src: continue
        filename = Path(src).name
        dest = str(Path(tfolder)/filename) if tfolder else filename
        if src != dest:
            dest_abs = str(root/dest)
            # warn if destination already exists (would overwrite)
            collision = Path(dest_abs).exists()
            moves.append({"kind":kind,"file":filename,
                          "from":src,"to":dest,
                          "from_abs":str(root/src),"to_abs":dest_abs,
                          "collision": collision})
    return jsonify({"moves":moves,"idea":idea,"target_project":target_proj})

# ── move: execute ─────────────────────────────────────────────

@app.route("/api/move/execute", methods=["POST"])
def execute_move():
    data = load_data()
    body = request.json
    idea = next((x for x in data["ideas"] if x["id"]==body["idea_id"]), None)
    if not idea: abort(404)
    moves, executed = body.get("moves",[]), []
    try:
        for m in moves:
            src, dest = Path(m["from_abs"]), Path(m["to_abs"])
            if not src.exists(): raise FileNotFoundError(f"Not found: {src}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            executed.append(m)
            if m["kind"]=="audio":  idea["audiofile"] = m["to"]
            else:                   idea["lyricfile"]  = m["to"]
        idea["project"] = body.get("target_project_id") or None
        idea["updated"] = now_ms()
        entry = {"id":new_id(),"ts":now_ms(),"idea_id":idea["id"],
                 "idea_title":idea["title"],
                 "from_project":body.get("from_project_id"),
                 "to_project":body.get("target_project_id"),
                 "moves":executed,"undone":False}
        data["move_history"].append(entry)
        save_data(data)
        return jsonify({"ok":True,"history_id":entry["id"],"idea":idea})
    except Exception as e:
        rollback_warnings = []
        for m in reversed(executed):
            try:
                shutil.move(m["to_abs"], m["from_abs"])
            except Exception as rb_err:
                rollback_warnings.append(f"Rollback failed for {m['file']}: {rb_err}")
        payload = {"error": str(e)}
        if rollback_warnings:
            payload["rollback_warnings"] = rollback_warnings
        return jsonify(payload), 500

# ── move: undo ────────────────────────────────────────────────

@app.route("/api/move/undo/<hid>", methods=["POST"])
def undo_move(hid):
    data  = load_data()
    entry = next((h for h in data["move_history"] if h["id"]==hid), None)
    if not entry: abort(404)
    if entry.get("undone"): return jsonify({"error":"Already undone."}), 400
    idea = next((x for x in data["ideas"] if x["id"]==entry["idea_id"]), None)
    if not idea:
        # idea was deleted — still mark history entry as undone, attempt file rollback
        warnings = []
        for m in reversed(entry["moves"]):
            src, dest = Path(m["to_abs"]), Path(m["from_abs"])
            if not src.exists(): warnings.append(f"Missing: {src}"); continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
        entry["undone"] = True
        save_data(data)
        return jsonify({"ok": True, "warnings": warnings, "note": "idea was deleted"})
    warnings = []
    for m in reversed(entry["moves"]):
        src, dest = Path(m["to_abs"]), Path(m["from_abs"])
        if not src.exists(): warnings.append(f"Missing: {src}"); continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        if m["kind"]=="audio":  idea["audiofile"] = m["from"]
        else:                   idea["lyricfile"]  = m["from"]
    idea["project"] = entry.get("from_project")
    idea["updated"] = now_ms()
    entry["undone"] = True
    save_data(data)
    return jsonify({"ok":True,"warnings":warnings,"idea":idea})

@app.route("/api/move/history")
def move_history():
    data = load_data()
    hist = sorted(data.get("move_history",[]), key=lambda h:h["ts"], reverse=True)[:50]
    return jsonify(hist)

# ── serve files ───────────────────────────────────────────────

@app.route("/audio/<path:filename>")
def serve_audio(filename):
    try:
        full = safe_path(audio_dir(), filename)
    except ValueError:
        abort(403)
    if not full.exists(): abort(404)
    # Try direct serve first; if format needs transcoding, pipe via ffmpeg
    ext = full.suffix.lower()
    if ext in ('.m4a', '.aiff', '.aif'):
        return serve_transcoded(full)
    return send_from_directory(str(audio_dir()), filename)

def serve_transcoded(full_path):
    """Transcode ALAC/unsupported audio to AAC, cache result, then serve."""
    import subprocess, shutil
    if not shutil.which('ffmpeg'):
        return send_from_directory(str(audio_dir()), str(full_path.relative_to(audio_dir())))

    # Cache transcoded files next to originals with a .transcoded.m4a suffix
    cache_path = full_path.with_suffix('.transcoded.m4a')

    if not cache_path.exists():
        print(f"  Transcoding: {full_path.name} ...")
        tmp = cache_path.with_suffix('.tmp.m4a')
        cmd = [
            'ffmpeg', '-y', '-v', 'quiet',
            '-i', str(full_path),
            '-vn',
            '-c:a', 'aac', '-b:a', '192k',
            '-movflags', 'faststart',
            str(tmp)
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            print(f"  ffmpeg timeout: {full_path.name}")
            tmp.unlink(missing_ok=True)
            return send_from_directory(str(audio_dir()), str(full_path.relative_to(audio_dir())))
        if result.returncode != 0:
            print(f"  ffmpeg error: {result.stderr.decode(errors='replace')[:300]}")
            # Fall back to direct serve if transcoding fails
            return send_from_directory(str(audio_dir()), str(full_path.relative_to(audio_dir())))
        tmp.rename(cache_path)
        print(f"  Transcoded ok: {cache_path.name}")

    return send_from_directory(str(cache_path.parent), cache_path.name)

@app.route("/lyrics-file/<path:filename>")
def serve_lyric_file(filename):
    try:
        full = safe_path(lyrics_dir(), filename)
    except ValueError:
        abort(403)
    if not full.exists(): abort(404)
    return send_from_directory(str(lyrics_dir()), filename)

@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")

if __name__ == "__main__":
    print(f"\n  🎵  Song Chest")
    print(f"  📁  Audio  : {audio_dir()}" + ("  ✓" if audio_dir().exists() else "  ⚠️  not found — set in Settings"))
    print(f"  📁  Lyrics : {lyrics_dir()}" + ("  ✓" if lyrics_dir().exists() else "  ⚠️  not found — set in Settings"))
    print(f"\n  → http://localhost:5000\n")
    app.run(debug=True, port=5000)
