"""Analyse des liens : validation, qualités disponibles, infos techniques."""
from dataclasses import dataclass, field
import ipaddress
from urllib.parse import urlparse

import yt_dlp


def split_urls(text: str) -> list[str]:
    seen, out = set(), []
    for part in text.replace(",", "\n").split():
        u = part.strip()
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


_BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "0.0.0.0"}


def is_valid_url(url: str) -> bool:
    """Protection : uniquement http(s) public, pas d'IP locale/privée, pas d'identifiants dans l'URL."""
    url = (url or "").strip()
    if not url or len(url) > 2048 or any(c in url for c in "\r\n\t "):
        return False
    try:
        p = urlparse(url)
        host = (p.hostname or "").lower()
    except ValueError:
        return False
    if p.scheme not in ("http", "https") or not host or p.username or p.password:
        return False
    if host in _BLOCKED_HOSTS or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)
    except ValueError:
        return "." in host


_EXTRACTORS = None


def is_supported(url: str) -> bool:
    """Le lien correspond à une source prise en charge par le moteur (hors extracteur générique)."""
    global _EXTRACTORS
    if not is_valid_url(url):
        return False
    if _EXTRACTORS is None:
        _EXTRACTORS = [ie for ie in yt_dlp.extractor.gen_extractor_classes() if ie.IE_NAME != "generic"]
    return any(ie.suitable(url) for ie in _EXTRACTORS)


def human_size(n: float | None) -> str:
    if not n:
        return "—"
    for unit in ("o", "Ko", "Mo", "Go"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "o" else f"{int(n)} o"
        n /= 1024
    return f"{n:.2f} To"


def human_duration(sec) -> str:
    if not sec:
        return "—"
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@dataclass
class Quality:
    height: int
    fps: float | None
    vcodec: str
    size: int | None  # vidéo + meilleur audio

    @property
    def label(self) -> str:
        fps = f" {int(self.fps)} fps" if self.fps else ""
        return f"{self.height}p{fps} — {human_size(self.size)}"


@dataclass
class VideoInfo:
    url: str
    title: str
    duration: float | None
    thumbnail: str | None
    uploader: str
    source: str
    qualities: list[Quality] = field(default_factory=list)
    audio_size: int | None = None
    raw_id: str = ""

    @property
    def best(self) -> Quality | None:
        return self.qualities[0] if self.qualities else None


def _fsize(f, duration):
    s = f.get("filesize") or f.get("filesize_approx")
    if not s and f.get("tbr") and duration:
        s = f["tbr"] * 1000 / 8 * duration
    return int(s) if s else None


def parse_info(info: dict, url: str) -> VideoInfo:
    duration = info.get("duration")
    formats = info.get("formats") or []
    audios = [f for f in formats if f.get("vcodec") in (None, "none") and f.get("acodec") not in (None, "none")]
    best_audio = max(audios, key=lambda f: f.get("abr") or f.get("tbr") or 0, default=None)
    audio_size = _fsize(best_audio, duration) if best_audio else None

    by_height: dict[int, Quality] = {}
    for f in formats:
        h = f.get("height")
        if not h or f.get("vcodec") in (None, "none"):
            continue
        size = _fsize(f, duration)
        if size and f.get("acodec") in (None, "none") and audio_size:
            size += audio_size
        q = Quality(h, f.get("fps"), (f.get("vcodec") or "").split(".")[0], size)
        cur = by_height.get(h)
        if cur is None or (q.fps or 0) > (cur.fps or 0) or ((q.size or 0) > (cur.size or 0) and (q.fps or 0) == (cur.fps or 0)):
            by_height[h] = q
    if not by_height and info.get("height"):
        by_height[info["height"]] = Quality(info["height"], info.get("fps"), info.get("vcodec") or "", _fsize(info, duration))

    return VideoInfo(
        url=url,
        title=info.get("title") or "Sans titre",
        duration=duration,
        thumbnail=info.get("thumbnail"),
        uploader=info.get("uploader") or info.get("channel") or "",
        source=info.get("extractor_key") or "Web",
        qualities=sorted(by_height.values(), key=lambda q: q.height, reverse=True),
        audio_size=audio_size,
        raw_id=info.get("id", ""),
    )


def analyze(url: str) -> VideoInfo:
    if not is_valid_url(url):
        raise ValueError("invalid_url")
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    return parse_info(info, url)
