# Song Chest

**A local-first workspace for songwriters.** Capture audio ideas, write lyrics, organise everything into projects — all stored on your own machine as plain files.

> Current version: **v0.9.0**

---

## Features

### Ideas & Projects
- Capture **audio ideas** (link to `.m4a`, `.mp3`, `.wav`, `.aiff`, `.ogg`, `.flac`) and **lyric ideas** (`.txt`, `.md`, `.rtf`)
- Organise ideas into **projects** (EPs, albums, singles) with colour labels
- **Drag ideas** from the canvas onto a project in the sidebar to assign them instantly
- **Unassigned** view keeps your inbox clean

### Writing & Playing
- **Built-in audio player** — play any recording directly in the app; persistent mini-player keeps playing as you browse
- **Lyric viewer** with Markdown rendering and optional YAML frontmatter hiding
- **Quick capture** — press `N` anywhere to open a fast capture overlay; idea is saved and appears at the top

### Organisation
- **Status tracking** — Draft, In Progress, Finished, Archived — with sidebar filtering
- **Star** important ideas to pin them to the Starred view
- **Tags** with colour coding and one-click sidebar filtering
- **Bidirectional linking** — connect related ideas; links are maintained automatically on both ends
- **Notes** field per idea for context, chords, references
- **Search** across title, content, notes, and tags simultaneously

### File Management
- **Auto-sync** — drop files into your audio/lyrics folders and Song Chest finds them
- **File move** — assign an idea to a project and Song Chest physically moves the file into the right subfolder
- **Move history** with per-move undo

### Safety & Data
- **Trash** — deleted ideas go here first; restore or permanently delete on your terms
- **Activity feed** — every change (create, tag, status, star, assign, delete, restore) is logged with timestamps, visible in Insights
- **Export / Backup** — download a `.zip` of your data and optionally your audio and lyrics files
- All data stored in plain `data.json` — human-readable, git-friendly, no database

### Obsidian Integration *(optional)*
- Connect your Obsidian vault; tagged notes appear alongside your ideas
- **Auto-link suggestions** — Song Chest spots notes whose title matches your idea and surfaces them
- Link and unlink Obsidian notes to ideas; linked notes show up in the idea detail view
- **Sync indicator** with one-click vault refresh

### Appearance
- **4 themes** — Default (dark gold), Basic (light monochrome), Colorful (vivid neon), Custom (pick your own 5 colours)
- Custom theme updates live as you drag the colour picker
- Theme persists across sessions

---

## Setup

**Quick start:**
```bash
bash start.sh
```
`start.sh` creates a Python virtualenv, installs dependencies, starts the server, and opens your browser automatically.

**Manual:**
```bash
pip install -r requirements.txt
python server.py
# → http://localhost:5000
```

**Requirements:** Python 3.9+, Flask (installed automatically via `requirements.txt`)

---

## Configuration

On first launch, Song Chest creates a `config.json` pointing to `./audio` and `./lyrics` inside the project folder. Change these to your real folders in **Settings** or by editing the file directly:

```json
{
  "audio_folder": "/Users/you/Music/songs",
  "lyrics_folder": "/Users/you/Documents/lyrics"
}
```

`config.json` is personal to your machine and is gitignored — it never gets committed.

---

## Your data

Everything is stored in `data.json` — a plain, human-readable JSON file you can inspect, back up, or put under version control yourself. No database, no cloud, no lock-in.

---

## Running tests

```bash
# Terminal 1 — server must be running
python server.py

# Terminal 2
python test_api.py
```

---

## Roadmap

- **v1.0** — installable macOS app (drag to Applications, no terminal required)
- **v1.1** — collaboration / shared vault over local network
- **v1.2** — mobile companion (capture ideas on the go)
