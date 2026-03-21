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

# Create empty audio/lyrics folders
RUN mkdir -p audio lyrics

EXPOSE 5000

# Run without debug mode or reloader
CMD ["python", "-c", \
     "import server; server.app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)"]
