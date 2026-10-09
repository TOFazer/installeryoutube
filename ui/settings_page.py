"""Paramètres."""
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLineEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from services import updater
from services.i18n import tr
from version import __version__

from .common import Worker, card, label


class SettingsPage(QScrollArea):
    theme_changed = Signal(str)
    toast = Signal(str)

    def __init__(self, settings):
        super().__init__()
        self.s = settings
        self.setWidgetResizable(True)
        root = QWidget()
        self.setWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(36, 30, 36, 30)
        lay.setSpacing(14)
        lay.addWidget(label(tr("settings"), "pageTitle"))

        def section(title):
            c = card()
            f = QFormLayout(c)
            f.setContentsMargins(20, 16, 20, 16)
            f.setSpacing(12)
            f.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            f.addRow(label(title, "featureTitle"))
            lay.addWidget(c)
            return f

        # --- Téléchargements ---
        f = section(tr("downloads"))
        drow = QHBoxLayout()
        self.dir = QLineEdit(settings.get("download_dir"))
        self.dir.editingFinished.connect(lambda: settings.set("download_dir", self.dir.text()))
        b = QPushButton(tr("browse"))
        b.clicked.connect(self._browse)
        drow.addWidget(self.dir, 1)
        drow.addWidget(b)
        f.addRow(tr("dest"), drow)

        self.fmt = self._combo([(tr("fmt_mp4"), "mp4"), (tr("fmt_original"), "original"),
                                (tr("fmt_mp3"), "mp3"), (tr("fmt_wav"), "wav")], "default_format")
        f.addRow(tr("def_format"), self.fmt)
        self.q = self._combo([(tr("best"), "best")] + [(f"{h}p", str(h)) for h in (2160, 1440, 1080, 720, 480)],
                             "default_quality")
        f.addRow(tr("def_quality"), self.q)
        self.org = self._combo([(tr("org_project"), "project"), (tr("org_source"), "source"),
                                (tr("org_none"), "none")], "organize_by")
        f.addRow(tr("organize"), self.org)
        self.tpl = self._combo([("Titre", "%(title)s"), ("Titre [id]", "%(title)s [%(id)s]"),
                                ("Date - Titre", "%(upload_date)s - %(title)s"),
                                ("Chaîne - Titre", "%(uploader)s - %(title)s")], "name_template")
        f.addRow(tr("name_template"), self.tpl)

        # --- Performances ---
        f = section("Performances")
        self.conc = QSpinBox()
        self.conc.setRange(1, 8)
        self.conc.setValue(int(settings.get("max_concurrent")))
        self.conc.valueChanged.connect(lambda v: settings.set("max_concurrent", v))
        f.addRow(tr("concurrent"), self.conc)
        self.frag = QSpinBox()
        self.frag.setRange(0, 16)
        self.frag.setSpecialValueText("Auto")
        self.frag.setValue(int(settings.get("fragments")))
        self.frag.valueChanged.connect(lambda v: settings.set("fragments", v))
        f.addRow(tr("fragments"), self.frag)
        self.limit = QDoubleSpinBox()
        self.limit.setRange(0, 1000)
        self.limit.setSpecialValueText("∞")
        self.limit.setValue(float(settings.get("speed_limit")))
        self.limit.valueChanged.connect(lambda v: settings.set("speed_limit", v))
        f.addRow(tr("speed_limit"), self.limit)

        # --- Apparence ---
        f = section(tr("theme"))
        self.theme = self._combo([(tr("dark"), "dark"), (tr("light"), "light")], "theme",
                                 after=self.theme_changed.emit)
        f.addRow(tr("theme"), self.theme)
        self.lang = self._combo([("Français", "fr"), ("English", "en")], "language",
                                after=lambda _: self.toast.emit(tr("restart_needed")))
        f.addRow(tr("language"), self.lang)
        self.notif = QCheckBox()
        self.notif.setChecked(bool(settings.get("notifications")))
        self.notif.toggled.connect(lambda v: settings.set("notifications", v))
        f.addRow(tr("notifications"), self.notif)

        # --- À propos ---
        f = section("OverLoad")
        f.addRow(tr("version"), label(f"v{__version__}", "chip"))
        self.auto = QCheckBox()
        self.auto.setChecked(bool(settings.get("check_updates")))
        self.auto.toggled.connect(lambda v: settings.set("check_updates", v))
        f.addRow(tr("auto_updates"), self.auto)
        ub = QPushButton(tr("check_updates"))
        ub.clicked.connect(lambda: self.check_updates(silent=False))
        f.addRow("", ub)
        st = settings.get("stats")
        tot = st["done"] + st["failed"]
        rate = f"{st['done'] * 100 / tot:.0f} %" if tot else "—"
        avg = f"{st['bytes'] / st['seconds'] / 1048576:.2f} Mo/s" if st["seconds"] else "—"
        f.addRow("Fiabilité", label(f"{rate}  ({st['done']}/{tot})", "muted"))
        f.addRow("Vitesse moyenne", label(avg, "muted"))
        lay.addStretch()

    def _combo(self, items, key, after=None):
        cb = QComboBox()
        for t, v in items:
            cb.addItem(t, v)
        cb.setCurrentIndex(max(0, cb.findData(self.s.get(key))))

        def changed():
            self.s.set(key, cb.currentData())
            if after:
                after(cb.currentData())
        cb.currentIndexChanged.connect(changed)
        return cb

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, tr("dest"), self.dir.text())
        if d:
            self.dir.setText(d)
            self.s.set("download_dir", d)

    def check_updates(self, silent=True):
        self._uw = Worker(updater.check_latest)

        def done(res):
            if res:
                ver, url = res
                self.toast.emit(tr("update_available", ver))
                if not silent:
                    QDesktopServices.openUrl(QUrl(url))
            elif not silent:
                self.toast.emit(tr("up_to_date"))
        self._uw.done.connect(done)
        self._uw.error.connect(lambda _: None if silent else self.toast.emit(tr("update_error")))
        self._uw.start()
