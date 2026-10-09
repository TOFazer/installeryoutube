import http.client
import json
import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from overload.server import create_server


class LocalApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.server = create_server("127.0.0.1", 0, self.temp_dir.name)
        self.server.context.ffprobe_path = None
        self.server.context.ffmpeg_path = None
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.connection = http.client.HTTPConnection("127.0.0.1", self.server.server_address[1], timeout=3)
        self.addCleanup(self.connection.close)

    def request_json(self, method, path, payload=None, headers=None):
        body = json.dumps(payload).encode("utf-8") if isinstance(payload, dict) else payload
        request_headers = {"Content-Type": "application/json"} if isinstance(payload, dict) else {}
        request_headers.update(headers or {})
        self.connection.request(method, path, body=body, headers=request_headers)
        response = self.connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw.decode("utf-8")) if raw else {}

    def create_project(self):
        status, response = self.request_json("POST", "/api/projects", {"name": "API smoke"})
        self.assertEqual(status, 201)
        return response["project"]["id"]

    def test_short_upload_is_kept_for_review_and_never_marked_complete(self):
        project_id = self.create_project()
        body = b"partial media bytes"
        status, response = self.request_json("POST", f"/api/projects/{project_id}/files", body, {
            "Content-Type": "application/octet-stream",
            "X-File-Name": "clip.mp4",
            "X-Expected-Size": str(len(body) + 100),
            "X-Target-Editor": "premiere",
        })
        self.assertEqual(status, 200)
        self.assertFalse(response["ready_for_editing"])
        self.assertEqual(response["asset"]["analysis"]["integrity"], "incomplete")
        self.assertIn("inférieure", response["message"])
        self.assertTrue((self.server.context.store.project_path(project_id) / response["asset"]["relative_path"]).is_file())
        self.assertEqual(response["asset"]["relative_path"].split("/")[0], "Needs review")

    def test_without_probe_tools_upload_remains_explicitly_unverified(self):
        project_id = self.create_project()
        body = b"not a playable video"
        status, response = self.request_json("POST", f"/api/projects/{project_id}/files", body, {
            "Content-Type": "application/octet-stream",
            "X-File-Name": "clip.mp4",
            "X-Expected-Size": str(len(body)),
        })
        self.assertEqual(status, 200)
        self.assertEqual(response["asset"]["analysis"]["integrity"], "unverified")
        self.assertFalse(response["ready_for_editing"])
        self.assertIn("n'a pas pu être vérifiée", response["message"])

    def test_duplicate_upload_name_gets_a_suffix_without_replacing_first_copy(self):
        project_id = self.create_project()
        names = []
        for content in (b"first copy", b"second copy"):
            status, response = self.request_json("POST", f"/api/projects/{project_id}/files", content, {
                "Content-Type": "application/octet-stream",
                "X-File-Name": "same.mp4",
                "X-Expected-Size": str(len(content)),
            })
            self.assertEqual(status, 200)
            names.append(response["asset"]["relative_path"])
        self.assertEqual(names, ["Needs review/same.mp4", "Needs review/same_2.mp4"])
        root = self.server.context.store.project_path(project_id)
        self.assertEqual((root / names[0]).read_bytes(), b"first copy")
        self.assertEqual((root / names[1]).read_bytes(), b"second copy")

    def test_verified_media_is_sorted_into_the_project_video_folder(self):
        project_id = self.create_project()
        ffprobe = Path(self.temp_dir.name) / "ffprobe"
        ffmpeg = Path(self.temp_dir.name) / "ffmpeg"
        metadata = {
            "streams": [
                {"codec_type": "video", "codec_name": "h264", "profile": "High", "width": 1280,
                 "height": 720, "pix_fmt": "yuv420p", "avg_frame_rate": "25/1", "duration": "2"},
                {"codec_type": "audio", "codec_name": "aac", "duration": "2"},
            ],
            "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "2", "tags": {"major_brand": "isom"}},
        }
        ffprobe.write_text(f"#!{sys.executable}\nimport json\nprint(json.dumps({metadata!r}))\n", encoding="utf-8")
        ffmpeg.write_text(f"#!{sys.executable}\nraise SystemExit(0)\n", encoding="utf-8")
        ffprobe.chmod(0o755)
        ffmpeg.chmod(0o755)
        self.server.context.ffprobe_path = str(ffprobe)
        self.server.context.ffmpeg_path = str(ffmpeg)

        body = b"test video bytes"
        status, response = self.request_json("POST", f"/api/projects/{project_id}/files", body, {
            "Content-Type": "application/octet-stream",
            "X-File-Name": "clip.mp4",
            "X-Expected-Size": str(len(body)),
        })
        self.assertEqual(status, 200)
        self.assertTrue(response["ready_for_editing"])
        self.assertEqual(response["asset"]["analysis"]["integrity"], "verified")
        self.assertEqual(response["asset"]["relative_path"], "Media/Video/clip.mp4")

    def test_editor_open_is_blocked_until_codec_warning_is_acknowledged(self):
        project_id = self.create_project()
        ffprobe = Path(self.temp_dir.name) / "ffprobe-av1"
        ffmpeg = Path(self.temp_dir.name) / "ffmpeg-av1"
        metadata = {
            "streams": [
                {"codec_type": "video", "codec_name": "av1", "profile": "Main", "width": 1920,
                 "height": 1080, "pix_fmt": "yuv420p", "avg_frame_rate": "30/1", "duration": "2"},
                {"codec_type": "audio", "codec_name": "aac", "duration": "2"},
            ],
            "format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "2", "tags": {"major_brand": "isom"}},
        }
        ffprobe.write_text(f"#!{sys.executable}\nimport json\nprint(json.dumps({metadata!r}))\n", encoding="utf-8")
        ffmpeg.write_text(f"#!{sys.executable}\nraise SystemExit(0)\n", encoding="utf-8")
        ffprobe.chmod(0o755)
        ffmpeg.chmod(0o755)
        self.server.context.ffprobe_path = str(ffprobe)
        self.server.context.ffmpeg_path = str(ffmpeg)
        body = b"av1 bytes"
        status, upload = self.request_json("POST", f"/api/projects/{project_id}/files", body, {
            "Content-Type": "application/octet-stream", "X-File-Name": "av1.mp4",
            "X-Expected-Size": str(len(body)),
        })
        self.assertEqual(status, 200)
        self.assertEqual(upload["asset"]["analysis"]["integrity"], "verified")
        status, response = self.request_json("POST", f"/api/projects/{project_id}/open-editor", {
            "relative_path": upload["asset"]["relative_path"], "editor": "premiere", "confirmed": False,
        })
        self.assertEqual(status, 409)
        self.assertIn("AV1", response["error"])

    def test_preview_proxy_host_is_allowed_for_live_preview(self):
        self.connection.putrequest("GET", "/api/health", skip_host=True)
        self.connection.putheader("Host", "8765-preview-sandbox.e2b.app")
        self.connection.putheader("Origin", "https://8765-preview-sandbox.e2b.app")
        self.connection.endheaders()
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["name"], "OverLoad")

    def test_dns_rebinding_host_is_rejected_even_when_origin_matches(self):
        self.connection.putrequest("GET", "/api/projects", skip_host=True)
        self.connection.putheader("Host", "attacker.invalid")
        self.connection.putheader("Origin", "https://attacker.invalid")
        self.connection.endheaders()
        response = self.connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 403)
        self.assertIn("Host", payload["error"])

    def test_cross_origin_mutation_is_rejected(self):
        status, payload = self.request_json("POST", "/api/projects", {"name": "Cross-site"}, {
            "Origin": "https://attacker.invalid",
        })
        self.assertEqual(status, 403)
        self.assertIn("inter-origines", payload["error"])
        self.assertEqual(self.server.context.store.list_projects(), [])


if __name__ == "__main__":
    unittest.main()
