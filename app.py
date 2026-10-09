import os, uuid, threading
from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp

app = Flask(__name__)
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
jobs = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/info")
def info():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify(error="Lien invalide."), 400
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "noplaylist": True}) as ydl:
            i = ydl.extract_info(url, download=False)
        return jsonify(title=i.get("title", "Inconnu"),
                       duration=i.get("duration_string", "N/A"),
                       thumbnail=i.get("thumbnail"),
                       uploader=i.get("uploader", ""))
    except Exception as e:
        return jsonify(error=str(e)), 400


def run_job(job_id, url, fmt):
    job = jobs[job_id]

    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            job["percent"] = round(d.get("downloaded_bytes", 0) * 100 / total, 1) if total else 0
            job["speed"] = (d.get("_speed_str") or "N/A").strip()
            job["status"] = "downloading"
        elif d["status"] == "finished":
            job["status"] = "processing"

    opts = {
        "progress_hooks": [hook],
        "outtmpl": os.path.join(DOWNLOAD_DIR, f"{job_id}_%(title)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
    }
    if fmt == "audio":
        opts.update({"format": "bestaudio/best", "postprocessors": [{
            "key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]})
    else:
        opts.update({"format": "bestvideo+bestaudio/best", "merge_output_format": "mp4"})
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = [f for f in os.listdir(DOWNLOAD_DIR) if f.startswith(job_id)]
        job["file"] = os.path.join(DOWNLOAD_DIR, files[0])
        job["status"], job["percent"] = "finished", 100
    except Exception as e:
        job["status"], job["error"] = "error", str(e)


@app.post("/api/download")
def download():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify(error="Lien invalide."), 400
    job_id = uuid.uuid4().hex[:10]
    jobs[job_id] = {"status": "starting", "percent": 0, "speed": "N/A"}
    threading.Thread(target=run_job, args=(job_id, url, data.get("format", "video")), daemon=True).start()
    return jsonify(id=job_id)


@app.get("/api/progress/<job_id>")
def progress(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify(error="Inconnu"), 404
    return jsonify({k: v for k, v in job.items() if k != "file"})


@app.get("/api/file/<job_id>")
def file(job_id):
    job = jobs.get(job_id)
    if not job or "file" not in job:
        return "Fichier introuvable", 404
    name = os.path.basename(job["file"]).split("_", 1)[1]
    return send_file(job["file"], as_attachment=True, download_name=name)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
