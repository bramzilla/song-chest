FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY server.py index.html ./

# Copy demo data (fresh state on every container start)
COPY demo/data.json   ./data.json
COPY demo/config.json ./config.json

# Copy demo lyric files (used by the lonesome demo after Sync)
COPY demo/lyrics/ ./lyrics/

# Generate silent placeholder WAV files for the audio folder.
# These let the lonesome demo show real audio ideas after Sync,
# without committing binary files to the repo.
RUN python3 -c "
import wave, os
os.makedirs('audio', exist_ok=True)
tracks = [
    'hotel-lobby-piano-loop',
    'chorus-melody-summer',
    'guitar-riff-descending',
    'full-band-take-live-room',
]
for name in tracks:
    with wave.open(f'audio/{name}.wav', 'w') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(22050)
        f.writeframes(b'\x00\x00' * 22050)  # 1 second of silence
"

EXPOSE 5000

# Run without debug mode or reloader
CMD ["python", "-c", \
     "import server; server.app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)"]
