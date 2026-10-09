"""Fenêtre principale : barre latérale + pages."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QPushButton, QStackedWidget, QSystemTrayIcon, QVBoxLayout, QWidget)
from PySide6.QtGui import QIcon

from services.i18n import tr
from version import __version__

from .common import Toast, label
from .downloads_page import DownloadsPage
from .history_page import HistoryPage
from .home_page import HomePage
from .projects_page import ProjectsPage
from .settings_page import SettingsPage
from .theme import icon, logo_pixmap, stylesheet


class MainWindow(QMainWindow):
    def __init__(self, settings, history, queue):
        super().__init__()
        self.settings, self.history, self.queue = settings, history, queue
        self.setWindowTitle("OverLoad")
        self.setWindowIcon(QIcon(logo_pixmap(128)))
        self.resize(1180, 760)
        self.setMinimumSize(820, 560)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(220)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 20, 14, 16)
        sl.setSpacing(4)
        brand = QHBoxLayout()
        lg = QLabel()
        lg.setPixmap(logo_pixmap(34))
        brand.addWidget(lg)
        brand.addWidget(label("OverLoad", "brand"))
        brand.addStretch()
        sl.addLayout(brand)
        sl.addSpacing(18)

        self.stack = QStackedWidget()
        self.home = HomePage(settings, history, queue)
        self.downloads = DownloadsPage(queue)
        self.library = HistoryPage(settings, history)
        self.projects = ProjectsPage(settings, history)
        self.settings_page = SettingsPage(settings)
        pages = [("home", "home", self.home), ("downloads", "download", self.downloads),
                 ("projects", "folder", self.projects), ("history", "library", self.library),
                 ("settings", "settings", self.settings_page)]
        self.group = QButtonGroup(self)
        self.nav = []
        for i, (key, ic, page) in enumerate(pages):
            self.stack.addWidget(page)
            b = QPushButton(f"  {tr(key)}")
            b.setObjectName("navBtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(icon(ic, "#9a9bab"))
            b.clicked.connect(lambda _=False, i=i: self.go(i))
            self.group.addButton(b, i)
            sl.addWidget(b)
            self.nav.append(b)
        sl.addStretch()
        sl.addWidget(label(f"v{__version__}", "small"))
        root.addWidget(side)
        root.addWidget(self.stack, 1)
        self.toast = Toast(central)

        self.badge_base = tr("downloads")
        self.home.toast.connect(self.toast.show_msg)
        self.home.go_downloads.connect(lambda: self.go(1))
        self.settings_page.toast.connect(self.toast.show_msg)
        self.settings_page.theme_changed.connect(self.apply_theme)
        self.projects.changed.connect(self.home.refresh_projects)
        self.projects.changed.connect(self.library.refresh_projects)
        queue.task_finished.connect(self._finished)
        queue.task_updated.connect(self._update_badge)
        queue.task_added.connect(self._update_badge)

        self.tray = QSystemTrayIcon(QIcon(logo_pixmap(64)), self)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.apply_theme(settings.get("theme"))
        self.go(0)

    def go(self, i):
        self.stack.setCurrentIndex(i)
        self.nav[i].setChecked(True)
        if i == 3:
            self.library.refresh()
        if i == 2:
            self.projects.refresh()

    def apply_theme(self, theme):
        QApplication.instance().setStyleSheet(stylesheet(theme))

    def _update_badge(self, *_):
        n = sum(1 for t in self.queue.tasks if t.is_active)
        self.nav[1].setText(f"  {self.badge_base}" + (f"  ({n})" if n else ""))

    def _finished(self, task):
        self.library.refresh()
        if self.settings.get("notifications") and self.tray.isVisible():
            ok = task.status == "done"
            self.tray.showMessage(tr("dl_finished") if ok else tr("dl_failed"), task.title or task.url,
                                  QSystemTrayIcon.Information if ok else QSystemTrayIcon.Warning, 4000)
        self.toast.show_msg(("✅ " if task.status == "done" else "❌ ") + (task.title or task.url)[:60])

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.toast.isVisible():
            p = self.toast.parentWidget()
            self.toast.move((p.width() - self.toast.width()) // 2, p.height() - self.toast.height() - 28)
