"""Widgets et utilitaires partagés."""
import os
import subprocess
import sys
import threading
import urllib.request

from PySide6.QtCore import QObject, Qt, QTimer, Signal, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QGraphicsOpacityEffect, QVBoxLayout


def open_path(path: str):
    if not path:
        return
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def open_folder(path: str):
    if not path:
        return
    if os.path.isfile(path):
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
            return
        path = os.path.dirname(path)
    os.makedirs(path, exist_ok=True)
    open_path(path)


def fmt_speed(bps: float) -> str:
    if not bps:
        return "—"
    mb = bps / (1024 * 1024)
    return f"{mb:.2f} Mo/s" if mb >= 0.1 else f"{bps/1024:.0f} Ko/s"


def fmt_eta(sec) -> str:
    if sec is None:
        return "—"
    sec = int(sec)
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}" if h else f"{m}:{s:02d}"


class Worker(QObject):
    """Exécute une fonction dans un thread et renvoie le résultat via signal."""
    done = Signal(object)
    error = Signal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self

    def _run(self):
        try:
            self.done.emit(self.fn(*self.args))
        except Exception as e:  # noqa: BLE001
            self.error.emit(str(e))


_thumb_cache: dict[str, bytes] = {}


def load_thumbnail(url: str, label: QLabel, w: int, h: int):
    if not url:
        return

    def fetch(u):
        if u not in _thumb_cache:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
            _thumb_cache[u] = urllib.request.urlopen(req, timeout=10).read()
        return _thumb_cache[u]

    def show(data):
        pm = QPixmap()
        pm.loadFromData(data)
        if not pm.isNull():
            label.setPixmap(pm.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation).copy(0, 0, w, h))
    wk = Worker(fetch, url)
    label._worker = wk  # garde une référence
    wk.done.connect(show)
    wk.start()


def card(name="card") -> QFrame:
    f = QFrame()
    f.setObjectName(name)
    return f


def label(text="", name=None, wrap=False) -> QLabel:
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    lb.setWordWrap(wrap)
    return lb


class Toast(QFrame):
    """Petit message animé en bas de la fenêtre."""
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("toast")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.lbl = QLabel()
        lay.addWidget(self.lbl)
        self.eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.eff)
        self.anim = QPropertyAnimation(self.eff, b"opacity", self)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.finished.connect(lambda: self.eff.opacity() < 0.05 and self.hide())
        self.timer = QTimer(self, singleShot=True, timeout=self._fade)
        self.hide()

    def show_msg(self, text, ms=3000):
        self.lbl.setText(text)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 28)
        self.show()
        self.raise_()
        self.anim.stop()
        self.anim.setDuration(200)
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self.timer.start(ms)

    def _fade(self):
        self.anim.setDuration(400)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.start()
