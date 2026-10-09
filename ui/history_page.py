"""Bibliothèque : recherche, date, statut, ouvrir fichier/dossier, retirer de l'historique."""
import os
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLineEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core.url_analyzer import human_duration, human_size
from services.i18n import tr

from .common import label, open_folder, open_path
from .theme import icon


class HistoryPage(QWidget):
    COLS = ("title", "project", "format", "file_size", "date", "status")

    def __init__(self, settings, history):
        super().__init__()
        self.settings, self.history = settings, history
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 30, 36, 20)
        lay.setSpacing(14)
        lay.addWidget(label(tr("history"), "pageTitle"))

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("search"))
        self.search.addAction(icon("search", "#9a9bab"), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self.refresh)
        bar.addWidget(self.search, 1)
        self.cb_project = QComboBox()
        self.cb_project.currentIndexChanged.connect(self.refresh)
        bar.addWidget(self.cb_project)
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels([tr(c) for c in self.COLS])
        self.table.verticalHeader().hide()
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, len(self.COLS)):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(lambda: self._act("file"))
        self.table.itemSelectionChanged.connect(self._sel)
        lay.addWidget(self.table, 1)

        self.details = label("", "small", wrap=True)
        lay.addWidget(self.details)
        acts = QHBoxLayout()
        self.b_file = QPushButton(tr("open_file"))
        self.b_file.setIcon(icon("play", "#9a9bab"))
        self.b_file.clicked.connect(lambda: self._act("file"))
        self.b_dir = QPushButton(tr("open_folder"))
        self.b_dir.setIcon(icon("folder", "#9a9bab"))
        self.b_dir.clicked.connect(lambda: self._act("folder"))
        self.b_rm = QPushButton(tr("remove_entry"))
        self.b_rm.setIcon(icon("trash", "#9a9bab"))
        self.b_rm.clicked.connect(lambda: self._act("remove"))
        for b in (self.b_file, self.b_dir, self.b_rm):
            acts.addWidget(b)
        acts.addStretch()
        lay.addLayout(acts)
        self.refresh_projects()
        self.refresh()

    def refresh_projects(self):
        cur = self.cb_project.currentData()
        self.cb_project.blockSignals(True)
        self.cb_project.clear()
        self.cb_project.addItem(tr("all_projects"), "")
        for p in self.settings.projects():
            self.cb_project.addItem(p["name"], p["name"])
        self.cb_project.setCurrentIndex(max(0, self.cb_project.findData(cur)))
        self.cb_project.blockSignals(False)

    def refresh(self):
        entries = self.history.search(self.search.text(), self.cb_project.currentData() or "")
        self.table.setRowCount(len(entries))
        for r, e in enumerate(entries):
            date = datetime.fromisoformat(e["date"]).strftime("%d/%m/%Y %H:%M")
            st = tr(e["status"])
            if e["status"] == "done" and e["file"] and not os.path.exists(e["file"]):
                st += " (fichier déplacé)"
            vals = [e["title"], e.get("project") or "—", e["format"].upper(), human_size(e.get("size")), date, st]
            for c, v in enumerate(vals):
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, e["id"])
                if c == 5:
                    it.setForeground(Qt.green if e["status"] == "done" else Qt.red)
                self.table.setItem(r, c, it)
        self._sel()

    def _current(self):
        items = self.table.selectedItems()
        if not items:
            return None
        eid = items[0].data(Qt.UserRole)
        return next((e for e in self.history.entries if e["id"] == eid), None)

    def _sel(self):
        e = self._current()
        for b in (self.b_file, self.b_dir, self.b_rm):
            b.setEnabled(e is not None)
        if not e:
            self.details.setText("")
            return
        i = e.get("info") or {}
        parts = [e["file"] or e["url"]]
        if i.get("resolution"):
            parts.append(i["resolution"])
        if i.get("fps"):
            parts.append(f"{i['fps']:g} fps")
        if i.get("vcodec"):
            parts.append(f"vidéo {i['vcodec']}")
        if i.get("acodec"):
            parts.append(f"audio {i['acodec']}")
        if i.get("duration"):
            parts.append(human_duration(i["duration"]))
        if i.get("sha256"):
            parts.append(f"SHA-256 {i['sha256'][:16]}…")
        self.details.setText("  •  ".join(parts))
        self.b_file.setEnabled(bool(e["file"]) and os.path.exists(e["file"]))

    def _act(self, what):
        e = self._current()
        if not e:
            return
        if what == "file" and e["file"] and os.path.exists(e["file"]):
            open_path(e["file"])
        elif what == "folder":
            open_folder(e["file"] if e["file"] and os.path.exists(e["file"]) else os.path.dirname(e["file"] or ""))
        elif what == "remove":
            self.history.remove(e["id"])  # le fichier n'est pas supprimé
            self.refresh()
