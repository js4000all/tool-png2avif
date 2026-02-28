import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import zlib

from PIL import Image
import pillow_avif  # noqa: F401  # Enables AVIF support in Pillow
import piexif
import piexif.helper
from tqdm import tqdm


USER_COMMENT_TAG = 0x9286
UNICODE_PREFIX = b"UNICODE\x00"


def iter_png_files(target: Path):
    if target.is_file():
        if target.suffix.lower() == ".png":
            yield target
        return

    # Recursive search
    yield from target.rglob("*.png")


def _extract_sd_parameters(png_path: Path):
    """
    Extract Stable Diffusion WebUI `parameters` text from PNG chunks.
    Supports tEXt, iTXt, and zTXt.
    Returns None when not present or when parsing fails.
    """
    try:
        with png_path.open("rb") as f:
            if f.read(8) != b"\x89PNG\r\n\x1a\n":
                return None

            while True:
                length_bytes = f.read(4)
                if len(length_bytes) != 4:
                    return None

                length = int.from_bytes(length_bytes, "big")
                chunk_type = f.read(4)
                data = f.read(length)
                f.read(4)  # CRC

                if len(chunk_type) != 4 or len(data) != length:
                    return None

                if chunk_type == b"tEXt":
                    sep = data.find(b"\x00")
                    if sep > 0 and data[:sep] == b"parameters":
                        return data[sep + 1 :].decode("latin-1")

                elif chunk_type == b"zTXt":
                    sep = data.find(b"\x00")
                    if sep > 0 and data[:sep] == b"parameters" and sep + 2 <= len(data):
                        if data[sep + 1] != 0:
                            continue
                        try:
                            decompressed = zlib.decompress(data[sep + 2 :])
                        except zlib.error:
                            continue
                        return decompressed.decode("latin-1")

                elif chunk_type == b"iTXt":
                    sep = data.find(b"\x00")
                    if sep > 0 and data[:sep] == b"parameters":
                        pos = sep + 1
                        if pos + 2 > len(data):
                            continue
                        compression_flag = data[pos]
                        compression_method = data[pos + 1]
                        pos += 2

                        lang_end = data.find(b"\x00", pos)
                        if lang_end < 0:
                            continue
                        pos = lang_end + 1

                        translated_end = data.find(b"\x00", pos)
                        if translated_end < 0:
                            continue
                        pos = translated_end + 1

                        text_bytes = data[pos:]
                        if compression_flag == 1:
                            if compression_method != 0:
                                continue
                            try:
                                text_bytes = zlib.decompress(text_bytes)
                            except zlib.error:
                                continue
                        return text_bytes.decode("utf-8")

                if chunk_type == b"IEND":
                    break
    except Exception:
        return None

    return None


def _to_user_comment_bytes(text: str) -> bytes:
    return piexif.helper.UserComment.dump(text or "", encoding="unicode")


def _worker_convert(png_path_str: str, quality: int, dryrun: bool):
    """
    Convert one PNG to AVIF in a worker process.
    Returns (success, png_path_str, avif_path_str).
    """
    png_path = Path(png_path_str)
    avif_path = png_path.with_suffix(".avif")

    try:
        parameters = _extract_sd_parameters(png_path)

        with Image.open(png_path) as img:
            # Keep alpha if present; Pillow+plugin handles RGBA -> AVIF.
            if not dryrun:
                save_kwargs = {"format": "AVIF", "quality": quality}
                if parameters is not None:
                    exif_dict = {
                        "Exif": {
                            USER_COMMENT_TAG: _to_user_comment_bytes(parameters),
                        },
                    }
                    save_kwargs["exif"] = piexif.dump(exif_dict)
                img.save(avif_path, **save_kwargs)

        if not dryrun:
            png_path.unlink()

        return (True, png_path_str, str(avif_path))

    except Exception:
        # Requirement said: log only (converted, removed)
        # So we stay silent on failures.
        return (False, png_path_str, str(avif_path))


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Recursively convert PNG files to AVIF under a directory (or a single PNG file)."
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="Enable per-file converted/removed logs.",
    )
    p.add_argument(
        "--dryrun",
        action="store_true",
        help="Disable AVIF write and PNG deletion while preserving normal flow.",
    )
    p.add_argument(
        "--quality",
        type=int,
        default=80,
        help="AVIF quality (0-100). Default: 80",
    )
    p.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Number of parallel worker processes. Default: 1",
    )
    p.add_argument(
        "target_path",
        help="Target directory or PNG file path.",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()

    target = Path(args.target_path)

    if not target.exists():
        return 2

    quality = args.quality
    if quality < 0 or quality > 100:
        return 2

    jobs = args.jobs
    if jobs < 1:
        return 2

    png_files = list(
        tqdm(
            iter_png_files(target),
            total=None,
            desc="Scanning",
            unit="file",
        )
    )

    with ProcessPoolExecutor(max_workers=jobs) as executor:
        futures = [
            executor.submit(_worker_convert, str(png_file), quality, args.dryrun)
            for png_file in png_files
        ]

        with tqdm(total=len(futures), desc="Converting", unit="file") as pbar:
            for future in as_completed(futures):
                converted, png_path_str, avif_path_str = future.result()
                pbar.update(1)

                if converted and args.verbose:
                    tqdm.write(f"converted: {png_path_str} -> {avif_path_str}")
                    tqdm.write(f"removed: {png_path_str}")

    any_found = bool(png_files)

    # If no PNGs were found, still treat as non-fatal but signal via exit code.
    return 0 if any_found else 1


if __name__ == "__main__":
    raise SystemExit(main())
