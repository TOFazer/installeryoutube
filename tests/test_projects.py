import tempfile
import unittest
from pathlib import Path

from overload.projects import ProjectStore, safe_filename, unique_filename


class ProjectStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.store = ProjectStore(self.temp_dir.name)
        self.project = self.store.create_project("Été / Campagne 2026")
        self.root = self.store.project_path(self.project["id"])

    def test_project_creates_software_neutral_folder_layout(self):
        self.assertTrue((self.root / "Media/Video").is_dir())
        self.assertTrue((self.root / "Media/Audio").is_dir())
        self.assertTrue((self.root / "Media/Images").is_dir())
        self.assertTrue((self.root / "Converted").is_dir())
        self.assertTrue((self.root / "Exports").is_dir())
        self.assertTrue((self.root / "Needs review").is_dir())
        self.assertEqual(self.store.list_projects()[0]["name"], "Été / Campagne 2026")

    def test_safe_filename_removes_paths_and_platform_reserved_characters(self):
        self.assertEqual(safe_filename("../../take:01?.mp4"), "take01.mp4")
        self.assertEqual(safe_filename("CON.mov"), "_CON.mov")
        self.assertEqual(safe_filename("../   "), "media")

    def test_unique_filename_never_overwrites(self):
        folder = self.root / "Media/Video"
        (folder / "source.mp4").write_bytes(b"original")
        self.assertEqual(unique_filename(folder, "source.mp4"), "source_2.mp4")
        self.assertEqual((folder / "source.mp4").read_bytes(), b"original")

    def test_asset_manifest_uses_relative_paths_and_rejects_traversal(self):
        media = self.root / "Media/Video/clip.mp4"
        media.write_bytes(b"media")
        asset = self.store.add_asset(self.project["id"], media, {"integrity": "verified", "media_type": "video"})
        self.assertEqual(asset["relative_path"], "Media/Video/clip.mp4")
        self.assertEqual(self.store.safe_asset_path(self.project["id"], asset["relative_path"]), media.resolve())
        with self.assertRaises(ValueError):
            self.store.safe_asset_path(self.project["id"], "../../outside.mp4")

    def test_reclassification_moves_a_reviewed_source_without_overwriting(self):
        media = self.root / "Needs review/clip.mp4"
        media.write_bytes(b"payload")
        self.store.add_asset(self.project["id"], media, {"integrity": "unverified", "media_type": "unknown"})
        destination = self.root / "Media/Video/clip.mp4"
        destination.write_bytes(b"existing video")
        moved = self.store.relocate_asset(
            self.project["id"], "Needs review/clip.mp4", "Media/Video",
            {"integrity": "verified", "media_type": "video"},
        )
        self.assertEqual(moved["relative_path"], "Media/Video/clip_2.mp4")
        self.assertEqual(destination.read_bytes(), b"existing video")
        self.assertEqual((self.root / moved["relative_path"]).read_bytes(), b"payload")

    def test_manifest_updates_the_analysis_for_a_rechecked_file(self):
        media = self.root / "Needs review/clip.mp4"
        media.write_bytes(b"old")
        self.store.add_asset(self.project["id"], media, {"integrity": "unverified", "media_type": "unknown"})
        updated = self.store.update_asset_analysis(self.project["id"], "Needs review/clip.mp4", {"integrity": "verified", "media_type": "video"})
        self.assertEqual(updated["analysis"]["integrity"], "verified")
        self.assertEqual(self.store.list_assets(self.project["id"])[0]["media_type"], "video")


if __name__ == "__main__":
    unittest.main()
