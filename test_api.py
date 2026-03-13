"""
Song Chest — API test suite
Run while the server is running: python test_api.py
"""
import json, sys, os, tempfile, shutil
from pathlib import Path
import urllib.request, urllib.error

BASE = "http://localhost:5000"
PASS = 0; FAIL = 0

def req(method, path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body else None
    r = urllib.request.Request(url, data=data, method=method,
                                headers={"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {}

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        print(f"  ✓  {name}")
        PASS += 1
    else:
        print(f"  ✗  {name}" + (f"  ({detail})" if detail else ""))
        FAIL += 1

def section(title):
    print(f"\n── {title} {'─'*(50-len(title))}")

# ── connectivity ──────────────────────────────────────────────
section("Connectivity")
try:
    status, _ = req("GET", "/")
    check("Server is running", status == 200)
except Exception as e:
    print(f"\n  ERROR: Cannot connect to {BASE}")
    print(f"  Make sure the server is running: python server.py\n")
    sys.exit(1)

# ── config ────────────────────────────────────────────────────
section("Config")
s, cfg = req("GET", "/api/config")
check("GET /api/config returns 200", s == 200)
check("Config has audio_folder", "audio_folder" in cfg)
check("Config has lyrics_folder", "lyrics_folder" in cfg)
check("Config has audio_exists flag", "audio_exists" in cfg)
check("Config has lyrics_exists flag", "lyrics_exists" in cfg)

# ── data ──────────────────────────────────────────────────────
section("Data")
s, data = req("GET", "/api/data")
check("GET /api/data returns 200", s == 200)
check("Data has projects list", isinstance(data.get("projects"), list))
check("Data has ideas list", isinstance(data.get("ideas"), list))
check("Data has move_history list", isinstance(data.get("move_history"), list))

# ── scan ──────────────────────────────────────────────────────
section("Scan")
s, scan = req("GET", "/api/scan")
check("GET /api/scan returns 200", s == 200)
check("Scan has audio list", isinstance(scan.get("audio"), list))
check("Scan has lyrics list", isinstance(scan.get("lyrics"), list))

# ── projects CRUD ─────────────────────────────────────────────
section("Projects — create")
s, proj = req("POST", "/api/projects", {"name": "Test Project", "type": "EP", "color": "#DAA520"})
check("POST /api/projects returns 201", s == 201)
check("Project has id", "id" in proj)
check("Project has correct name", proj.get("name") == "Test Project")
check("Project has folder slug", "folder" in proj and proj["folder"])
check("Project type is EP", proj.get("type") == "EP")
pid = proj.get("id","")

# check folders were created on disk
cfg_path = Path(__file__).parent / "config.json"
if cfg_path.exists():
    with open(cfg_path) as f:
        cfg_data = json.load(f)
    af = Path(cfg_data.get("audio_folder","")).expanduser()
    lf = Path(cfg_data.get("lyrics_folder","")).expanduser()
    check("Audio subfolder created on disk", (af / proj["folder"]).exists(), f"expected {af/proj['folder']}")
    check("Lyrics subfolder created on disk", (lf / proj["folder"]).exists(), f"expected {lf/proj['folder']}")
else:
    print("  (skipping disk folder check — config.json not found)")

section("Projects — validation")
s, r = req("POST", "/api/projects", {"name": "", "type": "EP"})
check("Empty project name returns 400", s == 400)

section("Projects — update")
s, updated = req("PUT", f"/api/projects/{pid}", {"name": "Renamed Project", "color": "#C9281D"})
check("PUT /api/projects/:id returns 200", s == 200)
check("Name was updated", updated.get("name") == "Renamed Project")
check("Color was updated", updated.get("color") == "#C9281D")

# ── ideas CRUD ────────────────────────────────────────────────
section("Ideas — create lyric")
s, idea1 = req("POST", "/api/ideas", {
    "type": "lyric", "title": "Test Lyric",
    "content": "These are\ntest lyrics", "project": pid,
    "tags": ["verse","test"], "notes": "some notes"
})
check("POST /api/ideas returns 201", s == 201)
check("Idea has id", "id" in idea1)
check("Idea type is lyric", idea1.get("type") == "lyric")
check("Idea has correct title", idea1.get("title") == "Test Lyric")
check("Idea has tags", idea1.get("tags") == ["verse","test"])
check("Idea has project", idea1.get("project") == pid)
iid1 = idea1.get("id","")

section("Ideas — create audio")
s, idea2 = req("POST", "/api/ideas", {
    "type": "audio", "title": "Test Riff",
    "audiofile": "", "project": None, "tags": []
})
check("POST audio idea returns 201", s == 201)
iid2 = idea2.get("id","")

section("Ideas — validation")
s, r = req("POST", "/api/ideas", {"type": "lyric", "title": ""})
check("Empty title returns 400", s == 400)
s, r = req("POST", "/api/ideas", {"title": "no type"})
check("Missing type returns 400", s == 400)

section("Ideas — linking")
s, linked = req("PUT", f"/api/ideas/{iid1}", {
    "type":"lyric","title":"Test Lyric","content":"",
    "project":pid,"tags":["verse","test"],"notes":"",
    "links":[iid2],"audiofile":"","lyricfile":""
})
check("Linking idea returns 200", s == 200)
check("Idea1 has link to idea2", iid2 in linked.get("links",[]))

# verify bidirectional link
s, data2 = req("GET", "/api/data")
idea2_updated = next((i for i in data2["ideas"] if i["id"]==iid2), None)
check("Bidirectional link created on idea2", idea2_updated and iid1 in idea2_updated.get("links",[]))

section("Ideas — unlink")
s, unlinked = req("PUT", f"/api/ideas/{iid1}", {
    "type":"lyric","title":"Test Lyric","content":"",
    "project":pid,"tags":["verse","test"],"notes":"",
    "links":[],"audiofile":"","lyricfile":""
})
s, data3 = req("GET", "/api/data")
idea2_check = next((i for i in data3["ideas"] if i["id"]==iid2), None)
check("Unlinking removes bidirectional link", idea2_check and iid1 not in idea2_check.get("links",[]))

section("Ideas — notes patch")
s, r = req("PATCH", f"/api/ideas/{iid1}/notes", {"notes": "patched notes"})
check("PATCH notes returns 200", s == 200)
s, data4 = req("GET", "/api/data")
i1 = next((i for i in data4["ideas"] if i["id"]==iid1), None)
check("Notes were saved", i1 and i1.get("notes") == "patched notes")

# ── sync ──────────────────────────────────────────────────────
section("Sync")
s, sync_r = req("POST", "/api/sync")
check("POST /api/sync returns 200", s == 200)
check("Sync returns imported count", "imported" in sync_r)
check("Sync imported is integer", isinstance(sync_r.get("imported"), int))

# run again — should import 0 new (idempotent)
s, sync_r2 = req("POST", "/api/sync")
check("Second sync imports 0 (idempotent)", sync_r2.get("imported") == 0)

# ── move preview ──────────────────────────────────────────────
section("Move — preview")
# create idea with a fake audiofile path to test preview
s, idea3 = req("POST", "/api/ideas", {
    "type":"audio","title":"Move Test","audiofile":"test-song.m4a",
    "project":None,"tags":[]
})
iid3 = idea3.get("id","")
s, preview = req("POST", "/api/move/preview", {
    "idea_id": iid3, "target_project_id": pid
})
check("Move preview returns 200", s == 200)
check("Preview has moves list", "moves" in preview)
check("Preview has idea", "idea" in preview)
check("Preview has target_project", "target_project" in preview)
if preview.get("moves"):
    m = preview["moves"][0]
    check("Move has from/to paths", "from" in m and "to" in m)
    check("Move has collision flag", "collision" in m)
    check("Dest is in project folder", m["to"].startswith(proj["folder"]))

section("Move — preview with no file")
s, idea4 = req("POST", "/api/ideas", {"type":"audio","title":"No File","audiofile":"","project":None,"tags":[]})
iid4 = idea4.get("id","")
s, preview2 = req("POST", "/api/move/preview", {"idea_id":iid4,"target_project_id":pid})
check("Preview with no file returns 200", s == 200)
check("Preview with no file has 0 moves", len(preview2.get("moves",[])) == 0)

# ── move history ──────────────────────────────────────────────
section("Move history")
s, hist = req("GET", "/api/move/history")
check("GET /api/move/history returns 200", s == 200)
check("History is a list", isinstance(hist, list))

# ── delete ────────────────────────────────────────────────────
section("Delete ideas")
s, _ = req("DELETE", f"/api/ideas/{iid1}")
check("DELETE idea returns 200", s == 200)
s, data5 = req("GET", "/api/data")
check("Idea is gone from data", not any(i["id"]==iid1 for i in data5["ideas"]))

section("Delete project")
s, _ = req("DELETE", f"/api/projects/{pid}")
check("DELETE project returns 200", s == 200)
s, data6 = req("GET", "/api/data")
check("Project is gone", not any(p["id"]==pid for p in data6["projects"]))
# ideas that were in the project should have project=None
remaining = [i for i in data6["ideas"] if i["id"] in (iid2,iid3,iid4)]
for i in remaining:
    req("DELETE", f"/api/ideas/{i['id']}")

# ── edge cases ────────────────────────────────────────────────
section("Edge cases")
s, _ = req("GET", "/api/ideas/nonexistent-id")
check("GET non-existent idea returns 404 or 405", s in (404, 405))
s, _ = req("PUT", "/api/ideas/nonexistent-id", {"title":"x","type":"lyric"})
check("PUT non-existent idea returns 404", s == 404)
s, _ = req("DELETE", "/api/ideas/nonexistent-id")
check("DELETE non-existent idea returns 200 (no-op)", s == 200)
s, _ = req("POST", "/api/move/preview", {"idea_id":"nonexistent","target_project_id":None})
check("Move preview non-existent idea returns 404", s == 404)

# ── summary ───────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'═'*52}")
print(f"  {PASS}/{total} tests passed", "✓" if FAIL==0 else f"— {FAIL} FAILED")
print(f"{'═'*52}\n")
sys.exit(0 if FAIL==0 else 1)
