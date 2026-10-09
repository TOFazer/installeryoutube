"""Moteur de téléchargement (yt-dlp) : options, progression, annulation, reprise."""
import hashlib
import os
import re
import time
import uuid
from dataclasses import dataclass, field, asdict

import yt_dlp

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:  # FFmpeg système en secours
    FFMPEG = None

STATUSES = ("pending", "running", "processing", "done", "failed", "cancelled")


class Cancelled(Exception):
    pass


@dataclass
class DownloadTask:
    url: str
    title: str = ""
    fmt: str = "mp4"            # mp4 | original | mp3 | wav
    quality: str = "best"       # best | hauteur
    project: str = ""
    dest: str = ""
    source: str = ""
    thumbnail: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    status: str = "pending"
    progress: float = 0.0       # 0..1
    speed: float = 0.0          # octets/s
    speed_samples: list = field(default_factory=list)   # historique pour le graphique
    avg_speed: float = 0.0
    connections: int = 0
    sha256: str = ""
    eta: int | None = None
    downloaded: int = 0
    total: int = 0
    error: str = ""
    file: str = ""
    info: dict = field(default_factory=dict)
    cancel_requested: bool = field(default=False, repr=False)

    @property
    def key(self) -> tuple:
        return (self.url, self.fmt, self.quality, self.project)

    @property
    def is_active(self) -> bool:
        return self.status in ("pending", "running", "processing")

    def reset(self):
        self.status, self.progress, self.speed, self.eta = "pending", 0.0, 0.0, None
        self.downloaded = 0
        self.speed_samples = []
        self.error = ""
        self.cancel_requested = False
        self.__dict__.pop("_recorded", None)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("cancel_requested", None)
        d.pop("speed_samples", None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "DownloadTask":
        fields = cls.__dataclass_fields__
        return cls(**{k: v for k, v in d.items() if k in fields and k != "cancel_requested"})


def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "media"


def auto_fragments(total_bytes: int | None, user_value) -> int:
    """Nombre de connexions adapté à la taille du fichier (si l'utilisateur a choisi 'auto' = 0)."""
    v = int(user_value or 0)
    if v > 0:
        return min(v, 16)
    if not total_bytes:
        return 4
    mb = total_bytes / 1_048_576
    return 2 if mb < 20 else 4 if mb < 200 else 8 if mb < 1000 else 12


def sha256(path: str, chunk=1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while b := f.read(chunk):
            h.update(b)
    return h.hexdigest()


def verify_file(path: str, expected_size: int | None = None) -> tuple[bool, str]:
    """Vérification d'intégrité : fichier présent, non vide, pas de .part, taille cohérente, conteneur lisible."""
    if not path or not os.path.exists(path):
        return False, "Fichier introuvable"
    size = os.path.getsize(path)
    if size == 0:
        return False, "Fichier vide"
    if os.path.exists(path + ".part"):
        return False, "Téléchargement incomplet (.part)"
    if FFMPEG:
        import subprocess
        try:
            r = subprocess.run([FFMPEG, "-v", "error", "-i", path, "-t", "1", "-f", "null", "-"],
                               capture_output=True, timeout=60,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode != 0:
                return False, "Fichier illisible (conteneur corrompu)"
        except Exception:  # noqa: BLE001
            pass
    return True, "OK"


def build_options(task: DownloadTask, *, fragments=4, speed_limit_mb=0, name_template="%(title)s") -> dict:
    os.makedirs(task.dest, exist_ok=True)
    opts = {
        "outtmpl": os.path.join(task.dest, f"{name_template}.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "continuedl": True,                 # reprise des fichiers .part
        "retries": 10,
        "fragment_retries": 10,
        "file_access_retries": 5,
        "socket_timeout": 20,
        "concurrent_fragment_downloads": auto_fragments(task.total, fragments),
        "windowsfilenames": True,
        "overwrites": False,
    }
    if speed_limit_mb:
        opts["ratelimit"] = int(float(speed_limit_mb) * 1024 * 1024)
    if FFMPEG:
        opts["ffmpeg_location"] = FFMPEG

    h = "" if task.quality in ("best", "", None) else f"[height<={int(task.quality)}]"
    if task.fmt == "mp3":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}]
    elif task.fmt == "wav":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}]
    elif task.fmt == "original":
        opts["format"] = f"bestvideo{h}+bestaudio/best{h}/best"
        opts["merge_output_format"] = "mkv"
    else:  # mp4 H.264 + AAC : lisible par Premiere, DaVinci, Final Cut…
        opts["format"] = (f"bestvideo{h}[vcodec^=avc1]+bestaudio[ext=m4a]/"
                          f"bestvideo{h}[ext=mp4]+bestaudio[ext=m4a]/"
                          f"bestvideo{h}+bestaudio/best{h}/best")
        opts["merge_output_format"] = "mp4"
    return opts


def extract_tech(info: dict) -> dict:
    """Infos utiles au montage."""
    w, h = info.get("width"), info.get("height")
    return {
        "resolution": f"{w}x{h}" if w and h else (f"{h}p" if h else ""),
        "fps": info.get("fps"),
        "vcodec": (info.get("vcodec") or "").split(".")[0] if info.get("vcodec") not in (None, "none") else "",
        "acodec": (info.get("acodec") or "").split(".")[0] if info.get("acodec") not in (None, "none") else "",
        "duration": info.get("duration"),
        "source": info.get("extractor_key", ""),
    }


def run_task(task: DownloadTask, on_update, **opt_kwargs) -> None:
    """Exécute le téléchargement (bloquant, à lancer dans un thread)."""
    last = [0.0]

    def hook(d):
        if task.cancel_requested:
            raise Cancelled()
        if d["status"] == "downloading":
            task.status = "running"
            task.downloaded = d.get("downloaded_bytes") or 0
            task.total = d.get("total_bytes") or d.get("total_bytes_estimate") or task.total
            task.progress = task.downloaded / task.total if task.total else 0
            task.speed = d.get("speed") or 0
            task.eta = d.get("eta")
            now = time.monotonic()
            if now - last[0] > 0.5:
                last[0] = now
                task.speed_samples.append(task.speed)
                del task.speed_samples[:-120]
                on_update(task)
        elif d["status"] == "finished":
            task.status = "processing"
            on_update(task)

    def pp_hook(d):
        if task.cancel_requested:
            raise Cancelled()
        if d.get("status") == "started":
            task.status = "processing"
            on_update(task)

    opts = build_options(task, **opt_kwargs)
    task.connections = opts["concurrent_fragment_downloads"]
    started = time.monotonic()
    opts["progress_hooks"] = [hook]
    opts["postprocessor_hooks"] = [pp_hook]
    task.status = "running"
    on_update(task)
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(task.url, download=True)
            if not task.title:
                task.title = info.get("title", "")
            reqs = info.get("requested_downloads") or []
            path = reqs[0].get("filepath") if reqs else None
            task.file = path or ydl.prepare_filename(info)
            task.info = extract_tech(info)
        elapsed = max(time.monotonic() - started, 0.001)
        ok, why = verify_file(task.file)
        if not ok:
            raise RuntimeError(f"Vérification d'intégrité échouée : {why}")
        size = os.path.getsize(task.file)
        task.total = task.downloaded = size
        task.avg_speed = size / elapsed
        task.info.update({"size": size, "avg_speed": task.avg_speed, "connections": task.connections})
        task.status = "processing"
        on_update(task)
        task.sha256 = sha256(task.file)
        task.info["sha256"] = task.sha256
        task.status, task.progress, task.speed, task.eta = "done", 1.0, 0, 0
    except Cancelled:
        task.status = "cancelled"
    except Exception as e:  # noqa: BLE001
        if task.cancel_requested:
            task.status = "cancelled"
        else:
            task.status = "failed"
            msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).replace("ERROR: ", "")
            task.error = msg[:300]
    on_update(task)
