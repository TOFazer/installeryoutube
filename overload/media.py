"""Media probing, integrity checks, and conservative editor-compatibility advice.

The probe deliberately separates file readability from editor compatibility. A file
can be perfectly healthy while using a codec/container that a particular editor or
editor version may not handle reliably.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Any

EDITOR_LABELS = {
    "premiere": "Premiere Pro",
    "resolve": "DaVinci Resolve",
    "capcut": "CapCut",
}

IMAGE_EXTENSIONS = {
    ".bmp", ".gif", ".heic", ".heif", ".jpeg", ".jpg", ".png", ".tif",
    ".tiff", ".webp",
}
AUDIO_EXTENSIONS = {".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav", ".wma"}
CONTAINER_BY_EXTENSION = {
    ".3gp": "3GP", ".avi": "AVI", ".m2ts": "MPEG-TS", ".m4a": "MP4",
    ".m4v": "MP4", ".mkv": "MKV", ".mov": "MOV", ".mp4": "MP4",
    ".mpeg": "MPEG", ".mpg": "MPEG", ".mts": "MPEG-TS", ".mxf": "MXF",
    ".ogv": "OGG", ".ts": "MPEG-TS", ".webm": "WebM", ".wmv": "WMV",
    ".aac": "AAC", ".aif": "AIFF", ".aiff": "AIFF", ".flac": "FLAC",
    ".mp3": "MP3", ".ogg": "OGG", ".opus": "OGG", ".wav": "WAV",
}
CODEC_LABELS = {
    "aac": "AAC", "ac3": "Dolby Digital / AC-3", "alac": "Apple Lossless",
    "av1": "AV1", "flac": "FLAC", "h264": "H.264 / AVC", "hevc": "H.265 / HEVC",
    "mjpeg": "Motion JPEG", "mp2": "MPEG Audio II", "mp3": "MP3",
    "mpeg1video": "MPEG-1 Video", "mpeg2video": "MPEG-2 Video", "opus": "Opus",
    "pcm_s16le": "PCM 16 bits", "pcm_s24le": "PCM 24 bits", "prores": "Apple ProRes",
    "truehd": "Dolby TrueHD", "vp8": "VP8", "vp9": "VP9", "vorbis": "Vorbis",
    "wmav2": "WMA",
}


@dataclass
class Diagnostic:
    code: str
    severity: str
    title: str
    message: str
    suggestion: str | None = None
    details: str | None = None


@dataclass
class MediaReport:
    filename: str
    size_bytes: int
    media_type: str
    container: str
    container_id: str
    integrity: str
    validation_level: str
    status: str
    target_editor: str
    compatibility: dict[str, Any]
    compatibility_by_editor: dict[str, dict[str, Any]]
    video_codec: str | None = None
    video_codec_label: str | None = None
    audio_codecs: list[str] = field(default_factory=list)
    audio_codec_labels: list[str] = field(default_factory=list)
    video_stream_count: int = 0
    audio_stream_count: int = 0
    width: int | None = None
    height: int | None = None
    frame_rate: float | None = None
    frame_rate_label: str | None = None
    duration_seconds: float | None = None
    pix_fmt: str | None = None
    profile: str | None = None
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def find_media_tool(name: str) -> str | None:
    """Find FFmpeg tools, honoring explicit environment overrides."""
    env_name = "OVERLOAD_FFPROBE" if name == "ffprobe" else "OVERLOAD_FFMPEG"
    override = os.environ.get(env_name)
    if override:
        return override if Path(override).is_file() else shutil.which(override)
    return shutil.which(name)


def _codec_label(codec: str | None) -> str | None:
    if not codec:
        return None
    return CODEC_LABELS.get(codec.lower(), codec.replace("_", " ").upper())


def _number(value: Any) -> float | None:
    if value is None or value == "N/A":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result >= 0 else None


def _rate(value: Any) -> float | None:
    if not value or value in {"N/A", "0/0"}:
        return None
    try:
        result = float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError, TypeError, OverflowError):
        return None
    return result if result > 0 else None


def _format_fps(value: float | None) -> str | None:
    if value is None:
        return None
    rounded = round(value, 2)
    return f"{rounded:g} fps"


def _guess_container(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    name = CONTAINER_BY_EXTENSION.get(ext)
    if name:
        return name, name.lower().replace(" ", "-")
    return (ext[1:].upper() if ext else "Inconnu", ext[1:].lower() if ext else "unknown")


def _container_from_probe(path: Path, fmt: dict[str, Any]) -> tuple[str, str]:
    names = {str(part).strip().lower() for part in str(fmt.get("format_name", "")).split(",") if part.strip()}
    tags = fmt.get("tags") or {}
    brand = str(tags.get("major_brand", "")).lower()
    ext = path.suffix.lower()

    if ext == ".webm" or ("webm" in names and "matroska" not in names):
        return "WebM", "webm"
    if "matroska" in names or ext == ".mkv":
        return "MKV", "matroska"
    if "mov" in names or "mp4" in names or ext in {".mp4", ".m4v", ".m4a", ".mov"}:
        if "qt" in brand or "quicktime" in brand or ext == ".mov":
            return "MOV", "mov"
        return "MP4", "mp4"
    if names:
        first = sorted(names)[0]
        mapping = {
            "avi": ("AVI", "avi"), "flv": ("FLV", "flv"), "mpeg": ("MPEG", "mpeg"),
            "mpegts": ("MPEG-TS", "mpegts"), "mxf": ("MXF", "mxf"),
            "ogg": ("OGG", "ogg"), "wav": ("WAV", "wav"), "mp3": ("MP3", "mp3"),
            "aiff": ("AIFF", "aiff"), "flac": ("FLAC", "flac"),
        }
        if first in mapping:
            return mapping[first]
        label = first.replace("_", "-").upper()
        return label, first
    return _guess_container(path)


def _editor_compatibility(
    editor: str,
    media_type: str,
    container: str,
    video_codec: str | None,
    audio_codecs: list[str],
    audio_stream_count: int,
    pix_fmt: str | None,
    profile: str | None,
    image_extension: str,
) -> dict[str, Any]:
    editor = editor if editor in EDITOR_LABELS else "premiere"
    label = EDITOR_LABELS[editor]

    def result(status: str, title: str, message: str, suggestion: str | None = None) -> dict[str, Any]:
        return {"editor": editor, "editor_label": label, "status": status, "title": title,
                "message": message, "suggestion": suggestion}

    if media_type == "image":
        if image_extension in {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff"}:
            return result("compatible", "Format image courant", "Ce format image est généralement pris en charge.")
        return result("caution", "Format image à vérifier", "La prise en charge de ce format peut dépendre de la version et du système.",
                      "Convertis l'image en PNG ou JPEG si elle ne s'importe pas correctement.")

    if media_type == "audio":
        known_audio_codecs = len(audio_codecs) == audio_stream_count
        if audio_stream_count > 0 and known_audio_codecs and all(
            codec in {"aac", "mp3", "pcm_s16le", "pcm_s24le", "alac"} or codec.startswith("pcm_")
            for codec in audio_codecs
        ):
            return result("compatible", "Format audio courant", "Le flux audio est dans un format courant pour le montage.")
        return result("caution", "Codec audio à vérifier", "La prise en charge de ce codec peut varier selon le logiciel et sa version.",
                      "Le profil de conversion OverLoad peut produire de l'AAC dans un fichier MP4.")

    if media_type != "video" or not video_codec:
        return result("unknown", "Compatibilité inconnue", "Les flux nécessaires n'ont pas pu être identifiés.")

    if video_codec == "h264" and container in {"MP4", "MOV"}:
        compatible_pixel_formats = {"yuv420p", "yuvj420p"}
        ten_bit_profile = bool(profile and any(word in profile.lower() for word in ("10", "high 10", "high 4")))
        audio_is_common = (len(audio_codecs) == audio_stream_count and all(
            codec in {"aac", "mp3"} or codec.startswith("pcm_") for codec in audio_codecs
        ))
        if pix_fmt in compatible_pixel_formats and not ten_bit_profile and audio_is_common:
            return result("compatible", "Profil courant", f"H.264 dans {container} est un profil largement utilisé en montage.")
        return result("caution", "Paramètres à vérifier", "Le H.264 est détecté, mais son profil, son échantillonnage couleur ou une piste audio peut limiter l'import.",
                      "Le profil MP4 H.264/AAC d'OverLoad normalise les paramètres sans réduire la résolution.")

    if video_codec == "prores" and container == "MOV":
        if editor in {"premiere", "resolve"}:
            audio_is_common = len(audio_codecs) == audio_stream_count and all(
                codec in {"aac", "mp3"} or codec.startswith("pcm_") for codec in audio_codecs
            )
            if audio_is_common:
                return result("compatible", "Format de post-production", "Apple ProRes dans MOV est un format courant dans les flux de post-production.")
            return result("caution", "Piste audio à vérifier", "La vidéo ProRes dans MOV est courante, mais une piste audio n'a pas été identifiée ou peut nécessiter une conversion.",
                          "Vérifie les pistes ou crée une copie MP4 H.264/AAC.")
        return result("caution", "Compatibilité à confirmer", "CapCut peut prendre en charge ce média différemment selon sa version et son système.",
                      "Utilise une copie MP4 H.264/AAC pour un échange plus universel.")

    if video_codec == "hevc":
        return result("caution", "H.265 / HEVC détecté", f"La prise en charge de HEVC par {label} varie selon la version, le système et les extensions installées.",
                      "Pour un échange plus prévisible, crée une copie MP4 H.264/AAC. L'original reste intact.")
    if video_codec == "av1":
        return result("caution", "AV1 détecté", f"La prise en charge d'AV1 par {label} dépend fortement de sa version et du système.",
                      "Le profil MP4 H.264/AAC est proposé comme copie de compatibilité, sans écraser l'original.")
    if video_codec in {"vp8", "vp9"} or container in {"WebM", "MKV"}:
        return result("caution", "Compatibilité à vérifier", f"{video_codec.upper()} dans {container} peut ne pas être pris en charge dans toutes les versions de {label}.",
                      "Crée une copie MP4 H.264/AAC si l'import échoue. Le fichier source sera conservé.")

    return result("caution", "Codec à vérifier", f"{_codec_label(video_codec)} n'est pas dans le profil courant recommandé pour {label}.",
                  "Vérifie la documentation de ta version ou crée une copie MP4 H.264/AAC.")


def _diagnostic_for_probe_error(stderr: str) -> tuple[str, str, str]:
    lower = stderr.lower()
    if any(term in lower for term in ("moov atom not found", "partial file", "truncated", "unexpected eof", "end of file")):
        return ("incomplete_or_truncated", "Fichier incomplet ou tronqué",
                "Le lecteur média n'a pas pu lire correctement le conteneur. Le fichier est peut-être incomplet ou endommagé.")
    if "invalid data found" in lower:
        return ("invalid_media_data", "Contenu média illisible",
                "FFprobe a détecté des données invalides. Le fichier peut être endommagé ou ne pas être un média pris en charge.")
    return ("ffprobe_failed", "Analyse du média impossible",
            "FFprobe n'a pas pu lire les métadonnées du fichier. Vérifie que le téléchargement est complet et que le fichier est bien un média.")


def inspect_media(
    file_path: str | Path,
    *,
    expected_size: int | None = None,
    target_editor: str = "premiere",
    deep_verify: bool = True,
    ffprobe_path: str | None = None,
    ffmpeg_path: str | None = None,
    timeout_seconds: int = 900,
) -> MediaReport:
    """Inspect a media file and, where available, decode it end-to-end with FFmpeg.

    ``verified`` means FFprobe found streams and an optional full FFmpeg decode
    completed successfully. ``readable`` means the container/streams were probed,
    but a full decode was not performed. A byte-count mismatch always prevents a
    file being labelled ready, even if FFprobe can still read its header.
    """
    path = Path(file_path)
    stat = path.stat()
    if not path.is_file():
        raise FileNotFoundError(str(path))

    size = stat.st_size
    container_guess, container_guess_id = _guess_container(path)
    target_editor = target_editor if target_editor in EDITOR_LABELS else "premiere"
    diagnostics: list[Diagnostic] = []
    size_problem: str | None = None
    if expected_size is not None and expected_size >= 0 and size != expected_size:
        size_problem = "incomplete" if size < expected_size else "size_mismatch"
        diagnostics.append(Diagnostic(
            code="size_mismatch", severity="error",
            title="La taille reçue ne correspond pas",
            message=(f"{size:,} octets reçus sur {expected_size:,} attendus.".replace(",", " ")
                     if size < expected_size else
                     f"{size:,} octets reçus, alors que {expected_size:,} étaient attendus.".replace(",", " ")),
            suggestion="Relance le téléchargement ou compare le fichier avec sa source avant de le monter.",
        ))

    if size == 0:
        integrity = "incomplete" if expected_size else "corrupt"
        diagnostics.append(Diagnostic(
            code="empty_file", severity="error", title="Fichier vide",
            message="Le fichier ne contient aucune donnée.",
            suggestion="Relance le téléchargement et vérifie l'espace disque disponible.",
        ))
        return _finish_report(path, size, "unknown", container_guess, container_guess_id,
                              integrity, "none", target_editor, None, None, None, None,
                              [], 0, 0, None, None, None, None, None, None, diagnostics)

    if ffprobe_path is None:
        ffprobe_path = find_media_tool("ffprobe")
    if not ffprobe_path:
        guessed_type = _guess_media_type(path, [], None)
        diagnostics.append(Diagnostic(
            code="ffprobe_missing", severity="warning", title="Diagnostic codec indisponible",
            message="FFprobe n'est pas installé : OverLoad ne peut pas confirmer le conteneur ni lire les flux.",
            suggestion="Installe FFmpeg (qui inclut FFprobe), puis relance l'analyse. Le fichier original est conservé.",
        ))
        if size_problem:
            integrity = size_problem
        else:
            integrity = "unverified"
        return _finish_report(path, size, guessed_type, container_guess, container_guess_id,
                              integrity, "none", target_editor, None, None, None, None,
                              [], 0, 0, None, None, None, None, None, None, diagnostics)

    try:
        result = subprocess.run(
            [ffprobe_path, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=min(max(timeout_seconds, 1), 3600), check=False,
        )
    except subprocess.TimeoutExpired:
        diagnostics.append(Diagnostic(
            code="ffprobe_timeout", severity="warning", title="Analyse interrompue",
            message="FFprobe a dépassé le délai d'analyse. Le fichier n'est pas déclaré prêt pour le montage.",
            suggestion="Réessaie l'analyse ou vérifie le fichier avec FFmpeg.",
        ))
        integrity = size_problem or "unverified"
        return _finish_report(path, size, "unknown", container_guess, container_guess_id,
                              integrity, "none", target_editor, None, None, None, None,
                              [], 0, 0, None, None, None, None, None, None, diagnostics)
    except OSError as exc:
        diagnostics.append(Diagnostic(
            code="ffprobe_unavailable", severity="warning", title="FFprobe indisponible",
            message="OverLoad n'a pas réussi à démarrer FFprobe.",
            suggestion="Vérifie le chemin de FFprobe ou réinstalle FFmpeg.", details=str(exc)[:500],
        ))
        integrity = size_problem or "unverified"
        return _finish_report(path, size, "unknown", container_guess, container_guess_id,
                              integrity, "none", target_editor, None, None, None, None,
                              [], 0, 0, None, None, None, None, None, None, diagnostics)

    try:
        probe = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        probe = {}
    streams = probe.get("streams") if isinstance(probe, dict) else []
    streams = streams if isinstance(streams, list) else []
    if result.returncode != 0 or not isinstance(probe, dict) or not streams:
        code, title, message = _diagnostic_for_probe_error(result.stderr or "")
        if not streams and result.returncode == 0:
            code, title, message = (
                "no_readable_streams", "Aucun flux audio ou vidéo lisible",
                "Le fichier a été reçu, mais aucun flux audio, vidéo ou image lisible n'a été trouvé.",
            )
        diagnostics.append(Diagnostic(
            code=code, severity="error", title=title, message=message,
            suggestion="Conserve l'original, puis retélécharge-le ou tente une réparation avec un outil adapté.",
            details=(result.stderr or "")[:700] or None,
        ))
        integrity = size_problem or ("not_media" if code == "no_readable_streams" else "corrupt")
        return _finish_report(path, size, "unknown", container_guess, container_guess_id,
                              integrity, "none", target_editor, None, None, None, None,
                              [], 0, 0, None, None, None, None, None, None, diagnostics)

    fmt = probe.get("format") if isinstance(probe.get("format"), dict) else {}
    video_streams = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "audio"]
    if not video_streams and not audio_streams:
        diagnostics.append(Diagnostic(
            code="no_readable_streams", severity="error", title="Aucun flux audio ou vidéo lisible",
            message="Le fichier a été reçu, mais aucun flux audio, vidéo ou image lisible n'a été trouvé.",
            suggestion="Conserve l'original, puis retélécharge-le ou vérifie son contenu.",
        ))
        integrity = size_problem or "not_media"
        return _finish_report(path, size, "unknown", container_guess, container_guess_id,
                              integrity, "none", target_editor, None, None, None, None,
                              [], 0, 0, None, None, None, None, None, None, diagnostics)
    image_ext = path.suffix.lower()
    media_type = _guess_media_type(path, video_streams, audio_streams)
    container, container_id = _container_from_probe(path, fmt)
    first_video = video_streams[0] if video_streams else {}
    video_codec = str(first_video.get("codec_name")) if first_video.get("codec_name") else None
    audio_codecs = [str(stream.get("codec_name")) for stream in audio_streams if stream.get("codec_name")]
    width = _positive_int(first_video.get("width"))
    height = _positive_int(first_video.get("height"))
    fps = _rate(first_video.get("avg_frame_rate")) or _rate(first_video.get("r_frame_rate"))
    duration = _number(first_video.get("duration")) or _number(fmt.get("duration"))
    if duration is None and audio_streams:
        duration = _number(audio_streams[0].get("duration"))
    pix_fmt = str(first_video.get("pix_fmt")) if first_video.get("pix_fmt") else None
    profile = str(first_video.get("profile")) if first_video.get("profile") else None

    compatibility_by_editor = {
        editor: _editor_compatibility(editor, media_type, container, video_codec, audio_codecs,
                                      len(audio_streams), pix_fmt, profile, image_ext)
        for editor in EDITOR_LABELS
    }
    compatibility = compatibility_by_editor[target_editor]
    if compatibility["status"] == "caution":
        diagnostics.append(Diagnostic(
            code="compatibility_caution", severity="warning", title=compatibility["title"],
            message=compatibility["message"], suggestion=compatibility.get("suggestion"),
        ))
    elif compatibility["status"] == "unknown":
        diagnostics.append(Diagnostic(
            code="compatibility_unknown", severity="warning", title=compatibility["title"],
            message=compatibility["message"], suggestion=compatibility.get("suggestion"),
        ))

    validation_level = "probe"
    integrity = "readable"
    if size_problem:
        integrity = size_problem
    else:
        if deep_verify and ffmpeg_path is None:
            ffmpeg_path = find_media_tool("ffmpeg")
        if deep_verify and ffmpeg_path:
            decode_cmd = [
                ffmpeg_path, "-nostdin", "-hide_banner", "-v", "error", "-xerror",
                "-i", str(path), "-map", "0:v?", "-map", "0:a?", "-f", "null", "-",
            ]
            try:
                decoded = subprocess.run(
                    decode_cmd, capture_output=True, text=True,
                    timeout=min(max(timeout_seconds, 1), 3600), check=False,
                )
                if decoded.returncode == 0:
                    integrity = "verified"
                    validation_level = "full_decode"
                elif _decoder_missing(decoded.stderr or ""):
                    diagnostics.append(Diagnostic(
                        code="decoder_unavailable", severity="warning", title="Décodage complet indisponible",
                        message="Les métadonnées sont lisibles, mais le FFmpeg installé ne peut pas décoder au moins un flux.",
                        suggestion="Vérifie les capacités de ton installation FFmpeg. Le fichier source n'a pas été modifié.",
                        details=(decoded.stderr or "")[-700:] or None,
                    ))
                else:
                    integrity = "corrupt"
                    diagnostics.append(Diagnostic(
                        code="decode_failed", severity="error", title="Échec de lecture du média",
                        message="Le conteneur est reconnu, mais un flux n'a pas pu être décodé jusqu'au bout.",
                        suggestion="Le téléchargement peut être tronqué ou le fichier endommagé. Garde l'original et retélécharge-le si possible.",
                        details=(decoded.stderr or "")[-700:] or None,
                    ))
            except subprocess.TimeoutExpired:
                diagnostics.append(Diagnostic(
                    code="decode_timeout", severity="warning", title="Vérification complète interrompue",
                    message="Les métadonnées sont lisibles, mais le contrôle intégral a dépassé le délai prévu.",
                    suggestion="Réessaie avec un délai plus long. L'intégrité complète n'est pas confirmée.",
                ))
            except OSError as exc:
                diagnostics.append(Diagnostic(
                    code="ffmpeg_unavailable", severity="warning", title="Décodage complet indisponible",
                    message="FFmpeg n'a pas pu être démarré ; seules les métadonnées ont été contrôlées.",
                    suggestion="Vérifie l'installation de FFmpeg. L'intégrité complète n'est pas confirmée.",
                    details=str(exc)[:500],
                ))
        else:
            diagnostics.append(Diagnostic(
                code="deep_check_not_run", severity="info", title="Contrôle des métadonnées terminé",
                message="Les flux sont identifiés, mais aucun décodage intégral n'a été lancé.",
                suggestion="Installe FFmpeg pour activer la vérification complète du contenu.",
            ))

    return _finish_report(
        path, size, media_type, container, container_id, integrity, validation_level,
        target_editor, compatibility, compatibility_by_editor, video_codec,
        _codec_label(video_codec), audio_codecs, len(video_streams), len(audio_streams),
        width, height, fps, duration, pix_fmt, profile, diagnostics,
    )


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if parsed > 0 else None


def _guess_media_type(path: Path, video_streams: list[dict[str, Any]], audio_streams: list[dict[str, Any]] | None = None) -> str:
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        return "image"
    if video_streams:
        return "video"
    if audio_streams:
        return "audio"
    if path.suffix.lower() in AUDIO_EXTENSIONS:
        return "audio"
    return "unknown"


def _decoder_missing(stderr: str) -> bool:
    lower = stderr.lower()
    return any(term in lower for term in ("decoder not found", "unknown decoder", "no decoder", "decoder unavailable"))


def _finish_report(
    path: Path,
    size: int,
    media_type: str,
    container: str,
    container_id: str,
    integrity: str,
    validation_level: str,
    target_editor: str,
    compatibility: dict[str, Any] | None,
    compatibility_by_editor: dict[str, dict[str, Any]] | None,
    video_codec: str | None,
    video_codec_label: str | None,
    audio_codecs: list[str] | None,
    video_stream_count: int,
    audio_stream_count: int,
    width: int | None,
    height: int | None,
    frame_rate: float | None,
    duration_seconds: float | None,
    pix_fmt: str | None,
    profile: str | None,
    diagnostics: list[Diagnostic],
) -> MediaReport:
    compatibility_by_editor = compatibility_by_editor or {
        editor: {
            "editor": editor, "editor_label": label, "status": "unknown",
            "title": "Compatibilité inconnue", "message": "Les codecs n'ont pas pu être analysés.",
            "suggestion": "Installe FFprobe puis relance le diagnostic.",
        }
        for editor, label in EDITOR_LABELS.items()
    }
    compatibility = compatibility or compatibility_by_editor.get(target_editor) or compatibility_by_editor["premiere"]
    if integrity == "verified" and compatibility.get("status") == "compatible":
        status = "ready"
    elif integrity in {"verified", "readable"}:
        status = "review"
    elif integrity == "unverified":
        status = "unverified"
    else:
        status = "invalid"
    return MediaReport(
        filename=path.name, size_bytes=size, media_type=media_type,
        container=container, container_id=container_id, integrity=integrity,
        validation_level=validation_level, status=status, target_editor=target_editor,
        compatibility=compatibility, compatibility_by_editor=compatibility_by_editor,
        video_codec=video_codec, video_codec_label=video_codec_label,
        audio_codecs=audio_codecs or [], audio_codec_labels=[_codec_label(codec) or codec for codec in (audio_codecs or [])],
        video_stream_count=video_stream_count, audio_stream_count=audio_stream_count,
        width=width, height=height, frame_rate=frame_rate,
        frame_rate_label=_format_fps(frame_rate), duration_seconds=duration_seconds,
        pix_fmt=pix_fmt, profile=profile, diagnostics=diagnostics,
    )
