"""Command-line entry point for the OverLoad local workbench."""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import Sequence

from . import __version__
from .media import EDITOR_LABELS, inspect_media
from .server import create_server


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="overload", description="Atelier local de préparation de médias OverLoad.")
    parser.add_argument("--version", action="version", version=f"OverLoad {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    serve = subparsers.add_parser("serve", help="Lancer l'interface locale OverLoad.")
    serve.add_argument("--host", default="127.0.0.1", help="Adresse d'écoute (par défaut : 127.0.0.1).")
    serve.add_argument("--port", type=int, default=8765, help="Port HTTP (par défaut : 8765).")
    serve.add_argument("--data-dir", type=Path, help="Dossier de données (par défaut : ~/.overload).")
    serve.add_argument("--no-browser", action="store_true", help="Ne pas ouvrir le navigateur automatiquement.")

    inspect = subparsers.add_parser("inspect", help="Analyser les flux, codecs et l'intégrité d'un média.")
    inspect.add_argument("file", type=Path)
    inspect.add_argument("--expected-size", type=int, help="Taille attendue en octets, si connue.")
    inspect.add_argument("--editor", choices=sorted(EDITOR_LABELS), default="premiere")
    inspect.add_argument("--metadata-only", action="store_true", help="Ne pas tenter le décodage intégral avec FFmpeg.")
    inspect.add_argument("--timeout", type=int, default=900, help="Délai maximum des vérifications en secondes.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if not args_list:
        args_list = ["serve"]
    parser = _build_parser()
    args = parser.parse_args(args_list)

    if args.command == "inspect":
        try:
            report = inspect_media(
                args.file,
                expected_size=args.expected_size,
                target_editor=args.editor,
                deep_verify=not args.metadata_only,
                timeout_seconds=args.timeout,
            )
        except (OSError, ValueError) as exc:
            print(f"Erreur : {exc}", file=sys.stderr)
            return 2
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0 if report.integrity in {"verified", "readable"} else 1

    if args.command == "serve":
        try:
            server = create_server(args.host, args.port, args.data_dir)
        except OSError as exc:
            print(f"Impossible de démarrer OverLoad : {exc}", file=sys.stderr)
            return 2
        host, port = server.server_address[:2]
        browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
        url = f"http://{browser_host}:{port}/"
        print(f"OverLoad {__version__} est disponible sur {url}")
        print(f"Données locales : {server.context.store.data_dir}")
        print("Arrêt : Ctrl+C")
        if server.context.ffprobe_path:
            print(f"FFprobe : {server.context.ffprobe_path}")
        else:
            print("FFprobe absent : les fichiers resteront non vérifiés jusqu'à son installation.")
        if server.context.ffmpeg_path:
            print(f"FFmpeg : {server.context.ffmpeg_path}")
        else:
            print("FFmpeg absent : analyse des codecs et conversion complète indisponibles.")
        if not args.no_browser:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nArrêt d'OverLoad…")
        finally:
            server.server_close()
        return 0

    parser.print_help()
    return 0
