import tempfile
import unittest
from pathlib import Path

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from png2avif import (
    ASCII_PREFIX,
    UNICODE_PREFIX,
    USER_COMMENT_TAG,
    _extract_sd_parameters,
    _inject_handler_description,
    _to_user_comment_bytes,
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

    def test_user_comment_encoding_ascii_and_unicode(self):
        ascii_value = "prompt: a cat"
        unicode_value = "プロンプト: 猫"

        self.assertEqual(
            _to_user_comment_bytes(ascii_value),
            ASCII_PREFIX + ascii_value.encode("ascii"),
        )
        self.assertEqual(
            _to_user_comment_bytes(unicode_value),
            UNICODE_PREFIX + unicode_value.encode("utf-16le"),
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
                exif = converted.getexif()
                self.assertEqual(
                    exif.get(USER_COMMENT_TAG),
                    ASCII_PREFIX + prompt.encode("ascii"),
                )

    def test_inject_handler_description_adds_libavif_string_and_keeps_image_readable(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            png = base / "plain.png"
            Image.new("RGB", (4, 4), (10, 20, 30)).save(png)

            success, _, avif_path_str = _worker_convert(str(png), 80, False)
            self.assertTrue(success)
            avif_path = Path(avif_path_str)

            data = avif_path.read_bytes()
            self.assertIn(b"libavif\x00", data)

            with Image.open(avif_path) as converted:
                self.assertEqual(converted.size, (4, 4))

            original = data
            _inject_handler_description(avif_path)
            self.assertEqual(avif_path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
