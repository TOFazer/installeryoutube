"""Accueil : coller un lien, analyser, choisir format/qualité/projet, télécharger."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from core import url_analyzer as ua
from core.download_manager import DownloadTask
from core.queue_manager import resolve_dest
from services.i18n import tr
from version import SLOGAN

from .common import Worker, card, label, load_thumbnail
from .theme import icon, logo_pixmap

FORMATS = ["mp4", "original", "mp3", "wav"]


class HomePage(QScrollArea):
    toast = Signal(str)
    go_downloads = Signal()

    def __init__(self, settings, history, queue):
        super().__init__()
        self.settings, self.history, self.queue = settings, history, queue
        self.info: ua.VideoInfo | None = None
        self.setWidgetResizable(True)
        root = QWidget()
        self.setWidget(root)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(36, 30, 36, 30)
        lay.setSpacing(18)

        # --- Hero ---
        hero = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(logo_pixmap(64))
        hero.addWidget(logo)
        tbox = QVBoxLayout()
        tbox.setSpacing(0)
        tbox.addWidget(label("OverLoad", "heroTitle"))
        tbox.addWidget(label(SLOGAN, "slogan"))
        hero.addLayout(tbox)
        hero.addStretch()
        lay.addLayout(hero)

        # --- Saisie ---
        box = card()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(20, 20, 20, 20)
        row = QHBoxLayout()
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText(tr("paste_link"))
        self.input.setFixedHeight(64)
        self.input.textChanged.connect(self._on_text)
        row.addWidget(self.input, 1)
        self.btn_analyze = QPushButton(tr("analyze"))
        self.btn_analyze.setObjectName("primary")
        self.btn_analyze.setIcon(icon("search", "#ffffff"))
        self.btn_analyze.setFixedHeight(64)
        self.btn_analyze.setCursor(Qt.PointingHandCursor)
        self.btn_analyze.clicked.connect(self.analyze)
        row.addWidget(self.btn_analyze)
        bl.addLayout(row)
        self.status = label("", "small", wrap=True)
        self.status.hide()
        bl.addWidget(self.status)
        box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        lay.addWidget(box)

        # --- Aperçu ---
        self.preview = card()
        pl = QHBoxLayout(self.preview)
        pl.setContentsMargins(16, 16, 16, 16)
        pl.setSpacing(18)
        self.thumb = QLabel()
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(256, 144)
        self.thumb.setAlignment(Qt.AlignCenter)
        pl.addWidget(self.thumb, 0, Qt.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(8)
        self.title = label("", "videoTitle", wrap=True)
        self.uploader = label("", "muted")
        info.addWidget(self.title)
        info.addWidget(self.uploader)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        info.addLayout(self.chips)
        info.addStretch()
        pl.addLayout(info, 1)
        self.preview.hide()
        lay.addWidget(self.preview)

        # --- Options ---
        opts = card()
        g = QGridLayout(opts)
        g.setContentsMargins(20, 18, 20, 18)
        g.setHorizontalSpacing(14)
        self.cb_format = QComboBox()
        for f in FORMATS:
            self.cb_format.addItem(tr(f"fmt_{f}"), f)
        self.cb_format.setCurrentIndex(max(0, FORMATS.index(settings.get("default_format"))
                                           if settings.get("default_format") in FORMATS else 0))
        self.cb_format.currentIndexChanged.connect(self._fill_qualities)
        self.cb_quality = QComboBox()
        self.cb_project = QComboBox()
        for i, (t, w) in enumerate([(tr("format"), self.cb_format), (tr("quality"), self.cb_quality),
                                    (tr("project"), self.cb_project)]):
            g.addWidget(label(t, "small"), 0, i)
            g.addWidget(w, 1, i)
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_dl = QPushButton(tr("download"))
        self.btn_dl.setObjectName("primary")
        self.btn_dl.setIcon(icon("download", "#ffffff"))
        self.btn_dl.setCursor(Qt.PointingHandCursor)
        self.btn_dl.setEnabled(False)
        self.btn_dl.clicked.connect(self.download)
        g.addWidget(self.btn_dl, 1, 3)
        lay.addWidget(opts)

        # --- Atouts ---
        feats = QGridLayout()
        feats.setSpacing(12)
        for i, (ic, t, d) in enumerate([("bolt", "f_rapid", "f_rapid_d"), ("film", "f_edit", "f_edit_d"),
                                        ("layers", "f_batch", "f_batch_d"), ("folder", "f_ready", "f_ready_d")]):
            f = card("feature")
            fl = QVBoxLayout(f)
            fl.setContentsMargins(16, 14, 16, 14)
            ib = QLabel()
            ib.setPixmap(icon(ic, "#8b5cf6", 22).pixmap(22, 22))
            fl.addWidget(ib)
            fl.addWidget(label(tr(t), "featureTitle"))
            fl.addWidget(label(tr(d), "small", wrap=True))
            feats.addWidget(f, i // 2 if False else 0, i)
        lay.addLayout(feats)
        lay.addWidget(label(tr("legal"), "small"), 0, Qt.AlignCenter)
        lay.addStretch(1)

        self.refresh_projects()
        self._fill_qualities()

    # ---------- helpers ----------
    def urls(self):
        return ua.split_urls(self.input.toPlainText())

    def _on_text(self):
        urls = self.urls()
        self.btn_dl.setEnabled(bool(urls))
        self.btn_dl.setText(tr("download") if len(urls) <= 1 else f"{tr('add_queue')} ({len(urls)})")
        if self.info and (len(urls) != 1 or urls[0] != self.info.url):
            self.info = None
            self.preview.hide()
            self._fill_qualities()

    def refresh_projects(self):
        cur = self.cb_project.currentData() or self.settings.get("current_project")
        self.cb_project.blockSignals(True)
        self.cb_project.clear()
        self.cb_project.addItem(tr("no_project"), "")
        for p in self.settings.projects():
            self.cb_project.addItem(p["name"], p["name"])
        i = self.cb_project.findData(cur)
        self.cb_project.setCurrentIndex(max(i, 0))
        self.cb_project.blockSignals(False)

    def _fill_qualities(self):
        fmt = self.cb_format.currentData()
        self.cb_quality.clear()
        if fmt in ("mp3", "wav"):
            size = ua.human_size(self.info.audio_size) if self.info else ""
            self.cb_quality.addItem(f"{tr('best')} {('— ' + size) if size and size != '—' else ''}", "best")
            self.cb_quality.setEnabled(False)
            return
        self.cb_quality.setEnabled(True)
        self.cb_quality.addItem(tr("best"), "best")
        if self.info and self.info.qualities:
            for q in self.info.qualities:
                self.cb_quality.addItem(q.label, str(q.height))
        else:
            for h in (2160, 1440, 1080, 720, 480, 360):
                self.cb_quality.addItem(f"≤ {h}p", str(h))
        pref = self.settings.get("default_quality")
        if pref != "best" and self.info and self.info.qualities:
            # qualité préférée ou la plus proche en dessous
            avail = [q.height for q in self.info.qualities if q.height <= int(pref)]
            pref = str(avail[0]) if avail else "best"
        i = self.cb_quality.findData(pref)
        self.cb_quality.setCurrentIndex(max(i, 0))

    def _set_status(self, text, error=False):
        self.status.setText(text)
        self.status.setVisible(bool(text))
        self.status.setStyleSheet("color:#f87171;" if error else "")

    # ---------- actions ----------
    def analyze(self):
        urls = self.urls()
        if not urls:
            return
        url = urls[0]
        if not ua.is_valid_url(url):
            return self._set_status("❌ " + tr("invalid_url"), True)
        self._set_status(tr("analyzing"))
        self.btn_analyze.setEnabled(False)
        self._w = Worker(ua.analyze, url)
        self._w.done.connect(self._show)
        self._w.error.connect(self._err)
        self._w.start()

    def _err(self, msg):
        self.btn_analyze.setEnabled(True)
        self._set_status("❌ " + (tr("invalid_url") if msg == "invalid_url" else msg.replace("ERROR: ", "")[:200]), True)

    def _show(self, info: ua.VideoInfo):
        self.btn_analyze.setEnabled(True)
        self.info = info
        n = len(self.urls())
        self._set_status(f"✓ {info.source}" + (f"  •  +{n-1} lien(s) dans le lot" if n > 1 else ""))
        self.title.setText(info.title)
        self.uploader.setText(info.uploader)
        self.thumb.clear()
        self.thumb.setText("…")
        load_thumbnail(info.thumbnail, self.thumb, 256, 144)
        while self.chips.count():
            w = self.chips.takeAt(0).widget()
            if w:
                w.deleteLater()
        b = info.best
        chips = [f"{tr('duration')} {ua.human_duration(info.duration)}"]
        if b:
            chips += [f"{tr('resolution')} {b.height}p"]
            if b.fps:
                chips.append(f"{int(b.fps)} {tr('fps')}")
            if b.vcodec:
                chips.append(f"{tr('codec')} {b.vcodec}")
            if b.size:
                chips.append(f"≈ {ua.human_size(b.size)}")
        for c in chips:
            self.chips.addWidget(label(c, "chip"))
        self.chips.addStretch()
        self.preview.show()
        self._fill_qualities()
        ex = self.history.find_existing(info.url, self.cb_format.currentData())
        if ex:
            self._set_status("⚠ " + tr("already_dl", ex["file"]))

    def download(self):
        urls = self.urls()
        if not urls:
            return
        fmt, quality, project = self.cb_format.currentData(), self.cb_quality.currentData(), self.cb_project.currentData()
        added, skipped, invalid = 0, 0, 0
        for url in urls:
            if not ua.is_valid_url(url):
                invalid += 1
                continue
            info = self.info if self.info and self.info.url == url else None
            if self.history.find_existing(url, fmt) and len(urls) > 1:
                skipped += 1
                continue
            source = info.source if info else ""
            size = 0
            if info:
                q = next((q for q in info.qualities if str(q.height) == quality), info.best)
                size = (info.audio_size if fmt in ("mp3", "wav") else (q.size if q else 0)) or 0
            t = DownloadTask(url=url, title=info.title if info else "", fmt=fmt, quality=quality,
                             project=project, source=source, thumbnail=info.thumbnail if info else "",
                             dest=resolve_dest(self.settings, project, source), total=int(size))
            if self.queue.add(t):
                added += 1
            else:
                skipped += 1
        self.settings.set("current_project", project)
        msg = tr("added", added)
        if skipped:
            msg += f"  •  {skipped} ⚠ {tr('duplicate')}"
        if invalid:
            msg += f"  •  {invalid} ❌"
        self.toast.emit(msg)
        if added:
            self.input.clear()
            self.go_downloads.emit()
