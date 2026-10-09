"""Tests du moteur : options, connexions adaptatives, file d'attente, et téléchargement réel en local."""
import functools
import http.server
import os
import subprocess
import threading
import time

import pytest
from PySide6.QtCore import QCoreApplication

from core import download_manager as dm
from core.queue_manager import QueueManager, resolve_dest
from services.history import History
from services.settings import Settings


@pytest.fixture(scope="module")
def app():
    try:
        from PySide6.QtWidgets import QApplication
        return QApplication.instance() or QApplication([])
    except ImportError:
        return QCoreApplication.instance() or QCoreApplication([])


def test_auto_fragments():
    assert dm.auto_fragments(5_000_000, 0) == 2
    assert dm.auto_fragments(500_000_000, 0) == 8
    assert dm.auto_fragments(5_000_000_000, 0) == 12
    assert dm.auto_fragments(None, 0) == 4
    assert dm.auto_fragments(1, 6) == 6
    assert dm.auto_fragments(1, 99) == 16


def test_build_options(tmp_path):
    t = dm.DownloadTask(url="u", fmt="mp4", quality="720", dest=str(tmp_path))
    o = dm.build_options(t, fragments=0, speed_limit_mb=2)
    assert "height<=720" in o["format"] and "avc1" in o["format"]
    assert o["merge_output_format"] == "mp4"
    assert o["ratelimit"] == 2 * 1024 * 1024
    assert o["continuedl"] and o["retries"] >= 5
    a = dm.build_options(dm.DownloadTask(url="u", fmt="wav", dest=str(tmp_path)))
    assert a["postprocessors"][0]["preferredcodec"] == "wav"


def test_safe_names():
    assert dm._safe('a/b:c*?"<>|') == "a_b_c______"
    assert dm._safe("...") == "media"


def test_resolve_dest(tmp_path):
    s = Settings(tmp_path / "s.json")
    s.set("download_dir", str(tmp_path / "dl"))
    s.add_project("Clip", str(tmp_path / "clip"))
    assert resolve_dest(s, "Clip", "Youtube") == str(tmp_path / "clip")
    assert resolve_dest(s, "", "Youtube") == str(tmp_path / "dl")
    s.set("organize_by", "source")
    assert resolve_dest(s, "", "Youtube") == os.path.join(str(tmp_path / "dl"), "Youtube")


def _wait(app, cond, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_queue_concurrency_dedup_retry_cancel(app, tmp_path):
    s = Settings(tmp_path / "s.json")
    s.set("max_concurrent", 2)
    h = History(tmp_path / "h.json")
    running, peak, gate = [0], [0], threading.Event()

    def runner(task, update, **kw):
        running[0] += 1
        peak[0] = max(peak[0], running[0])
        task.status = "running"
        update(task)
        while not gate.is_set() and not task.cancel_requested:
            time.sleep(0.01)
        running[0] -= 1
        if task.cancel_requested:
            task.status = "cancelled"
        elif task.url.endswith("bad"):
            task.status, task.error = "failed", "boom"
        else:
            task.status = "done"
        update(task)

    q = QueueManager(s, h, runner=runner, persist_path=tmp_path / "q.json")
    tasks = [dm.DownloadTask(url=f"https://x.com/{i}", dest=str(tmp_path)) for i in range(4)]
    tasks.append(dm.DownloadTask(url="https://x.com/bad", dest=str(tmp_path)))
    for t in tasks:
        assert q.add(t)
    assert not q.add(dm.DownloadTask(url="https://x.com/0", dest=str(tmp_path)))  # doublon
    _wait(app, lambda: q.running_count() == 2, 5)
    q.cancel(tasks[0].id)
    assert _wait(app, lambda: tasks[0].status == "cancelled", 5)
    gate.set()
    assert _wait(app, lambda: all(not t.is_active for t in tasks), 10)
    assert peak[0] <= 2
    assert tasks[4].status == "failed"
    assert _wait(app, lambda: s.get("stats")["failed"] == 1, 5)  # l'annulation ne compte pas
    gate.clear()
    q.retry(tasks[4].id)
    assert tasks[4].status in ("pending", "running")
    gate.set()
    assert _wait(app, lambda: not tasks[4].is_active, 5)
    assert _wait(app, lambda: s.get("stats")["failed"] == 2, 5)
    st = s.get("stats")
    assert st["done"] == 3 and st["failed"] == 2


def test_restore_interrupted(app, tmp_path):
    s, h = Settings(tmp_path / "s.json"), History(tmp_path / "h.json")
    q1 = QueueManager(s, h, runner=lambda t, u, **k: None, persist_path=tmp_path / "q.json")
    s.set("max_concurrent", 1)
    q1.add(dm.DownloadTask(url="https://x.com/a", dest=str(tmp_path)))
    q1.add(dm.DownloadTask(url="https://x.com/b", dest=str(tmp_path)))
    q2 = QueueManager(s, h, runner=lambda t, u, **k: None, persist_path=tmp_path / "q.json")
    assert q2.restore() == 2


@pytest.fixture(scope="module")
def local_video(tmp_path_factory):
    if not dm.FFMPEG:
        pytest.skip("ffmpeg indisponible")
    d = tmp_path_factory.mktemp("srv")
    out = d / "sample.mp4"
    subprocess.run([dm.FFMPEG, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "3", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)], check=True)
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(d))
    handler.log_message = lambda *a: None
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/sample.mp4", out
    srv.shutdown()


def test_real_download_and_integrity(local_video, tmp_path):
    url, src = local_video
    t = dm.DownloadTask(url=url, fmt="original", dest=str(tmp_path / "out"))
    updates = []
    dm.run_task(t, lambda task: updates.append(task.status), fragments=2)
    assert t.status == "done", t.error
    assert os.path.exists(t.file)
    assert os.path.getsize(t.file) == os.path.getsize(src)
    assert t.sha256 == dm.sha256(str(src))
    assert dm.verify_file(t.file) == (True, "OK")
    assert "running" in updates and updates[-1] == "done"


def test_real_download_mp3(local_video, tmp_path):
    url, _ = local_video
    t = dm.DownloadTask(url=url, fmt="mp3", dest=str(tmp_path / "a"))
    dm.run_task(t, lambda task: None)
    assert t.status == "done", t.error
    assert t.file.endswith(".mp3") and os.path.getsize(t.file) > 0


def test_corrupt_file_detected(tmp_path):
    f = tmp_path / "bad.mp4"
    f.write_bytes(b"\x00" * 2048)
    ok, _ = dm.verify_file(str(f))
    assert ok is (dm.FFMPEG is None)
    assert dm.verify_file(str(tmp_path / "nope.mp4"))[0] is False


def test_failed_download_reports_error(tmp_path):
    t = dm.DownloadTask(url="http://127.0.0.1:1/none.mp4", dest=str(tmp_path))
    dm.run_task(t, lambda task: None)
    assert t.status == "failed" and t.error
