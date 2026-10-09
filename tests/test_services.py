from services.history import History
from services.settings import Settings
from services import updater


def test_settings_persist_and_projects(tmp_path):
    s = Settings(tmp_path / "s.json")
    s.set("max_concurrent", 5)
    assert s.add_project("Clip", str(tmp_path / "clip"))
    assert not s.add_project("clip", "x")  # doublon insensible à la casse
    s2 = Settings(tmp_path / "s.json")
    assert s2.get("max_concurrent") == 5
    assert s2.project_folder("Clip") == str(tmp_path / "clip")
    s2.remove_project("Clip")
    assert s2.projects() == []


def test_settings_ignores_unknown_and_corrupt(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json")
    s = Settings(p)
    assert s.get("theme") == "dark"


def test_history(tmp_path):
    f = tmp_path / "v.mp4"
    f.write_bytes(b"x")
    h = History(tmp_path / "h.json")
    e = h.add(title="Mon Clip", url="u1", file=str(f), fmt="mp4", project="P")
    h.add(title="Autre", url="u2", fmt="mp3", status="failed")
    assert [x["title"] for x in h.search("clip")] == ["Mon Clip"]
    assert len(h.search(project="P")) == 1
    assert h.find_existing("u1", "mp4")["id"] == e["id"]
    assert h.find_existing("u1", "mp3") is None
    h.remove(e["id"])
    assert f.exists()  # le fichier n'est pas supprimé
    assert len(History(tmp_path / "h.json").entries) == 1


def test_version_compare():
    assert updater.is_newer("v1.2.0", "1.1.9")
    assert updater.is_newer("2.0", "1.9.9")
    assert not updater.is_newer("v1.0.0", "1.0.0")
    assert not updater.is_newer("0.9", "1.0.0")
