"""
Song Chest — local server
Run: ./start.sh  or  python server.py
Open: http://localhost:5000
"""

import json, os, shutil, uuid, time, re, hashlib, urllib.parse
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory, send_file, abort

APP_VERSION = "0.9.0"

app = Flask(__name__, static_folder=".")

BASE_DIR    = Path(__file__).parent
DATA_FILE   = BASE_DIR / "data.json"
CONFIG_FILE = BASE_DIR / "config.json"

AUDIO_EXT  = {".m4a", ".mp3", ".wav", ".aiff", ".ogg", ".flac"}
LYRICS_EXT = {".txt", ".md", ".rtf"}

# RTF metadata group keywords whose entire content should be ignored
_RTF_SKIP = frozenset([
    'fonttbl', 'colortbl', 'stylesheet', 'pict', 'info', 'header',
    'footer', 'footnote', 'filetbl', 'listtable', 'expandedcolortbl',
    'themedata', 'colorschememapping', 'datastore', 'wgrffmtfilter',
])

def rtf_to_text(data):
    """Convert RTF to plain text using a state-machine parser."""
    if isinstance(data, bytes):
        try:   src = data.decode('utf-8')
        except UnicodeDecodeError: src = data.decode('latin-1')
    else:
        src = data

    out = []
    i = 0
    depth = 0       # current brace nesting depth
    skip_depth = 0  # depth at which an ignored group started (0 = not skipping)

    while i < len(src):
        c = src[i]

        if c == '{':
            depth += 1
            i += 1
            # Ignorable destination: {\* ...} or {\knownkeyword ...}
            if not skip_depth:
                if src[i:i+2] == '\\*':
                    skip_depth = depth
                    i += 2
                    if i < len(src) and src[i] == ' ':
                        i += 1
                elif src[i] == '\\' and i + 1 < len(src) and src[i + 1].isalpha():
                    j = i + 1
                    while j < len(src) and src[j].isalpha():
                        j += 1
                    if src[i + 1:j] in _RTF_SKIP:
                        skip_depth = depth

        elif c == '}':
            if skip_depth == depth:
                skip_depth = 0
            depth -= 1
            i += 1

        elif c == '\\' and i + 1 < len(src):
            n = src[i + 1]
            if n in ('{', '}', '\\'):          # escaped literal
                if not skip_depth:
                    out.append(n)
                i += 2
            elif n == '\n':                    # escaped newline
                if not skip_depth:
                    out.append('\n')
                i += 2
            elif n == '~':                     # non-breaking space
                if not skip_depth:
                    out.append('\u00a0')
                i += 2
            elif n == "'":                     # hex escape \'XX
                if i + 3 < len(src):
                    try:
                        ch = bytes.fromhex(src[i + 2:i + 4]).decode('cp1252', errors='replace')
                        if not skip_depth:
                            out.append(ch)
                    except Exception:
                        pass
                    i += 4
                else:
                    i += 2
            elif n.isalpha():                  # control word
                j = i + 1
                while j < len(src) and src[j].isalpha():
                    j += 1
                word = src[i + 1:j]
                if j < len(src) and src[j] == '-':
                    j += 1
                while j < len(src) and src[j].isdigit():
                    j += 1
                if j < len(src) and src[j] == ' ':
                    j += 1
                if not skip_depth:
                    if word in ('par', 'pard', 'sect', 'page', 'line'):
                        out.append('\n')
                    elif word == 'tab':
                        out.append('\t')
                i = j
            else:
                i += 2

        else:
            if not skip_depth and c not in ('\r', '\n'):
                out.append(c)
            i += 1

    text = ''.join(out)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    return text.strip()

# ── config ────────────────────────────────────────────────────

def load_config():
    obs_default = {
        "enabled": False,
        "vault_path": "",
        "vault_name": "",
        "filter": {"tags": ["song-idea"], "folders": []},
        "preview_length": 120,
    }
    defaults = {
        "audio_folder":  str(BASE_DIR / "audio"),
        "lyrics_folder": str(BASE_DIR / "lyrics"),
        "integrations": {"obsidian": obs_default},
        "preferences": {},
    }
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k in ("audio_folder", "lyrics_folder"):
            cfg[k] = str(Path(cfg.get(k, defaults[k])).expanduser().resolve())
        # Deep-merge integrations block so missing keys get defaults
        ci = cfg.setdefault("integrations", {})
        co = ci.setdefault("obsidian", {})
        for k, v in obs_default.items():
            if k == "filter":
                cf = co.setdefault("filter", {})
                for fk, fv in v.items():
                    cf.setdefault(fk, fv)
            elif k not in co:
                co[k] = v
        # Normalize vault_path with normpath (not resolve) to avoid macOS /var→/private/var symlink issues
        vp = co.get("vault_path", "")
        if vp:
            co["vault_path"] = os.path.normpath(os.path.expanduser(vp))
        return cfg
    save_config(defaults)
    return defaults

def save_config(cfg):
    tmp = CONFIG_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    tmp.replace(CONFIG_FILE)

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
        d.setdefault("obsidian_links", [])
        d.setdefault("trash", [])
        return d
    return {"projects": [], "ideas": [], "move_history": [], "obsidian_links": [], "trash": []}

def save_data(data):
    tmp = DATA_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(DATA_FILE)

def new_id():  return str(uuid.uuid4())[:8]
def now_ms():  return int(time.time() * 1000)

_ACTIVITY_CAP = 500

def append_activity(data, kind, idea, detail=None):
    """Append one activity entry; keep only the most recent _ACTIVITY_CAP."""
    entry = {
        "id":       new_id(),
        "ts":       now_ms(),
        "kind":     kind,          # created|updated|deleted|restored|moved|tagged|status|starred|notes
        "idea_id":  idea["id"],
        "title":    idea["title"],
    }
    if detail: entry["detail"] = detail
    data.setdefault("activity", []).insert(0, entry)
    data["activity"] = data["activity"][:_ACTIVITY_CAP]

# ── filesystem helpers ────────────────────────────────────────

def scan_files():
    result = {"audio": [], "lyrics": []}
    for kind, root, exts in [("audio", audio_dir(), AUDIO_EXT),
                              ("lyrics", lyrics_dir(), LYRICS_EXT)]:
        if root.exists():
            for p in sorted(root.rglob("*")):
                if p.suffix.lower() in exts and not p.name.endswith('.transcoded.m4a'):
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
                    "lyrics_exists": lyrics_dir().exists(),
                    "version":       APP_VERSION})

@app.route("/api/config", methods=["POST"])
def update_config():
    global CONFIG
    body = request.json
    for k in ("audio_folder", "lyrics_folder"):
        if body.get(k):
            CONFIG[k] = str(Path(body[k]).expanduser().resolve())
    if "preferences" in body:
        CONFIG.setdefault("preferences", {}).update(body["preferences"])
    if "integrations" in body:
        intg = body["integrations"]
        obs = intg.get("obsidian", {})
        if obs.get("enabled") and not obs.get("vault_path", "").strip():
            return jsonify({"error": "vault_path is required when Obsidian integration is enabled"}), 400
        CONFIG.setdefault("integrations", {})
        # Deep-merge obsidian sub-object to preserve keys the client doesn't send (e.g. preview_length)
        if "obsidian" in intg:
            existing = CONFIG["integrations"].setdefault("obsidian", {})
            existing.update(intg["obsidian"])
        for k, v in intg.items():
            if k != "obsidian":
                CONFIG["integrations"][k] = v
        # Normalize vault_path
        vp = CONFIG["integrations"].get("obsidian", {}).get("vault_path", "")
        if vp:
            CONFIG["integrations"]["obsidian"]["vault_path"] = os.path.normpath(os.path.expanduser(vp))
    save_config(CONFIG)
    audio_dir().mkdir(parents=True, exist_ok=True)
    lyrics_dir().mkdir(parents=True, exist_ok=True)
    return jsonify({**CONFIG,
                    "audio_exists":  audio_dir().exists(),
                    "lyrics_exists": lyrics_dir().exists()})

# ── obsidian integration ──────────────────────────────────────

_OBSIDIAN_SCAN_DEPTH = 3

def _parse_obsidian_frontmatter(text):
    """Return (tags, title, body) parsed from a markdown file with optional YAML frontmatter."""
    tags, title, body = [], None, text
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end].strip()
            body = text[end + 4:].lstrip("\n")
            # title
            m = re.search(r"^title:\s*(.+)$", fm, re.MULTILINE)
            if m:
                title = m.group(1).strip().strip("\"'")
            # tags: [a, b] inline
            m = re.search(r"^tags:\s*\[(.+)\]", fm, re.MULTILINE)
            if m:
                tags = [t.strip().strip("\"'") for t in m.group(1).split(",") if t.strip()]
            else:
                # tags:\n  - a\n  - b multiline
                m = re.search(r"^tags:\s*\n((?:[ \t]*-[ \t]*.+\n?)+)", fm, re.MULTILINE)
                if m:
                    for line in m.group(1).splitlines():
                        lm = re.match(r"[ \t]*-[ \t]*(.+)", line)
                        if lm:
                            tags.append(lm.group(1).strip().strip("\"'"))
    return tags, title, body

def scan_obsidian_vault(cfg):
    obs = cfg.get("integrations", {}).get("obsidian", {})
    if not obs.get("enabled") or not obs.get("vault_path", ""):
        return []
    vault_path = Path(obs["vault_path"])
    if not vault_path.exists():
        return []

    vault_name = obs.get("vault_name", "") or vault_path.name
    filter_tags = set(obs.get("filter", {}).get("tags", []))
    filter_folders = obs.get("filter", {}).get("folders", [])
    preview_length = int(obs.get("preview_length", 120))
    both_empty = not filter_tags and not filter_folders

    results = []

    def _walk(path, depth):
        if depth > _OBSIDIAN_SCAN_DEPTH:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda e: e.name)
        except PermissionError:
            return
        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                _walk(entry, depth + 1)
            elif entry.is_file() and entry.suffix.lower() == ".md":
                try:
                    vault_rel = str(entry.relative_to(vault_path))

                    # Folder check before file I/O for speed
                    # Use path-boundary-aware prefix to avoid "Song" matching "Song Ideas/"
                    folder_match = bool(filter_folders and any(
                        vault_rel == f.rstrip("/") or
                        vault_rel.startswith(f.rstrip("/") + "/")
                        for f in filter_folders
                    ))

                    # Short-circuit: folder filter active, no folder match, and no tag filter
                    if not both_empty and not folder_match and not filter_tags:
                        continue

                    text = entry.read_text(encoding="utf-8", errors="replace")
                    tags, title, body = _parse_obsidian_frontmatter(text)

                    tag_match = bool(filter_tags and filter_tags & set(tags))

                    if not (both_empty or tag_match or folder_match):
                        continue

                    if not title:
                        title = re.sub(r"[-_]", " ", entry.stem).strip().capitalize()

                    stable_id = hashlib.sha1(vault_rel.encode()).hexdigest()[:8]
                    encoded_path = urllib.parse.quote(vault_rel, safe="")
                    obsidian_uri = (
                        f"obsidian://open?vault={urllib.parse.quote(vault_name, safe='')}"
                        f"&file={encoded_path}"
                    )

                    results.append({
                        "id": stable_id,
                        "title": title,
                        "vault_relative_path": vault_rel,
                        "tags": tags,
                        "preview": body[:preview_length].strip(),
                        "last_modified": int(entry.stat().st_mtime * 1000),
                        "obsidian_uri": obsidian_uri,
                    })
                except Exception:
                    continue

    _walk(vault_path, 0)
    return results

@app.route("/api/browse-folder", methods=["POST"])
def browse_folder():
    """Open a native folder-picker dialog and return the selected path."""
    title = (request.json or {}).get("title", "Select Folder")
    import subprocess
    try:
        # macOS: AppleScript is always available, no extra deps
        script = f'POSIX path of (choose folder with prompt "{title}")'
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            return jsonify({"path": r.stdout.strip().rstrip("/")})
        return jsonify({"path": None})
    except FileNotFoundError:
        # osascript not available (non-macOS) — fall back to tkinter
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
            path = filedialog.askdirectory(title=title)
            root.destroy()
            return jsonify({"path": path or None})
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"path": None})

@app.route("/api/obsidian/note-content")
def obsidian_note_content():
    obs = CONFIG.get("integrations", {}).get("obsidian", {})
    if not obs.get("enabled") or not obs.get("vault_path"):
        return jsonify({"error": "Obsidian not enabled"}), 400
    vault = Path(obs["vault_path"])
    rel = request.args.get("path", "").strip()
    if not rel:
        return jsonify({"error": "path required"}), 400
    try:
        full = Path(os.path.normpath(vault / rel))
    except Exception:
        abort(400)
    if not str(full).startswith(str(vault) + os.sep):
        abort(403)
    if not full.exists() or not full.is_file():
        abort(404)
    return full.read_text(encoding="utf-8", errors="replace"), 200, \
        {"Content-Type": "text/plain; charset=utf-8"}

@app.route("/api/obsidian/notes")
def obsidian_notes():
    return jsonify(scan_obsidian_vault(CONFIG))

@app.route("/api/obsidian/link", methods=["POST"])
def obsidian_link():
    data = load_data()
    body = request.json
    idea_id = body.get("idea_id", "")
    note_id = body.get("note_id", "")
    if not idea_id or not note_id:
        return jsonify({"error": "idea_id and note_id required"}), 400
    links = data.setdefault("obsidian_links", [])
    if not any(l["idea_id"] == idea_id and l["note_id"] == note_id for l in links):
        links.append({"idea_id": idea_id, "note_id": note_id})
        save_data(data)
    return jsonify({"ok": True})

@app.route("/api/obsidian/link/<idea_id>/<note_id>", methods=["DELETE"])
def obsidian_unlink(idea_id, note_id):
    data = load_data()
    data.setdefault("obsidian_links", [])
    data["obsidian_links"] = [
        l for l in data["obsidian_links"]
        if not (l["idea_id"] == idea_id and l["note_id"] == note_id)
    ]
    save_data(data)
    return jsonify({"ok": True})

@app.route("/api/obsidian/status")
def obsidian_status():
    obs = CONFIG.get("integrations", {}).get("obsidian", {})
    enabled = obs.get("enabled", False)
    vault_path = obs.get("vault_path", "")
    vault_exists = bool(vault_path and Path(vault_path).exists())
    note_count = len(scan_obsidian_vault(CONFIG)) if (enabled and vault_exists) else 0
    return jsonify({"enabled": enabled, "vault_exists": vault_exists, "note_count": note_count})

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
            "notes": body.get("notes",""), "status": body.get("status","draft"),
            "starred": bool(body.get("starred",False)),
            "created": now_ms(), "updated": now_ms()}
    for lid in idea["links"]:
        other = next((x for x in data["ideas"] if x["id"]==lid), None)
        if other and idea["id"] not in other["links"]: other["links"].append(idea["id"])
    data["ideas"].insert(0, idea)
    append_activity(data, "created", idea)
    save_data(data); return jsonify(idea), 201

@app.route("/api/ideas/<iid>", methods=["PUT"])
def update_idea(iid):
    data = load_data()
    idea = next((x for x in data["ideas"] if x["id"]==iid), None)
    if not idea: abort(404)
    old_links  = set(idea.get("links",[]))
    old_proj   = idea.get("project")
    old_tags   = set(idea.get("tags",[]))
    old_status = idea.get("status","draft")
    old_starred= idea.get("starred", False)
    old_notes  = idea.get("notes","")
    body = request.json
    for k in ("type","title","content","audiofile","lyricfile","project","tags","links","notes","status","starred"):
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
    # activity logging — one entry per meaningful change
    if idea.get("project") != old_proj:
        proj_names = {p["id"]: p["name"] for p in data.get("projects",[])}
        dest = proj_names.get(idea["project"], "Unassigned") if idea["project"] else "Unassigned"
        append_activity(data, "moved", idea, dest)
    elif set(idea.get("tags",[])) != old_tags:
        added   = set(idea.get("tags",[])) - old_tags
        removed = old_tags - set(idea.get("tags",[]))
        if added:   append_activity(data, "tagged",   idea, f'+{", ".join(sorted(added))}')
        if removed: append_activity(data, "tagged",   idea, f'-{", ".join(sorted(removed))}')
    elif idea.get("status","draft") != old_status:
        append_activity(data, "status", idea, idea.get("status","draft"))
    elif idea.get("starred", False) != old_starred:
        append_activity(data, "starred", idea, "starred" if idea.get("starred") else "unstarred")
    elif idea.get("notes","") != old_notes:
        append_activity(data, "notes", idea)
    else:
        append_activity(data, "updated", idea)
    save_data(data); return jsonify(idea)

@app.route("/api/ideas/<iid>", methods=["DELETE"])
def delete_idea(iid):
    data = load_data()
    idea = next((x for x in data["ideas"] if x["id"] == iid), None)
    if not idea: return jsonify({"ok": True})  # already gone — idempotent
    # Soft-delete: remove from ideas, sever links, move to trash
    data["ideas"] = [x for x in data["ideas"] if x["id"] != iid]
    for other in data["ideas"]: other["links"] = [l for l in other["links"] if l != iid]
    data["obsidian_links"] = [l for l in data.get("obsidian_links", []) if l["idea_id"] != iid]
    idea["deleted_at"] = now_ms()
    data.setdefault("trash", []).insert(0, idea)
    append_activity(data, "deleted", idea)
    save_data(data); return jsonify({"ok": True})

@app.route("/api/trash")
def get_trash():
    data = load_data()
    return jsonify(sorted(data.get("trash", []), key=lambda x: x.get("deleted_at", 0), reverse=True))

@app.route("/api/trash/<iid>/restore", methods=["POST"])
def restore_idea(iid):
    data = load_data()
    idea = next((x for x in data.get("trash", []) if x["id"] == iid), None)
    if not idea: abort(404)
    data["trash"] = [x for x in data["trash"] if x["id"] != iid]
    idea.pop("deleted_at", None)
    idea["updated"] = now_ms()
    data["ideas"].insert(0, idea)
    append_activity(data, "restored", idea)
    save_data(data); return jsonify(idea)

@app.route("/api/trash/<iid>", methods=["DELETE"])
def delete_from_trash(iid):
    data = load_data()
    data["trash"] = [x for x in data.get("trash", []) if x["id"] != iid]
    save_data(data); return jsonify({"ok": True})

@app.route("/api/trash", methods=["DELETE"])
def empty_trash():
    data = load_data()
    count = len(data.get("trash", []))
    data["trash"] = []
    save_data(data); return jsonify({"ok": True, "removed": count})

@app.route("/api/activity")
def get_activity():
    data = load_data()
    return jsonify(data.get("activity", []))

@app.route("/api/ideas/<iid>/notes", methods=["PATCH"])
def patch_notes(iid):
    data = load_data()
    idea = next((x for x in data["ideas"] if x["id"]==iid), None)
    if not idea: abort(404)
    idea["notes"] = request.json.get("notes","")
    idea["updated"] = now_ms()
    append_activity(data, "notes", idea)
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
        proj_names = {p["id"]: p["name"] for p in data.get("projects",[])}
        dest = proj_names.get(idea["project"], "Unassigned") if idea["project"] else "Unassigned"
        append_activity(data, "moved", idea, dest)
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
    proj_names = {p["id"]: p["name"] for p in data.get("projects",[])}
    dest = proj_names.get(entry.get("from_project"), "Unassigned") if entry.get("from_project") else "Unassigned"
    idea["project"] = entry.get("from_project")
    idea["updated"] = now_ms()
    entry["undone"] = True
    append_activity(data, "moved", idea, dest + " (undone)")
    save_data(data)
    return jsonify({"ok":True,"warnings":warnings,"idea":idea})

@app.route("/api/export")
def export_data():
    import io, zipfile as zf_mod
    include_audio  = request.args.get('audio')  == '1'
    include_lyrics = request.args.get('lyrics') == '1'
    buf = io.BytesIO()
    with zf_mod.ZipFile(buf, 'w', zf_mod.ZIP_DEFLATED) as zf:
        if DATA_FILE.exists():
            zf.write(str(DATA_FILE), 'data.json')
        if include_audio:
            adir = audio_dir()
            if adir.exists():
                for p in sorted(adir.rglob('*')):
                    if p.is_file() and not p.name.endswith('.transcoded.m4a'):
                        zf.write(str(p), 'audio/' + str(p.relative_to(adir)))
        if include_lyrics:
            ldir = lyrics_dir()
            if ldir.exists():
                for p in sorted(ldir.rglob('*')):
                    if p.is_file():
                        zf.write(str(p), 'lyrics/' + str(p.relative_to(ldir)))
    buf.seek(0)
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name='song-chest-backup.zip')

@app.route("/api/move/history")
def move_history():
    data = load_data()
    hist = sorted(data.get("move_history",[]), key=lambda h:h["ts"], reverse=True)[:50]
    return jsonify(hist)

# ── cleanup transcoded cache ───────────────────────────────────

@app.route("/api/cleanup/transcoded", methods=["POST"])
def cleanup_transcoded():
    data = load_data()
    adir = audio_dir()

    removed_ideas = []
    removed_files = []
    warnings = []

    # Remove idea entries pointing to .transcoded.m4a files
    keep = []
    for idea in data["ideas"]:
        af = idea.get("audiofile") or ""
        if af.endswith(".transcoded.m4a"):
            removed_ideas.append(idea["id"])
            # Remove this idea from any linked ideas
            for other in data["ideas"]:
                if idea["id"] in other.get("links", []):
                    other["links"] = [l for l in other["links"] if l != idea["id"]]
        else:
            keep.append(idea)
    data["ideas"] = keep

    # Delete .transcoded.m4a files from disk
    if adir.exists():
        for p in adir.rglob("*.transcoded.m4a"):
            try:
                p.unlink()
                removed_files.append(str(p.relative_to(adir)))
            except OSError as e:
                warnings.append(f"Could not delete {p.name}: {e}")

    save_data(data)
    return jsonify({
        "removed_ideas": removed_ideas,
        "removed_files": removed_files,
        "warnings": warnings
    })

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
    if full.suffix.lower() == '.rtf':
        plain = rtf_to_text(full.read_bytes())
        return plain, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    return send_from_directory(str(lyrics_dir()), filename)

@app.route("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")

if __name__ == "__main__":
    print(f"\n  🎵  Song Chest")
    print(f"  📁  Audio  : {audio_dir()}" + ("  ✓" if audio_dir().exists() else "  ⚠️  not found — set in Settings"))
    print(f"  📁  Lyrics : {lyrics_dir()}" + ("  ✓" if lyrics_dir().exists() else "  ⚠️  not found — set in Settings"))
    print(f"\n  → http://localhost:5000\n")
    app.run(host="0.0.0.0", debug=True, port=5000)
