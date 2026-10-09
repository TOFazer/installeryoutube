import sys
import tempfile
import time
import unittest
from pathlib import Path

from overload.conversion import ConversionError, ConversionJobManager, build_conversion_command
from overload.projects import ProjectStore


class ConversionCommandTests(unittest.TestCase):
    def test_compatible_h264_aac_uses_stream_copy(self):
        analysis = {
            "media_type": "video", "container": "MP4", "video_codec": "h264",
            "audio_codecs": ["aac"], "pix_fmt": "yuv420p", "profile": "High",
        }
        command, mode = build_conversion_command("ffmpeg", "/tmp/source.mp4", "/tmp/output.mp4", analysis)
        self.assertIn("copy", command)
        self.assertIn("Sans réencodage", mode)
        self.assertNotIn("libx264", command)
        self.assertNotIn("-r", command)
        self.assertNotIn("-s", command)

    def test_h264_aac_in_an_mkv_can_be_remuxed_without_video_reencoding(self):
        analysis = {
            "media_type": "video", "container": "MKV", "video_codec": "h264",
            "audio_codecs": ["aac"], "pix_fmt": "yuv420p", "profile": "High",
        }
        command, mode = build_conversion_command("ffmpeg", "/tmp/source.mkv", "/tmp/output.mp4", analysis)
        self.assertIn("-c:v", command)
        self.assertEqual(command[command.index("-c:v") + 1], "copy")
        self.assertIn("Sans réencodage", mode)

    def test_av1_is_reencoded_to_h264_and_aac_without_scaling_or_forcing_fps(self):
        analysis = {
            "media_type": "video", "container": "WebM", "video_codec": "av1",
            "audio_codecs": ["opus"], "pix_fmt": "yuv420p", "profile": "Main",
        }
        command, mode = build_conversion_command("ffmpeg", "/tmp/source.webm", "/tmp/output.mp4", analysis)
        self.assertIn("libx264", command)
        self.assertIn("aac", command)
        self.assertIn("-crf", command)
        self.assertNotIn("-r", command)
        self.assertNotIn("-s", command)
        self.assertIn("Réencodage", mode)

    def test_unknown_audio_stream_is_encoded_instead_of_silently_dropped(self):
        analysis = {
            "media_type": "video", "container": "MP4", "video_codec": "h264",
            "audio_codecs": [], "audio_stream_count": 1, "pix_fmt": "yuv420p", "profile": "High",
        }
        command, mode = build_conversion_command("ffmpeg", "/tmp/source.mp4", "/tmp/output.mp4", analysis)
        self.assertIn("0:a?", command)
        self.assertIn("aac", command)
        self.assertNotIn("-an", command)
        self.assertIn("Vidéo copiée", mode)

    def test_h264_video_can_be_copied_while_incompatible_audio_is_converted(self):
        analysis = {
            "media_type": "video", "container": "MP4", "video_codec": "h264",
            "audio_codecs": ["opus"], "pix_fmt": "yuv420p", "profile": "High",
        }
        command, mode = build_conversion_command("ffmpeg", "/tmp/source.mp4", "/tmp/output.mp4", analysis)
        self.assertIn("copy", command)
        self.assertIn("aac", command)
        self.assertIn("Vidéo copiée", mode)

    def test_conversion_cannot_target_the_original(self):
        analysis = {"media_type": "video", "video_codec": "h264"}
        with self.assertRaises(ConversionError):
            build_conversion_command("ffmpeg", "/tmp/source.mp4", "/tmp/source.mp4", analysis)


class ConversionJobTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.store = ProjectStore(self.temp_dir.name)
        self.project = self.store.create_project("Test conversion")
        self.root = self.store.project_path(self.project["id"])
        self.source = self.root / "Media/Video/clip.mp4"
        self.source.write_bytes(b"source-original")
        self.analysis = {
            "integrity": "verified", "media_type": "video", "container": "WebM",
            "video_codec": "av1", "audio_codecs": ["opus"], "pix_fmt": "yuv420p",
            "profile": "Main", "duration_seconds": 4.0,
        }
        self.store.add_asset(self.project["id"], self.source, self.analysis)
        self.fake_ffmpeg = self.root / "fake-ffmpeg"

    def make_fake_ffmpeg(self, *, sleep=False):
        if sleep is True:
            body = """import time
print('out_time=00:00:00.500000', flush=True)
print('progress=continue', flush=True)
time.sleep(30)
"""
        elif sleep == "fail":
            body = """import sys
print('encoder initialization failed', flush=True)
raise SystemExit(7)
"""
        else:
            body = """import sys
from pathlib import Path
output = Path(sys.argv[-1])
output.write_bytes(b'converted-copy')
print('out_time=00:00:02.000000', flush=True)
print('speed=2.0x', flush=True)
print('progress=end', flush=True)
"""
        self.fake_ffmpeg.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        self.fake_ffmpeg.chmod(0o755)
        return str(self.fake_ffmpeg)

    def wait_for_status(self, manager, job_id, wanted, timeout=4):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            job = manager.get(job_id)
            if job and job["status"] == wanted:
                return job
            time.sleep(0.025)
        self.fail(f"Conversion did not reach {wanted}: {manager.get(job_id)}")

    def test_success_creates_a_new_copy_and_preserves_original(self):
        manager = ConversionJobManager(self.store, self.make_fake_ffmpeg())
        result = manager.start(self.project["id"], "Media/Video/clip.mp4", self.analysis)
        final = self.wait_for_status(manager, result["id"], "completed")
        output = self.root / final["output_relative_path"]
        self.assertTrue(output.is_file())
        self.assertEqual(output.read_bytes(), b"converted-copy")
        self.assertEqual(self.source.read_bytes(), b"source-original")
        self.assertEqual(final["progress"], 1.0)
        self.assertEqual(len(self.store.list_assets(self.project["id"])), 2)

    def test_cancellation_stops_job_and_keeps_source(self):
        manager = ConversionJobManager(self.store, self.make_fake_ffmpeg(sleep=True))
        result = manager.start(self.project["id"], "Media/Video/clip.mp4", self.analysis)
        end = time.monotonic() + 2
        while time.monotonic() < end and manager.get(result["id"])["status"] == "queued":
            time.sleep(0.01)
        manager.cancel(result["id"])
        final = self.wait_for_status(manager, result["id"], "cancelled", timeout=4)
        self.assertEqual(final["status"], "cancelled")
        self.assertEqual(self.source.read_bytes(), b"source-original")
        self.assertFalse((self.root / "Converted" / "clip_H264-AAC.mp4").exists())

    def test_ffmpeg_failure_is_visible_and_preserves_source(self):
        manager = ConversionJobManager(self.store, self.make_fake_ffmpeg(sleep="fail"))
        result = manager.start(self.project["id"], "Media/Video/clip.mp4", self.analysis)
        final = self.wait_for_status(manager, result["id"], "failed")
        self.assertIn("encoder initialization failed", final["error"])
        self.assertEqual(self.source.read_bytes(), b"source-original")
        self.assertFalse(list((self.root / "Converted").glob("*.mp4")))

    def test_output_name_is_unique_and_never_overwrites_a_previous_conversion(self):
        existing = self.root / "Converted/clip_H264-AAC.mp4"
        existing.write_bytes(b"previous")
        manager = ConversionJobManager(self.store, self.make_fake_ffmpeg())
        result = manager.start(self.project["id"], "Media/Video/clip.mp4", self.analysis)
        final = self.wait_for_status(manager, result["id"], "completed")
        self.assertEqual(final["output_relative_path"], "Converted/clip_H264-AAC_2.mp4")
        self.assertEqual(existing.read_bytes(), b"previous")


if __name__ == "__main__":
    unittest.main()
