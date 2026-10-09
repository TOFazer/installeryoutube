"""Benchmark reproductible d'OverLoad.

Mesure la vitesse réelle (Mo/s) d'un même lien avec différents nombres de connexions,
plusieurs fois, et produit un rapport (médiane) en Markdown + CSV. Aucun chiffre inventé :
seules les mesures faites sur ta machine sont publiées.

Usage :
    python scripts/benchmark.py URL [URL ...] --connections 1 4 8 --runs 3 --format mp4 --quality 720
"""
import argparse
import csv
import os
import platform
import shutil
import statistics
import sys
import tempfile
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import download_manager as dm  # noqa: E402
from version import __version__  # noqa: E402


def run_once(url, connections, fmt, quality):
    tmp = tempfile.mkdtemp(prefix="overload-bench-")
    t = dm.DownloadTask(url=url, fmt=fmt, quality=quality, dest=tmp)
    start = time.monotonic()
    dm.run_task(t, lambda task: None, fragments=connections)
    elapsed = time.monotonic() - start
    size = os.path.getsize(t.file) if t.status == "done" and os.path.exists(t.file) else 0
    shutil.rmtree(tmp, ignore_errors=True)
    return {"status": t.status, "error": t.error, "bytes": size, "seconds": elapsed,
            "mbps": size / elapsed / 1_048_576 if size else 0.0}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--connections", nargs="+", type=int, default=[1, 4, 8])
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--format", default="original", choices=["mp4", "original", "mp3", "wav"])
    ap.add_argument("--quality", default="best")
    ap.add_argument("--out", default="benchmark-results")
    a = ap.parse_args()

    os.makedirs(a.out, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    rows = []
    for url in a.urls:
        for c in a.connections:
            for r in range(1, a.runs + 1):
                print(f"[{c} conn.] essai {r}/{a.runs} : {url}", flush=True)
                res = run_once(url, c, a.format, a.quality)
                res.update(url=url, connections=c, run=r)
                rows.append(res)
                print(f"   -> {res['status']}  {res['mbps']:.2f} Mo/s  ({res['bytes']/1_048_576:.1f} Mo en {res['seconds']:.1f} s)")

    csv_path = os.path.join(a.out, f"bench-{stamp}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["url", "connections", "run", "status", "bytes", "seconds", "mbps", "error"])
        w.writeheader()
        w.writerows(rows)

    md = [f"# Benchmark OverLoad v{__version__}", "",
          f"- Date : {datetime.now():%Y-%m-%d %H:%M}",
          f"- Système : {platform.system()} {platform.release()} / Python {platform.python_version()}",
          f"- Format : {a.format}, qualité : {a.quality}, essais par configuration : {a.runs}", "",
          "| Lien | Connexions | Médiane Mo/s | Min | Max | Réussite |", "|---|---|---|---|---|---|"]
    for url in a.urls:
        for c in a.connections:
            sel = [x for x in rows if x["url"] == url and x["connections"] == c]
            ok = [x["mbps"] for x in sel if x["status"] == "done"]
            med = f"{statistics.median(ok):.2f}" if ok else "—"
            md.append(f"| {url} | {c} | {med} | {min(ok):.2f} | {max(ok):.2f} | {len(ok)}/{len(sel)} |" if ok
                      else f"| {url} | {c} | — | — | — | 0/{len(sel)} |")
    md += ["", "_Résultats mesurés sur cette machine. La vitesse dépend de la connexion, des serveurs et des "
           "limites imposées par la source : aucune accélération n'est garantie._"]
    md_path = os.path.join(a.out, f"bench-{stamp}.md")
    open(md_path, "w", encoding="utf-8").write("\n".join(md))
    print("\n".join(md))
    print(f"\nRapport : {md_path}\nDonnées : {csv_path}")


if __name__ == "__main__":
    main()
