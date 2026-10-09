"""Gestionnaire de téléchargements : file, états, vitesse, annuler/réessayer."""
from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from core.url_analyzer import human_size
from services.i18n import tr

from .common import card, fmt_eta, fmt_speed, label, load_thumbnail, open_folder, open_path
from .speed_graph import SpeedGraph
from .theme import icon

STATUS_COLORS = {"pending": "#9a9bab", "running": "#8b5cf6", "processing": "#3b82f6",
                 "done": "#22c55e", "failed": "#ef4444", "cancelled": "#9a9bab"}


class TaskRow(QFrame):
    def __init__(self, task, queue):
        super().__init__()
        self.task, self.queue = task, queue
        self.setObjectName("card")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(14)
        self.thumb = QLabel()
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(112, 63)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setPixmap(icon("film", "#8b5cf6", 22).pixmap(22, 22))
        if task.thumbnail:
            load_thumbnail(task.thumbnail, self.thumb, 112, 63)
        lay.addWidget(self.thumb)

        mid = QVBoxLayout()
        mid.setSpacing(5)
        top = QHBoxLayout()
        self.title = label("", "featureTitle")
        self.title.setMinimumWidth(80)
        top.addWidget(self.title, 1)
        self.state = QLabel()
        top.addWidget(self.state)
        mid.addLayout(top)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        mid.addWidget(self.bar)
        self.meta = label("", "small")
        mid.addWidget(self.meta)
        lay.addLayout(mid, 1)

        self.btns = {}
        for key, ic, fn in [("cancel", "x", lambda: queue.cancel(task.id)),
                            ("retry", "retry", lambda: queue.retry(task.id)),
                            ("open_file", "play", lambda: open_path(task.file)),
                            ("open_folder", "folder", lambda: open_folder(task.file or task.dest)),
                            ("remove", "trash", lambda: queue.remove(task.id))]:
            b = QPushButton()
            b.setObjectName("ghost")
            b.setIcon(icon(ic, "#9a9bab"))
            b.setToolTip(tr(key))
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            lay.addWidget(b)
            self.btns[key] = b
        self.refresh()

    def refresh(self):
        t = self.task
        self.title.setText(t.title or t.url)
        self.title.setToolTip(t.url)
        col = STATUS_COLORS.get(t.status, "#9a9bab")
        self.state.setText(f"● {tr(t.status)}")
        self.state.setStyleSheet(f"color:{col}; font-weight:600;")
        self.bar.setValue(int(t.progress * 1000))
        st = "done" if t.status == "done" else "failed" if t.status == "failed" else ""
        if self.bar.property("state") != st:
            self.bar.setProperty("state", st)
            self.bar.style().unpolish(self.bar)
            self.bar.style().polish(self.bar)
        fmt = t.fmt.upper() + ("" if t.quality == "best" or t.fmt in ("mp3", "wav") else f" ≤{t.quality}p")
        parts = [fmt]
        if t.project:
            parts.append(f"Projet : {t.project}")
        if t.status == "running":
            parts += [f"{t.progress*100:.1f}%", f"{human_size(t.downloaded)} / {human_size(t.total)}",
                      fmt_speed(t.speed), f"reste {fmt_eta(t.eta)}"]
            if t.connections:
                parts.append(f"{t.connections} connexions")
        elif t.status == "done":
            parts += [human_size(t.total), f"moy. {fmt_speed(t.avg_speed)}"]
            if t.info.get("resolution"):
                parts.append(t.info["resolution"])
            if t.sha256:
                parts.append("✓ SHA-256")
        elif t.status == "failed":
            parts.append(t.error)
        self.meta.setText("  •  ".join(parts))
        self.meta.setStyleSheet("color:#f87171;" if t.status == "failed" else "")
        active = t.is_active
        self.btns["cancel"].setVisible(active)
        self.btns["retry"].setVisible(t.status in ("failed", "cancelled"))
        self.btns["open_file"].setVisible(t.status == "done")
        self.btns["remove"].setVisible(not active)


class DownloadsPage(QWidget):
    def __init__(self, queue):
        super().__init__()
        self.queue = queue
        self.rows: dict[str, TaskRow] = {}
        self.total_samples = deque(maxlen=120)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 30, 36, 20)
        lay.setSpacing(14)

        head = QHBoxLayout()
        head.addWidget(label(tr("downloads"), "pageTitle"))
        head.addStretch()
        clear = QPushButton(tr("clear_done"))
        clear.setIcon(icon("trash", "#9a9bab"))
        clear.clicked.connect(queue.clear_finished)
        head.addWidget(clear)
        lay.addLayout(head)

        # Tableau de bord vitesse
        dash = card()
        dl = QHBoxLayout(dash)
        dl.setContentsMargins(18, 14, 18, 14)
        txt = QVBoxLayout()
        txt.addWidget(label(tr("total_speed"), "small"))
        self.speed_lbl = label("—", "videoTitle")
        txt.addWidget(self.speed_lbl)
        self.active_lbl = label("", "small")
        txt.addWidget(self.active_lbl)
        dl.addLayout(txt)
        self.graph = SpeedGraph(64)
        dl.addWidget(self.graph, 1)
        lay.addWidget(dash)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        self.list = QVBoxLayout(inner)
        self.list.setContentsMargins(0, 0, 6, 0)
        self.list.setSpacing(10)
        self.empty = label(tr("empty_queue"), "muted")
        self.empty.setAlignment(Qt.AlignCenter)
        self.list.addWidget(self.empty)
        self.list.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)

        queue.task_added.connect(self.add_row)
        queue.task_updated.connect(self.update_row)
        queue.task_removed.connect(self.remove_row)
        for t in queue.tasks:
            self.add_row(t)
        self.timer = QTimer(self, interval=1000, timeout=self._tick)
        self.timer.start()

    def add_row(self, task):
        if task.id in self.rows:
            return
        row = TaskRow(task, self.queue)
        self.rows[task.id] = row
        self.list.insertWidget(0, row)
        self.empty.hide()

    def update_row(self, task):
        r = self.rows.get(task.id)
        if r:
            r.refresh()

    def remove_row(self, task_id):
        r = self.rows.pop(task_id, None)
        if r:
            r.deleteLater()
        self.empty.setVisible(not self.rows)

    def _tick(self):
        sp = self.queue.total_speed()
        self.total_samples.append(sp)
        self.graph.set_samples(self.total_samples)
        self.speed_lbl.setText(fmt_speed(sp))
        pend = sum(1 for t in self.queue.tasks if t.status == "pending")
        self.active_lbl.setText(f"{self.queue.running_count()} {tr('active')}  •  {pend} {tr('pending').lower()}")
