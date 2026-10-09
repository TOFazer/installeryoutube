"""Vérification des mises à jour via les Releases GitHub officielles du projet."""
import json
import urllib.request

from version import REPO, __version__


def parse(v: str) -> tuple:
    v = v.strip().lstrip("vV")
    out = []
    for p in v.split("."):
        num = "".join(c for c in p if c.isdigit())
        out.append(int(num) if num else 0)
    return tuple(out)


def is_newer(remote: str, local: str = __version__) -> bool:
    return parse(remote) > parse(local)


def check_latest(timeout=8):
    """Retourne (version, url) si une nouvelle version existe, sinon None."""
    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "OverLoad"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    tag = data.get("tag_name", "")
    if tag and is_newer(tag):
        return tag, data.get("html_url", f"https://github.com/{REPO}/releases")
    return None
