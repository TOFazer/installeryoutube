"""Mode Monteur : un dossier par projet."""
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from services.i18n import tr

from .common import card, label, open_folder
from .theme import icon


class ProjectsPage(QWidget):
    changed = Signal()

    def __init__(self, settings, history):
        super().__init__()
        self.settings, self.history = settings, history
        lay = QVBoxLayout(self)
        lay.setContentsMargins(36, 30, 36, 20)
        lay.setSpacing(14)
        lay.addWidget(label(tr("projects"), "pageTitle"))
        lay.addWidget(label(tr("project_hint"), "muted", wrap=True))

        c = card()
        cl = QHBoxLayout(c)
        cl.setContentsMargins(16, 14, 16, 14)
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr("project_name"))
        self.name.returnPressed.connect(self.create)
        cl.addWidget(self.name, 1)
        b = QPushButton(tr("create"))
        b.setObjectName("primary")
        b.setIcon(icon("plus", "#ffffff"))
        b.clicked.connect(self.create)
        cl.addWidget(b)
        lay.addWidget(c)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda it: open_folder(it.data(Qt.UserRole)))
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        bo = QPushButton(tr("open_folder"))
        bo.setIcon(icon("folder", "#9a9bab"))
        bo.clicked.connect(lambda: self.list.currentItem() and open_folder(self.list.currentItem().data(Qt.UserRole)))
        bd = QPushButton(tr("delete"))
        bd.setIcon(icon("trash", "#9a9bab"))
        bd.clicked.connect(self.delete)
        row.addWidget(bo)
        row.addWidget(bd)
        row.addStretch()
        lay.addLayout(row)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for p in self.settings.projects():
            n = len(self.history.search(project=p["name"]))
            it = QListWidgetItem(icon("folder", "#8b5cf6"), f"{p['name']}    —    {p['folder']}    ({n} média(s))")
            it.setData(Qt.UserRole, p["folder"])
            it.setData(Qt.UserRole + 1, p["name"])
            self.list.addItem(it)

    def create(self):
        name = self.name.text().strip()
        if not name:
            return
        base = os.path.join(self.settings.get("download_dir"), name)
        folder = QFileDialog.getExistingDirectory(self, tr("dest"), base) or base
        if self.settings.add_project(name, folder):
            os.makedirs(folder, exist_ok=True)
            self.name.clear()
            self.refresh()
            self.changed.emit()

    def delete(self):
        it = self.list.currentItem()
        if it:
            self.settings.remove_project(it.data(Qt.UserRole + 1))  # le dossier n'est pas supprimé
            self.refresh()
            self.changed.emit()
