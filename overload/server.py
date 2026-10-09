"""Local web interface and JSON API for the OverLoad media workbench."""

from __future__ import annotations

import json
import mimetypes
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from . import __version__
from .conversion import ConversionError, ConversionJobManager
from .integrations import editor_status, open_in_editor, open_path
from .media import EDITOR_LABELS, find_media_tool, inspect_media
from .projects import ProjectStore, reserve_unique_path, safe_filename


MAX_JSON_BYTES = 1_000_000
CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024 * 1024


class ApiError(Exception):
    def __init__(self, status: int, message: str, *, details: Any = None):
        super().__init__(message)
        self.status = status
        self.message = message
        self.details = details


class AppContext:
    def __init__(self, data_dir: str | Path | None = None):
        self.store = ProjectStore(data_dir)
        self.ffprobe_path = find_media_tool("ffprobe")
        self.ffmpeg_path = find_media_tool("ffmpeg")
        self.jobs = ConversionJobManager(self.store, self.ffmpeg_path)
        try:
            self.max_upload_bytes = max(1, int(os.environ.get("OVERLOAD_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES)))
        except ValueError:
            self.max_upload_bytes = DEFAULT_MAX_UPLOAD_BYTES


class OverloadRequestHandler(BaseHTTPRequestHandler):
    server_version = "OverLoad/0.1"
    sys_version = ""

    @property
    def context(self) -> AppContext:
        return self.server.context  # type: ignore[attr-defined]

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler method name
        path = urlsplit(self.path).path
        if path.startswith("/api/") and not self._host_allowed():
            self._send_api_error(ApiError(403, "En-tête Host refusé."))
            return
        if path == "/" or path == "/index.html":
            self._send_static("index.html")
            return
        if path in {"/app.css", "/app.js"}:
            self._send_static(path.lstrip("/"))
            return
        parts = self._parts()
        try:
            if parts == ["api", "health"]:
                self._send_json(200, self._health())
                return
            if parts == ["api", "projects"]:
                self._send_json(200, {"projects": self.context.store.list_projects()})
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "files":
                self.context.store.get_project(parts[2])
                self._send_json(200, {"assets": self.context.store.list_assets(parts[2])})
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "jobs":
                self.context.store.get_project(parts[2])
                self._send_json(200, {"jobs": self.context.jobs.list_for_project(parts[2])})
                return
            if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
                job = self.context.jobs.get(parts[2])
                if not job:
                    raise ApiError(404, "Conversion introuvable.")
                self._send_json(200, {"job": job})
                return
            raise ApiError(404, "Route introuvable.")
        except ApiError as exc:
            self._send_api_error(exc)
        except FileNotFoundError as exc:
            self._send_api_error(ApiError(404, str(exc) or "Projet introuvable."))
        except Exception as exc:  # Keep API errors readable instead of returning an HTML traceback.
            self._send_api_error(ApiError(500, "Erreur interne du service.", details=str(exc)[:500]))

    def do_POST(self) -> None:  # noqa: N802
        if not self._host_allowed():
            self._send_api_error(ApiError(403, "En-tête Host refusé."))
            return
        origin = self.headers.get("Origin")
        host = self.headers.get("Host", "")
        if origin and urlsplit(origin).netloc.lower() != host.lower():
            self._send_api_error(ApiError(403, "Requête inter-origines refusée."))
            return
        parts = self._parts()
        try:
            if parts == ["api", "projects"]:
                payload = self._read_json()
                project = self.context.store.create_project(str(payload.get("name", "")))
                self._send_json(201, {"project": project})
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "files":
                self._handle_upload(parts[2])
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "analyze":
                self._handle_analyze(parts[2])
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "convert":
                self._handle_convert(parts[2])
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "open-folder":
                self._read_json()
                project_path = self.context.store.project_path(parts[2])
                opened, message = open_path(project_path)
                self._send_json(200 if opened else 409, {"opened": opened, "message": message})
                return
            if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] in {"open-file", "open-editor"}:
                self._handle_open(parts[2], parts[3])
                return
            if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "cancel":
                self._read_json()
                job = self.context.jobs.cancel(parts[2])
                if not job:
                    raise ApiError(404, "Conversion introuvable.")
                self._send_json(200, {"job": job})
                return
            raise ApiError(404, "Route introuvable.")
        except ApiError as exc:
            self._send_api_error(exc)
        except FileNotFoundError as exc:
            self._send_api_error(ApiError(404, str(exc) or "Fichier ou projet introuvable."))
        except ValueError as exc:
            self._send_api_error(ApiError(400, str(exc)))
        except ConversionError as exc:
            self._send_api_error(ApiError(409, str(exc)))
        except Exception as exc:
            self._send_api_error(ApiError(500, "Erreur interne du service.", details=str(exc)[:500]))

    def _handle_upload(self, project_id: str) -> None:
        project_root = self.context.store.project_path(project_id)
        try:
            content_length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            content_length = -1
        if content_length < 0:
            self.close_connection = True
            raise ApiError(411, "La requête doit inclure une taille Content-Length.")
        if content_length > self.context.max_upload_bytes:
            self.close_connection = True
            raise ApiError(413, f"Le fichier dépasse la limite OverLoad de {self.context.max_upload_bytes:,} octets.")

        raw_name = unquote(self.headers.get("X-File-Name", "media"), errors="replace")
        filename = safe_filename(raw_name)
        raw_expected = self.headers.get("X-Expected-Size")
        expected_size: int | None = None
        if raw_expected is not None:
            try:
                expected_size = int(raw_expected)
            except ValueError:
                raise ApiError(400, "Taille attendue invalide.")
            if expected_size < 0 or expected_size > self.context.max_upload_bytes:
                raise ApiError(400, "Taille attendue invalide ou supérieure à la limite OverLoad.")

        incoming = project_root / ".incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        suffix = Path(filename).suffix[:20]
        temporary = incoming / f"upload-{uuid.uuid4().hex}{suffix}"
        received = 0
        try:
            with temporary.open("xb") as stream:
                while received < content_length:
                    block = self.rfile.read(min(CHUNK_SIZE, content_length - received))
                    if not block:
                        break
                    stream.write(block)
                    received += len(block)
                stream.flush()
                os.fsync(stream.fileno())
        except (ConnectionError, OSError):
            # If possible keep the partial payload for a useful size-mismatch diagnosis.
            received = temporary.stat().st_size if temporary.exists() else 0

        expected_for_probe = expected_size if expected_size is not None else content_length
        target_editor = self.headers.get("X-Target-Editor", "premiere")
        report = inspect_media(
            temporary,
            expected_size=expected_for_probe,
            target_editor=target_editor,
            deep_verify=True,
            ffprobe_path=self.context.ffprobe_path,
            ffmpeg_path=self.context.ffmpeg_path,
        )
        if report.integrity == "verified" and report.media_type in {"video", "audio", "image"}:
            folder = {
                "video": "Media/Video",
                "audio": "Media/Audio",
                "image": "Media/Images",
            }[report.media_type]
        else:
            folder = "Needs review"
        destination_dir = project_root / folder
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = reserve_unique_path(destination_dir, filename)
        stored_name = destination.name
        try:
            os.replace(temporary, destination)
        except OSError:
            destination.unlink(missing_ok=True)
            raise
        # Reflect the actual, collision-safe saved name in the report.
        report.filename = stored_name
        asset = self.context.store.add_asset(project_id, destination, report.to_dict(), role="source")
        message = _upload_message(report.integrity, report.compatibility.get("status", "unknown"))
        self._send_json(200, {
            "asset": asset,
            "message": message,
            "received_bytes": received,
            "expected_bytes": expected_for_probe,
            "ready_for_editing": report.integrity == "verified" and report.compatibility.get("status") == "compatible",
        })

    def _handle_analyze(self, project_id: str) -> None:
        payload = self._read_json()
        relative_path = str(payload.get("relative_path", ""))
        file_path = self.context.store.safe_asset_path(project_id, relative_path)
        report = inspect_media(
            file_path,
            target_editor=str(payload.get("target_editor", "premiere")),
            deep_verify=True,
            ffprobe_path=self.context.ffprobe_path,
            ffmpeg_path=self.context.ffmpeg_path,
        )
        current_asset = next((item for item in self.context.store.list_assets(project_id)
                              if item.get("relative_path") == relative_path), None)
        if current_asset and current_asset.get("role") == "converted":
            asset = self.context.store.update_asset_analysis(project_id, relative_path, report.to_dict())
        else:
            folder_by_type = {"video": "Media/Video", "audio": "Media/Audio", "image": "Media/Images"}
            destination = (folder_by_type.get(report.media_type)
                           if report.integrity == "verified" else None) or "Needs review"
            asset = self.context.store.relocate_asset(project_id, relative_path, destination, report.to_dict())
        self._send_json(200, {"asset": asset, "message": _upload_message(report.integrity, report.compatibility.get("status", "unknown"))})

    def _handle_convert(self, project_id: str) -> None:
        payload = self._read_json()
        relative_path = str(payload.get("relative_path", ""))
        file_path = self.context.store.safe_asset_path(project_id, relative_path)
        report = inspect_media(
            file_path,
            target_editor=str(payload.get("target_editor", "premiere")),
            deep_verify=False,
            ffprobe_path=self.context.ffprobe_path,
            ffmpeg_path=self.context.ffmpeg_path,
        ).to_dict()
        job = self.context.jobs.start(project_id, relative_path, report)
        self._send_json(202, {"job": job})

    def _handle_open(self, project_id: str, operation: str) -> None:
        payload = self._read_json()
        relative_path = str(payload.get("relative_path", ""))
        file_path = self.context.store.safe_asset_path(project_id, relative_path)
        asset = next((item for item in self.context.store.list_assets(project_id)
                      if item.get("relative_path") == relative_path), None)
        if not asset:
            raise ApiError(404, "Ce média n'est pas référencé dans le projet.")
        if asset.get("stale"):
            raise ApiError(409, "Le fichier a changé depuis son dernier diagnostic. Relance l'analyse avant de l'ouvrir.")
        report = (asset.get("analysis") or {})
        if report.get("integrity") not in {"verified", "readable"}:
            raise ApiError(409, "Ce fichier n'a pas passé le contrôle d'intégrité. Relance l'analyse avant de l'ouvrir dans un logiciel de montage.")
        if operation == "open-file":
            opened, message = open_path(file_path)
        else:
            editor = str(payload.get("editor", "premiere"))
            if editor not in EDITOR_LABELS:
                raise ApiError(400, "Logiciel de montage inconnu.")
            compatibility = (report.get("compatibility_by_editor") or {}).get(editor) or report.get("compatibility") or {}
            if compatibility.get("status") != "compatible" and not payload.get("confirmed"):
                raise ApiError(409, f"{compatibility.get('title', 'Compatibilité à vérifier')} : {compatibility.get('message', 'Vérifie le codec avant l’import.')}")
            opened, message = open_in_editor(editor, file_path)
        self._send_json(200 if opened else 409, {"opened": opened, "message": message})

    def _health(self) -> dict[str, Any]:
        return {
            "name": "OverLoad",
            "version": __version__,
            "ffprobe": {"available": bool(self.context.ffprobe_path), "binary": Path(self.context.ffprobe_path).name if self.context.ffprobe_path else None},
            "ffmpeg": {"available": bool(self.context.ffmpeg_path), "binary": Path(self.context.ffmpeg_path).name if self.context.ffmpeg_path else None},
            "editors": editor_status(),
            "data_dir": str(self.context.store.data_dir),
            "max_upload_bytes": self.context.max_upload_bytes,
        }

    def _host_allowed(self) -> bool:
        raw_host = self.headers.get("Host", "")
        hostname = (urlsplit(f"//{raw_host}").hostname or "").lower().rstrip(".")
        if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".e2b.app"):
            return True
        configured = [item.strip().lower() for item in os.environ.get("OVERLOAD_ALLOWED_HOSTS", "").split(",") if item.strip()]
        for pattern in configured:
            if pattern.startswith("*.") and hostname.endswith(pattern[1:]):
                return True
            if hostname == pattern.rstrip("."):
                return True
        return False

    def _parts(self) -> list[str]:
        path = urlsplit(self.path).path
        return [unquote(part) for part in path.strip("/").split("/") if part]

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0:
            raise ApiError(411, "La requête doit inclure Content-Length.")
        if length > MAX_JSON_BYTES:
            raise ApiError(413, "La requête JSON est trop volumineuse.")
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApiError(400, "Corps JSON invalide.") from exc
        if not isinstance(payload, dict):
            raise ApiError(400, "Le corps JSON doit être un objet.")
        return payload

    def _send_static(self, name: str) -> None:
        allowed = {"index.html", "app.css", "app.js"}
        if name not in allowed:
            self._send_api_error(ApiError(404, "Fichier introuvable."))
            return
        path = Path(__file__).parent / "web" / name
        try:
            content = path.read_bytes()
        except OSError:
            self._send_api_error(ApiError(404, "Interface non construite."))
            return
        content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self._security_headers()
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._security_headers()
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionError, OSError):
            pass

    def _send_api_error(self, error: ApiError) -> None:
        payload: dict[str, Any] = {"error": error.message}
        if error.details is not None:
            payload["details"] = error.details
        self._send_json(error.status, payload)

    def _security_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'")

    def log_message(self, format: str, *args: Any) -> None:
        # Use short, local-development logs; never print request bodies or file contents.
        super().log_message(format, *args)


class OverloadHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], context: AppContext):
        super().__init__(address, OverloadRequestHandler)
        self.context = context

    def server_close(self) -> None:
        self.context.jobs.shutdown()
        super().server_close()


def _upload_message(integrity: str, compatibility: str) -> str:
    if integrity == "verified" and compatibility == "compatible":
        return "Fichier reçu, lu intégralement et prêt pour le montage."
    if integrity == "verified":
        return "Intégrité vérifiée ; compatibilité du codec à contrôler avant l'import."
    if integrity == "readable":
        return "Flux détectés ; l'intégrité complète n'a pas été vérifiée."
    if integrity == "unverified":
        return "Fichier conservé, mais son intégrité n'a pas pu être vérifiée."
    if integrity == "incomplete":
        return "La taille reçue est inférieure à la taille attendue : téléchargement probablement incomplet."
    if integrity == "size_mismatch":
        return "La taille reçue diffère de la taille annoncée : contrôle requis."
    if integrity == "not_media":
        return "Aucun flux audio ou vidéo lisible n'a été détecté."
    return "Le fichier semble endommagé ou illisible. L'original a été conservé pour diagnostic."


def create_server(host: str = "127.0.0.1", port: int = 8765, data_dir: str | Path | None = None) -> OverloadHTTPServer:
    return OverloadHTTPServer((host, port), AppContext(data_dir))
