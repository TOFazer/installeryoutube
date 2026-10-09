import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from overload.media import inspect_media


def probe_payload(video_codec="h264", *, audio_codecs=("aac",), container="mp4", pix_fmt="yuv420p", frame_rate="30000/1001"):
    if container == "mp4":
        format_name = "mov,mp4,m4a,3gp,3g2,mj2"
        tags = {"major_brand": "isom"}
        extension = ".mp4"
    elif container == "webm":
        format_name = "matroska,webm"
        tags = {}
        extension = ".webm"
    elif container == "mkv":
        format_name = "matroska,webm"
        tags = {}
        extension = ".mkv"
    else:
        format_name = "mov,mp4,m4a,3gp,3g2,mj2"
        tags = {"major_brand": "qt  "}
        extension = ".mov"

    streams = [{
        "index": 0,
        "codec_type": "video",
        "codec_name": video_codec,
        "profile": "High",
        "width": 1920,
        "height": 1080,
        "pix_fmt": pix_fmt,
        "avg_frame_rate": frame_rate,
        "r_frame_rate": frame_rate,
        "duration": "12.5",
    }]
    for index, codec in enumerate(audio_codecs, start=1):
        streams.append({"index": index, "codec_type": "audio", "codec_name": codec, "duration": "12.5"})
    return {"streams": streams, "format": {"format_name": format_name, "duration": "12.5", "tags": tags}}, extension


class MediaInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.path = Path(self.temp_dir.name) / "clip.mp4"
        self.path.write_bytes(b"not a real media file, ffprobe is mocked")

    def run_inspection(self, payload, *, filename=None, ffprobe_return=0, ffprobe_stderr="", ffmpeg_return=0, ffmpeg_stderr="", **kwargs):
        path = self.path
        if filename:
            path = Path(self.temp_dir.name) / filename
            path.write_bytes(self.path.read_bytes())
        def fake_run(command, **_options):
            if Path(command[0]).name == "ffprobe":
                return subprocess.CompletedProcess(command, ffprobe_return, json.dumps(payload), ffprobe_stderr)
            return subprocess.CompletedProcess(command, ffmpeg_return, "", ffmpeg_stderr)

        with patch("overload.media.subprocess.run", side_effect=fake_run):
            return inspect_media(
                path,
                ffprobe_path="/mock/ffprobe",
                ffmpeg_path="/mock/ffmpeg",
                **kwargs,
            )

    def test_reads_container_codecs_duration_and_rate(self):
        payload, _ = probe_payload()
        report = self.run_inspection(payload)
        self.assertEqual(report.integrity, "verified")
        self.assertEqual(report.status, "ready")
        self.assertEqual(report.container, "MP4")
        self.assertEqual(report.video_codec, "h264")
        self.assertEqual(report.audio_codecs, ["aac"])
        self.assertEqual(report.width, 1920)
        self.assertAlmostEqual(report.frame_rate, 29.97003, places=3)
        self.assertEqual(report.video_stream_count, 1)
        self.assertEqual(report.audio_stream_count, 1)

    def test_av1_is_a_compatibility_warning_not_file_corruption(self):
        payload, _ = probe_payload("av1", container="webm", audio_codecs=("opus",))
        report = self.run_inspection(payload, filename="clip.webm")
        self.assertEqual(report.integrity, "verified")
        self.assertEqual(report.compatibility["status"], "caution")
        self.assertEqual(report.status, "review")
        self.assertTrue(any(item.code == "compatibility_caution" for item in report.diagnostics))

    def test_hevc_and_vp9_are_compatibility_warnings_not_integrity_errors(self):
        hevc, _ = probe_payload("hevc", container="mp4")
        hevc_report = self.run_inspection(hevc)
        self.assertEqual(hevc_report.integrity, "verified")
        self.assertEqual(hevc_report.compatibility["status"], "caution")
        self.assertEqual(hevc_report.video_codec_label, "H.265 / HEVC")

        vp9, _ = probe_payload("vp9", container="webm", audio_codecs=("opus",))
        vp9_report = self.run_inspection(vp9, filename="clip.webm")
        self.assertEqual(vp9_report.integrity, "verified")
        self.assertEqual(vp9_report.compatibility["status"], "caution")
        self.assertEqual(vp9_report.container, "WebM")

    def test_editor_profiles_are_reported_independently(self):
        payload, _ = probe_payload("av1", container="webm", audio_codecs=("opus",))
        report = self.run_inspection(payload, target_editor="resolve")
        self.assertEqual(report.target_editor, "resolve")
        self.assertEqual(report.compatibility["editor_label"], "DaVinci Resolve")
        self.assertEqual(set(report.compatibility_by_editor), {"premiere", "resolve", "capcut"})

    def test_mkv_is_not_misreported_as_webm(self):
        payload, _ = probe_payload("vp9", container="mkv", audio_codecs=("opus",))
        report = self.run_inspection(payload, filename="clip.mkv")
        self.assertEqual(report.container, "MKV")

    def test_high_resolution_and_high_frame_rate_are_preserved_in_report(self):
        payload, _ = probe_payload()
        payload["streams"][0]["width"] = 3840
        payload["streams"][0]["height"] = 2160
        payload["streams"][0]["avg_frame_rate"] = "120/1"
        report = self.run_inspection(payload)
        self.assertEqual((report.width, report.height), (3840, 2160))
        self.assertEqual(report.frame_rate, 120.0)

    def test_no_audio_track_is_valid(self):
        payload, _ = probe_payload(audio_codecs=())
        report = self.run_inspection(payload)
        self.assertEqual(report.integrity, "verified")
        self.assertEqual(report.audio_stream_count, 0)
        self.assertEqual(report.compatibility["status"], "compatible")

    def test_unidentified_audio_stream_triggers_compatibility_warning(self):
        payload, _ = probe_payload()
        payload["streams"][1].pop("codec_name")
        report = self.run_inspection(payload)
        self.assertEqual(report.integrity, "verified")
        self.assertEqual(report.audio_stream_count, 1)
        self.assertEqual(report.audio_codecs, [])
        self.assertEqual(report.compatibility["status"], "caution")

    def test_data_only_container_is_not_declared_a_valid_media_file(self):
        payload = {"streams": [{"codec_type": "data", "codec_name": "bin_data"}], "format": {"format_name": "mov,mp4"}}
        report = self.run_inspection(payload)
        self.assertEqual(report.integrity, "not_media")
        self.assertEqual(report.status, "invalid")

    def test_multiple_audio_tracks_are_reported(self):
        payload, _ = probe_payload(audio_codecs=("aac", "ac3"))
        report = self.run_inspection(payload)
        self.assertEqual(report.audio_stream_count, 2)
        self.assertEqual(report.audio_codecs, ["aac", "ac3"])
        self.assertEqual(report.compatibility["status"], "caution")

    def test_expected_size_mismatch_is_incomplete_even_if_header_is_readable(self):
        payload, _ = probe_payload()
        report = self.run_inspection(payload, expected_size=self.path.stat().st_size + 100)
        self.assertEqual(report.integrity, "incomplete")
        self.assertEqual(report.status, "invalid")
        self.assertEqual(report.validation_level, "probe")
        self.assertTrue(any(item.code == "size_mismatch" for item in report.diagnostics))

    def test_decode_failure_is_distinguished_from_codec_warning(self):
        payload, _ = probe_payload()
        report = self.run_inspection(payload, ffmpeg_return=1, ffmpeg_stderr="corrupt packet at end of file")
        self.assertEqual(report.integrity, "corrupt")
        self.assertEqual(report.status, "invalid")
        self.assertTrue(any(item.code == "decode_failed" for item in report.diagnostics))

    def test_ffprobe_error_marks_file_as_corrupt(self):
        report = self.run_inspection({}, ffprobe_return=1, ffprobe_stderr="moov atom not found")
        self.assertEqual(report.integrity, "corrupt")
        self.assertTrue(any(item.code == "incomplete_or_truncated" for item in report.diagnostics))

    def test_no_probe_binary_never_claims_file_is_ready(self):
        with patch("overload.media.find_media_tool", return_value=None):
            report = inspect_media(self.path, deep_verify=True)
        self.assertEqual(report.integrity, "unverified")
        self.assertEqual(report.status, "unverified")
        self.assertEqual(report.compatibility["status"], "unknown")

    def test_expected_size_greater_than_received_is_reported_in_human_readable_units(self):
        with patch("overload.media.find_media_tool", return_value=None):
            report = inspect_media(self.path, expected_size=self.path.stat().st_size + 1024)
        self.assertEqual(report.integrity, "incomplete")
        mismatch = next(item for item in report.diagnostics if item.code == "size_mismatch")
        self.assertIn("octets reçus", mismatch.message)


if __name__ == "__main__":
    unittest.main()
