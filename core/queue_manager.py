"""File d'attente : téléchargements simultanés, doublons, reprise après fermeture."""
import os
import threading

from PySide6.QtCore import QObject, Signal

from services.paths import data_dir
from services.storage import load_json, save_json
from . import download_manager as dm


class QueueManager(QObject):
    task_added = Signal(object)
    task_updated = Signal(object)
    task_removed = Signal(str)
    task_finished = Signal(object)

    def __init__(self, settings, history, runner=None, persist_path=None):
        super().__init__()
        self.settings = settings
        self.history = history
        self.tasks: list[dm.DownloadTask] = []
        self.runner = runner or dm.run_task
        self.persist_path = persist_path or (data_dir() / "queue.json")
        self._lock = threading.Lock()
        self.task_updated.connect(self._on_updated)

    # ---------- API ----------
    def add(self, task: dm.DownloadTask) -> bool:
        if any(t.key == task.key and t.is_active for t in self.tasks):
            return False
        self.tasks.append(task)
        self.task_added.emit(task)
        self._persist()
        self.pump()
        return True

    def get(self, task_id: str):
        return next((t for t in self.tasks if t.id == task_id), None)

    def cancel(self, task_id: str):
        t = self.get(task_id)
        if not t:
            return
        if t.status == "pending":
            t.status = "cancelled"
            self.task_updated.emit(t)
        elif t.is_active:
            t.cancel_requested = True

    def retry(self, task_id: str):
        t = self.get(task_id)
        if t and t.status in ("failed", "cancelled"):
            if any(o is not t and o.key == t.key and o.is_active for o in self.tasks):
                return
            t.reset()
            self.task_updated.emit(t)
            self._persist()
            self.pump()

    def remove(self, task_id: str):
        t = self.get(task_id)
        if t and not t.is_active:
            self.tasks.remove(t)
            self.task_removed.emit(task_id)
            self._persist()

    def clear_finished(self):
        for t in [t for t in self.tasks if not t.is_active]:
            self.remove(t.id)

    def running_count(self) -> int:
        return sum(1 for t in self.tasks if t.status in ("running", "processing"))

    def total_speed(self) -> float:
        return sum(t.speed for t in self.tasks if t.status == "running")

    # ---------- Exécution ----------
    def pump(self):
        with self._lock:
            limit = max(1, int(self.settings.get("max_concurrent")))
            free = limit - self.running_count()
            for t in self.tasks:
                if free <= 0:
                    break
                if t.status == "pending":
                    t.status = "running"
                    free -= 1
                    threading.Thread(target=self._run, args=(t,), daemon=True).start()

    def _run(self, task):
        self.runner(task, self.task_updated.emit,
                    fragments=self.settings.get("fragments"),
                    speed_limit_mb=self.settings.get("speed_limit"),
                    name_template=self.settings.get("name_template"))

    def _on_updated(self, task):
        if task.status in ("done", "failed", "cancelled") and not getattr(task, "_recorded", False):
            if task.status != "cancelled":
                task._recorded = True
                size = os.path.getsize(task.file) if task.file and os.path.exists(task.file) else task.total
                self.history.add(title=task.title or task.url, url=task.url, file=task.file,
                                 status=task.status, fmt=task.fmt, project=task.project,
                                 size=size, info=task.info)
                st = dict(self.settings.get("stats"))
                if task.status == "done":
                    st["done"] += 1
                    if task.avg_speed:
                        st["bytes"] += size
                        st["seconds"] += size / task.avg_speed
                else:
                    st["failed"] += 1
                self.settings.set("stats", st)
                self.task_finished.emit(task)
            self._persist()
            self.pump()

    # ---------- Reprise ----------
    def _persist(self):
        data = [t.to_dict() for t in self.tasks if t.is_active]
        try:
            save_json(self.persist_path, data)
        except OSError:
            pass

    def restore(self) -> int:
        """Recharge les tâches interrompues (les fichiers .part sont repris)."""
        n = 0
        for d in load_json(self.persist_path, []):
            t = dm.DownloadTask.from_dict(d)
            t.reset()
            if not any(o.key == t.key for o in self.tasks):
                self.tasks.append(t)
                self.task_added.emit(t)
                n += 1
        if n:
            self.pump()
        return n


def resolve_dest(settings, project: str, source: str) -> str:
    """Dossier final : dossier du projet (ou dossier par défaut) + sous-dossier selon le classement."""
    base = settings.project_folder(project) if project else None
    base = base or settings.get("download_dir")
    org = settings.get("organize_by")
    if org == "project" and project and not settings.project_folder(project):
        base = os.path.join(base, dm._safe(project))
    if org == "source" and source:
        base = os.path.join(base, dm._safe(source))
    return base
