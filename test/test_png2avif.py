import tempfile
import unittest
from pathlib import Path

import piexif
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from png2avif import (
    UNICODE_PREFIX,
    USER_COMMENT_TAG,
    _extract_sd_parameters,
    _to_user_comment_bytes,
    _worker_chunk,
    _worker_convert,
)


class TestParametersMetadata(unittest.TestCase):
    def _make_png(self, path: Path, chunk_type: str, value: str):
        img = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
        info = PngInfo()
        if chunk_type == "tEXt":
            info.add_text("parameters", value)
        elif chunk_type == "zTXt":
            info.add_text("parameters", value, zip=True)
        elif chunk_type == "iTXt":
            info.add_itxt("parameters", value, lang="", tkey="", zip=False)
        else:
            raise ValueError(chunk_type)
        img.save(path, pnginfo=info)

    def test_extract_parameters_from_all_png_text_chunks(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            expected = "Steps: 20, CFG scale: 7, Seed: 123"

            for chunk_type in ("tEXt", "zTXt", "iTXt"):
                png = base / f"{chunk_type}.png"
                self._make_png(png, chunk_type, expected)
                self.assertEqual(_extract_sd_parameters(png), expected)

    def test_user_comment_encoding_uses_unicode_prefix(self):
        ascii_value = "prompt: a cat"
        unicode_value = "プロンプト: 猫"

        self.assertEqual(
            _to_user_comment_bytes(ascii_value),
            UNICODE_PREFIX + ascii_value.encode("utf-16be"),
        )
        self.assertEqual(
            _to_user_comment_bytes(unicode_value),
            UNICODE_PREFIX + unicode_value.encode("utf-16be"),
        )

    def test_worker_writes_user_comment_to_avif_and_keeps_dryrun_side_effect_free(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            png = base / "input.png"
            prompt = "masterpiece, best quality"
            self._make_png(png, "tEXt", prompt)

            success, _, avif_path_str = _worker_convert(str(png), 80, True)
            self.assertTrue(success)
            self.assertTrue(png.exists())
            self.assertFalse(Path(avif_path_str).exists())

            success, _, avif_path_str = _worker_convert(str(png), 80, False)
            self.assertTrue(success)
            avif_path = Path(avif_path_str)
            self.assertFalse(png.exists())
            self.assertTrue(avif_path.exists())

            with Image.open(avif_path) as converted:
                exif_bytes = converted.info.get("exif")
                self.assertIsNotNone(exif_bytes)
                exif = piexif.load(exif_bytes)
                self.assertEqual(
                    exif["Exif"].get(USER_COMMENT_TAG),
                    UNICODE_PREFIX + prompt.encode("utf-16be"),
                )

    def test_worker_chunk_processes_multiple_files(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            files = []
            for idx in range(3):
                png = base / f"input-{idx}.png"
                self._make_png(png, "tEXt", f"prompt-{idx}")
                files.append(str(png))

            results = _worker_chunk(files, 80, False)
            self.assertEqual(len(results), 3)
            self.assertTrue(all(result[0] for result in results))
            for _, png_path_str, avif_path_str in results:
                self.assertFalse(Path(png_path_str).exists())
                self.assertTrue(Path(avif_path_str).exists())



if __name__ == "__main__":
    unittest.main()
