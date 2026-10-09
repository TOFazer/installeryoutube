"""Optional H.264/AAC conversion jobs with progress and safe cancellation."""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .media import inspect_media
from .projects import ProjectStore, utc_now


class ConversionError(RuntimeError):
    pass


def _audio_info(analysis: dict[str, Any]) -> tuple[bool, bool]:
    codecs = [str(codec).lower() for codec in analysis.get("audio_codecs", [])]
    try:
        reported_count = max(0, int(analysis.get("audio_stream_count", 0)))
    except (TypeError, ValueError, OverflowError):
        reported_count = 0
    has_audio = reported_count > 0 or bool(codecs)
    complete_codec_list = not reported_count or reported_count == len(codecs)
    audio_is_aac = not has_audio or (complete_codec_list and bool(codecs) and all(codec == "aac" for codec in codecs))
    return has_audio, audio_is_aac


def _is_copy_compatible(analysis: dict[str, Any]) -> bool:
    video_codec = str(analysis.get("video_codec") or "").lower()
    pix_fmt = analysis.get("pix_fmt")
    profile = str(analysis.get("profile") or "").lower()
    _has_audio, audio_is_aac = _audio_info(analysis)
    ten_bit = any(marker in profile for marker in ("10", "high 4"))
    return (
        video_codec == "h264"
        and pix_fmt in {"yuv420p", "yuvj420p"}
        and not ten_bit
        and audio_is_aac
    )


def build_conversion_command(
    ffmpeg_path: str,
    source: str | Path,
    destination: str | Path,
    analysis: dict[str, Any],
) -> tuple[list[str], str]:
    """Build the optional compatibility profile without changing size or frame rate.

    There is intentionally no ``-s`` or ``-r`` option: FFmpeg retains the source
    dimensions and timestamps. Stream copy is selected only when all streams fit
    the MP4 H.264/AAC target; otherwise the affected media is encoded.
    """
    source = Path(source).resolve()
    destination = Path(destination).resolve()
    if source == destination:
        raise ConversionError("Le fichier source et le fichier de sortie doivent être différents.")
    if analysis.get("media_type") != "video" or not analysis.get("video_codec"):
        raise ConversionError("Le profil MP4 H.264/AAC est réservé aux fichiers vidéo.")

    copy_streams = _is_copy_compatible(analysis)
    video_copy = (
        str(analysis.get("video_codec", "")).lower() == "h264"
        and analysis.get("pix_fmt") in {"yuv420p", "yuvj420p"}
        and not any(marker in str(analysis.get("profile") or "").lower() for marker in ("10", "high 4"))
    )
    audio_codecs = [str(codec).lower() for codec in analysis.get("audio_codecs", [])]
    has_audio, audio_is_aac = _audio_info(analysis)

    command = [
        ffmpeg_path, "-nostdin", "-hide_banner", "-n", "-progress", "pipe:1",
        "-loglevel", "error", "-i", str(source), "-map", "0:v:0",
    ]
    if has_audio:
        command.extend(["-map", "0:a?"])
    else:
        command.append("-an")
    command.extend(["-map_metadata", "0"])

    if video_copy:
        command.extend(["-c:v", "copy"])
    else:
        command.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"])

    if has_audio:
        if audio_is_aac:
            command.extend(["-c:a", "copy"])
        else:
            command.extend(["-c:a", "aac", "-b:a", "192k"])
    command.extend(["-movflags", "+faststart", str(destination)])

    if copy_streams:
        mode = "Sans réencodage — flux compatibles copiés"
    elif video_copy and has_audio:
        mode = "Vidéo copiée, audio converti en AAC"
    elif video_copy:
        mode = "Vidéo copiée · sans audio"
    elif not has_audio:
        mode = "Vidéo réencodée en H.264 · sans audio"
    elif audio_is_aac:
        mode = "Vidéo réencodée en H.264, audio AAC copié"
    else:
        mode = "Réencodage H.264 / AAC"
    return command, mode


def _parse_timecode(value: str) -> float | None:
    match = re.match(r"^(\d+):(\d{2}):(\d{2})(?:\.(\d+))?$", value.strip())
    if not match:
        return None
    hours, minutes, seconds = (int(match.group(i)) for i in (1, 2, 3))
    fraction = float(f"0.{match.group(4)}") if match.group(4) else 0.0
    return hours * 3600 + minutes * 60 + seconds + fraction


@dataclass
class ConversionJob:
    id: str
    project_id: str
    source_path: Path
    source_name: str
    source_relative_path: str
    output_path: Path
    output_relative_path: str
    temporary_path: Path
    analysis: dict[str, Any]
    duration_seconds: float | None
    mode: str = "Préparation"
    status: str = "queued"
    progress: float = 0.0
    current_seconds: float = 0.0
    speed: float | None = None
    eta_seconds: float | None = None
    error: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)
    process: subprocess.Popen[str] | None = field(default=None, repr=False)
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    thread: threading.Thread | None = field(default=None, repr=False)

    def public(self) -> dict[str, Any]:
        with self.lock:
            return {
                "id": self.id,
                "project_id": self.project_id,
                "source_name": self.source_name,
                "source_relative_path": self.source_relative_path,
                "output_relative_path": self.output_relative_path if self.status == "completed" else None,
                "mode": self.mode,
                "status": self.status,
                "progress": round(max(0.0, min(self.progress, 1.0)), 4),
                "current_seconds": round(self.current_seconds, 2),
                "duration_seconds": self.duration_seconds,
                "speed": self.speed,
                "eta_seconds": self.eta_seconds,
                "error": self.error,
                "created_at": self.created_at,
                "updated_at": self.updated_at,
            }


class ConversionJobManager:
    def __init__(self, store: ProjectStore, ffmpeg_path: str | None):
        self.store = store
        self.ffmpeg_path = ffmpeg_path
        self._jobs: dict[str, ConversionJob] = {}
        self._lock = threading.RLock()

    def start(self, project_id: str, relative_path: str, analysis: dict[str, Any]) -> dict[str, Any]:
        if not self.ffmpeg_path:
            raise ConversionError("FFmpeg n'est pas installé. Installe FFmpeg pour activer la conversion.")
        if analysis.get("integrity") not in {"verified", "readable"}:
            raise ConversionError("Ce fichier n'est pas assez lisible pour être converti. Relance son diagnostic d'abord.")
        if analysis.get("media_type") != "video":
            raise ConversionError("La conversion MP4 H.264/AAC est disponible pour les vidéos uniquement.")

        source = self.store.safe_asset_path(project_id, relative_path)
        project_root = self.store.project_path(project_id)
        output_dir = project_root / "Converted"
        output_dir.mkdir(parents=True, exist_ok=True)
        proposed_name = f"{source.stem}_H264-AAC.mp4"
        output_path = _reserve_output(output_dir, proposed_name)
        job_id = uuid.uuid4().hex[:12]
        temporary_path = output_dir / f".{output_path.stem}.{job_id}.partial.mp4"
        if source.resolve() == output_path.resolve() or source.resolve() == temporary_path.resolve():
            output_path.unlink(missing_ok=True)
            raise ConversionError("La conversion ne peut pas remplacer le fichier source.")

        job = ConversionJob(
            id=job_id,
            project_id=project_id,
            source_path=source,
            source_name=source.name,
            source_relative_path=source.relative_to(project_root).as_posix(),
            output_path=output_path,
            output_relative_path=output_path.relative_to(project_root).as_posix(),
            temporary_path=temporary_path,
            analysis=analysis,
            duration_seconds=_as_positive_float(analysis.get("duration_seconds")),
        )
        with self._lock:
            active_count = sum(1 for existing in self._jobs.values() if existing.status in {"queued", "running"})
            if active_count >= 2:
                output_path.unlink(missing_ok=True)
                raise ConversionError("Deux conversions sont déjà actives. Attends la fin ou annule une tâche avant d'en lancer une autre.")
            self._jobs[job_id] = job
        job.thread = threading.Thread(target=self._run, args=(job,), name=f"overload-convert-{job_id}", daemon=True)
        job.thread.start()
        return job.public()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
        return job.public() if job else None

    def list_for_project(self, project_id: str) -> list[dict[str, Any]]:
        with self._lock:
            jobs = [job for job in self._jobs.values() if job.project_id == project_id]
        return sorted((job.public() for job in jobs), key=lambda job: job.get("created_at", ""), reverse=True)

    def shutdown(self) -> None:
        with self._lock:
            active = [job for job in self._jobs.values() if job.status in {"queued", "running"}]
        for job in active:
            self.cancel(job.id)
        for job in active:
            if job.thread and job.thread.is_alive():
                job.thread.join(timeout=5)

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            return None
        with job.lock:
            if job.status in {"completed", "failed", "cancelled"}:
                return job.public()
            job.cancel_event.set()
            process = job.process
            job.updated_at = utc_now()
        if process and process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        return job.public()

    def _run(self, job: ConversionJob) -> None:
        started_at = time.monotonic()
        with job.lock:
            if job.cancel_event.is_set():
                job.status = "cancelled"
                job.updated_at = utc_now()
                self._remove_reservation(job)
                return
            job.status = "running"
            job.updated_at = utc_now()

        try:
            command, mode = build_conversion_command(
                self.ffmpeg_path or "ffmpeg", job.source_path, job.temporary_path, job.analysis,
            )
            with job.lock:
                job.mode = mode
                job.updated_at = utc_now()
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            with job.lock:
                job.process = process
                should_cancel = job.cancel_event.is_set()
            if should_cancel and process.poll() is None:
                process.terminate()

            output_tail: list[str] = []
            progress_values: dict[str, str] = {}
            stream = process.stdout
            try:
                if stream is not None:
                    while True:
                        line = stream.readline()
                        if line == "":
                            if process.poll() is not None:
                                break
                            if job.cancel_event.is_set() and process.poll() is None:
                                process.terminate()
                            else:
                                time.sleep(0.05)
                            continue
                        clean = line.strip()
                        if clean:
                            output_tail.append(clean)
                            output_tail = output_tail[-30:]
                        if "=" in clean:
                            key, value = clean.split("=", 1)
                            progress_values[key] = value
                            self._update_progress(job, progress_values, started_at)
                        if job.cancel_event.is_set() and process.poll() is None:
                            process.terminate()
            finally:
                if stream is not None:
                    stream.close()
            return_code = process.wait()
            with job.lock:
                job.process = None

            if job.cancel_event.is_set():
                job.temporary_path.unlink(missing_ok=True)
                self._remove_reservation(job)
                self._set_terminal(job, "cancelled")
                return
            if return_code != 0:
                job.temporary_path.unlink(missing_ok=True)
                self._remove_reservation(job)
                diagnostic = "\n".join(output_tail)[-1600:]
                self._set_terminal(job, "failed", diagnostic or f"FFmpeg s'est arrêté avec le code {return_code}.")
                return
            if not job.temporary_path.is_file() or job.temporary_path.stat().st_size == 0:
                self._remove_reservation(job)
                self._set_terminal(job, "failed", "FFmpeg n'a pas produit de fichier de sortie exploitable.")
                return

            os.replace(job.temporary_path, job.output_path)
            output_report = inspect_media(
                job.output_path, target_editor="premiere", deep_verify=False,
            ).to_dict()
            self.store.add_asset(job.project_id, job.output_path, output_report, role="converted")
            with job.lock:
                job.progress = 1.0
                if job.duration_seconds is not None:
                    job.current_seconds = job.duration_seconds
                job.eta_seconds = 0.0
            self._set_terminal(job, "completed")
        except Exception as exc:  # Keep a failure visible in the UI; never leave a false success.
            with job.lock:
                process = job.process
                job.process = None
            if process is not None:
                if process.poll() is None:
                    try:
                        process.terminate()
                        process.wait(timeout=3)
                    except (OSError, subprocess.TimeoutExpired):
                        try:
                            process.kill()
                            process.wait(timeout=3)
                        except (OSError, subprocess.TimeoutExpired):
                            pass
                if process.stdout is not None:
                    process.stdout.close()
            job.temporary_path.unlink(missing_ok=True)
            self._remove_reservation(job)
            self._set_terminal(job, "failed", str(exc)[:1600] or "Erreur inconnue pendant la conversion.")

    @staticmethod
    def _update_progress(job: ConversionJob, values: dict[str, str], started_at: float) -> None:
        current = _parse_timecode(values.get("out_time", ""))
        if current is None and values.get("out_time_ms"):
            try:
                # FFmpeg's out_time_ms field is expressed in microseconds.
                current = float(values["out_time_ms"]) / 1_000_000
            except (ValueError, OverflowError):
                current = None
        speed_match = re.match(r"([0-9.]+)x", values.get("speed", ""))
        speed = float(speed_match.group(1)) if speed_match else None
        with job.lock:
            if current is not None:
                job.current_seconds = max(job.current_seconds, current)
            if speed is not None and speed > 0:
                job.speed = speed
            if job.duration_seconds and job.duration_seconds > 0:
                raw_progress = job.current_seconds / job.duration_seconds
                job.progress = min(0.995, max(job.progress, raw_progress))
                if job.speed and job.speed > 0:
                    job.eta_seconds = max(0.0, (job.duration_seconds - job.current_seconds) / job.speed)
                elif job.progress > 0.001:
                    elapsed = max(0.001, time.monotonic() - started_at)
                    rate = job.current_seconds / elapsed
                    job.eta_seconds = max(0.0, (job.duration_seconds - job.current_seconds) / rate) if rate > 0 else None
            job.updated_at = utc_now()

    @staticmethod
    def _set_terminal(job: ConversionJob, status: str, error: str | None = None) -> None:
        with job.lock:
            job.status = status
            job.error = error
            job.updated_at = utc_now()
            if status == "completed":
                job.progress = 1.0
                job.eta_seconds = 0.0

    @staticmethod
    def _remove_reservation(job: ConversionJob) -> None:
        try:
            job.output_path.unlink(missing_ok=True)
        except OSError:
            pass


def _reserve_output(directory: Path, desired_name: str) -> Path:
    stem, suffix = Path(desired_name).stem, Path(desired_name).suffix
    counter = 1
    while True:
        name = desired_name if counter == 1 else f"{stem}_{counter}{suffix}"
        candidate = directory / name
        try:
            descriptor = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            return candidate
        except FileExistsError:
            counter += 1


def _as_positive_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if result > 0 else None
