"""Optional real-tool coverage for size, cadence, resolution, and image quality.

The suite is skipped when FFmpeg/FFprobe (or the H.264 encoder/SSIM filter) is
not installed; unit tests cover command construction without external binaries.
"""

import math
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from overload.conversion import build_conversion_command
from overload.media import find_media_tool, inspect_media


FFMPEG = find_media_tool("ffmpeg")
FFPROBE = find_media_tool("ffprobe")


@unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg et FFprobe ne sont pas installés")
class RealFfmpegCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        encoders = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], capture_output=True, text=True, check=False)
        filters = subprocess.run([FFMPEG, "-hide_banner", "-filters"], capture_output=True, text=True, check=False)
        if "libx264" not in encoders.stdout or "ssim" not in filters.stdout:
            raise unittest.SkipTest("FFmpeg doit fournir libx264 et le filtre SSIM pour ce test")

    def test_conversion_preserves_dimensions_and_fps_and_compares_size_and_ssim(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source_mpeg4.mp4"
            output = root / "compatibility_test.mp4"
            make_source = [
                FFMPEG, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25",
                "-f", "lavfi", "-i", "sine=frequency=880:sample_rate=48000",
                "-t", "2", "-c:v", "mpeg4", "-q:v", "4", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", str(source),
            ]
            created = subprocess.run(make_source, capture_output=True, text=True, timeout=60, check=False)
            if created.returncode != 0:
                self.skipTest(f"Impossible de générer le média de test : {created.stderr[-500:]}")

            source_report = inspect_media(source, ffprobe_path=FFPROBE, ffmpeg_path=FFMPEG, deep_verify=True)
            self.assertEqual(source_report.integrity, "verified")
            command, _mode = build_conversion_command(FFMPEG, source, output, source_report.to_dict())
            converted = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
            self.assertEqual(converted.returncode, 0, converted.stderr[-1200:])

            output_report = inspect_media(output, ffprobe_path=FFPROBE, ffmpeg_path=FFMPEG, deep_verify=True)
            self.assertEqual(output_report.integrity, "verified")
            self.assertEqual((output_report.width, output_report.height), (source_report.width, source_report.height))
            self.assertAlmostEqual(output_report.frame_rate, source_report.frame_rate, places=2)
            self.assertTrue(output_report.audio_codecs)
            self.assertTrue(all(codec == "aac" for codec in output_report.audio_codecs))

            source_size = source.stat().st_size
            output_size = output.stat().st_size
            self.assertGreater(source_size, 0)
            self.assertGreater(output_size, 0)
            size_delta_percent = (output_size - source_size) * 100 / source_size
            self.assertTrue(math.isfinite(size_delta_percent))

            compare = subprocess.run([
                FFMPEG, "-nostdin", "-hide_banner", "-i", str(source), "-i", str(output),
                "-filter_complex", "[0:v:0]setpts=PTS-STARTPTS[reference];[1:v:0]setpts=PTS-STARTPTS[converted];[reference][converted]ssim[out]",
                "-map", "[out]", "-an", "-f", "null", "-",
            ], capture_output=True, text=True, timeout=60, check=False)
            self.assertEqual(compare.returncode, 0, compare.stderr[-1200:])
            match = re.search(r"All:([0-9.]+)", compare.stderr + compare.stdout)
            self.assertIsNotNone(match, compare.stderr[-1200:])
            self.assertGreater(float(match.group(1)), 0.90)

            # The original remains byte-for-byte untouched; both sizes are retained for QA.
            self.assertEqual(source_report.size_bytes, source_size)
            self.assertTrue(output_report.size_bytes == output_size)


if __name__ == "__main__":
    unittest.main()
