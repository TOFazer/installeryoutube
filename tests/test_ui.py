"""Test de fumée de l'interface (hors écran)."""
import pytest

pytest.importorskip("PySide6.QtWidgets")


def test_main_window_builds(tmp_path):
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError as e:  # bibliothèques graphiques absentes
        pytest.skip(str(e))
    app = QApplication.instance() or QApplication([])
    from core.queue_manager import QueueManager
    from services.history import History
    from services.settings import Settings
    from ui.main_window import MainWindow
    s, h = Settings(tmp_path / "s.json"), History(tmp_path / "h.json")
    w = MainWindow(s, h, QueueManager(s, h, runner=lambda *a, **k: None, persist_path=tmp_path / "q.json"))
    for i in range(5):
        w.go(i)
    w.apply_theme("light")
    w.home.input.setPlainText("https://a.com/1\nhttps://a.com/2")
    assert "2" in w.home.btn_dl.text()
    w.close()
    app.processEvents()
