# Song Chest — local songwriting workspace

## Folder structure

```
songchest/
├── server.py         ← Flask backend
├── index.html        ← frontend (served by Flask)
├── data.json         ← all your ideas, projects, tags, links
├── requirements.txt
├── audio/            ← put your .m4a / .mp3 / .wav files here
│   └── riffs/        ← subfolders are fine
└── lyrics/           ← put your .txt / .md / .rtf files here
    └── drafts/
```

## Config

Song Chest uses a `config.json` file to know where your audio and lyrics folders live. This file is personal to your machine and is intentionally excluded from git.

To get started, copy the example and edit it:

```bash
cp config.example.json config.json
```

Then open `config.json` and point the paths at your actual folders:

```json
{
  "audio_folder": "/Users/you/Music/my-songs/audio",
  "lyrics_folder": "/Users/you/Documents/my-songs/lyrics"
}
```

You can also change these paths any time from within the app's settings.

---

## Setup (one time)

```bash
pip install -r requirements.txt
```

### If an error is thrown:

That just means your system uses pip3 instead of pip. Try:
```bash
pip3 install -r requirements.txt
```

If that also fails, try:
```bash
python3 -m pip install -r requirements.txt
```

OR, python might not work, but python3 does; then try: 
```bash
python3 server.py
```


## Run

```bash
python server.py
```

Then open **http://localhost:5000** in your browser.

## Your data

Everything is stored in `data.json` — a plain, human-readable JSON file.
You can open it in any text editor, inspect it, back it up, or put it under git version control.

Example entry:
```json
{
  "id": "a1b2c3d4",
  "type": "lyric",
  "title": "Train window watching",
  "content": "The fields turn gold and grey...",
  "project": "e5f6g7h8",
  "tags": ["verse", "melancholy", "travel"],
  "links": ["x1y2z3w4"],
  "notes": "Wrote this at Leuven station.",
  "created": 1718000000000,
  "updated": 1718003600000
}
```

## Audio files

Drop any `.m4a`, `.mp3`, `.wav`, `.aiff`, `.ogg`, or `.flac` file into the `audio/` folder.
Subfolders are supported. Song Chest will scan and list them automatically when you add an audio idea.

## Lyrics files

Drop `.txt`, `.md`, or `.rtf` files into the `lyrics/` folder.
When editing a lyric idea, you can pick a file from the list and its contents will auto-load into the text field.

## Collaboration / sharing later

Because the backend is a clean REST API (`/api/projects`, `/api/ideas`, etc.),
you can later:
- Swap `data.json` for SQLite or PostgreSQL with minimal changes to `server.py`
- Deploy to a small VPS or Railway/Render to share with a co-writer
- Add login/auth on top of the existing API routes
