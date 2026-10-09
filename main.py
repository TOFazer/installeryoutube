"""OverLoad — point d'entrée."""
import sys

from PySide6.QtWidgets import QApplication

from core.queue_manager import QueueManager
from services.history import History
from services.i18n import set_language
from services.settings import Settings
from version import APP_NAME


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    settings = Settings()
    set_language(settings.get("language"))
    history = History()
    queue = QueueManager(settings, history)

    from ui.main_window import MainWindow
    win = MainWindow(settings, history, queue)
    win.show()
    restored = queue.restore()
    if restored:
        win.toast.show_msg(f"↻ {restored} téléchargement(s) repris")
    if settings.get("check_updates"):
        win.settings_page.check_updates(silent=True)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
