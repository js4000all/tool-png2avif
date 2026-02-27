import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import zlib

from PIL import Image
import pillow_avif  # noqa: F401  # Enables AVIF support in Pillow
from tqdm import tqdm


USER_COMMENT_TAG = 0x9286
ASCII_PREFIX = b"ASCII\x00\x00\x00"
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
    if all(ord(ch) < 128 for ch in text):
        return ASCII_PREFIX + text.encode("ascii")
    return UNICODE_PREFIX + text.encode("utf-16le")


def _parse_box_header(data: bytes, offset: int, end: int):
    if offset + 8 > end:
        return None
    size = int.from_bytes(data[offset : offset + 4], "big")
    box_type = data[offset + 4 : offset + 8]
    header_size = 8
    if size == 1:
        if offset + 16 > end:
            return None
        size = int.from_bytes(data[offset + 8 : offset + 16], "big")
        header_size = 16
    elif size == 0:
        size = end - offset
    if size < header_size or offset + size > end:
        return None
    return size, header_size, box_type


def _patch_iloc_offsets(meta_payload: bytes, delta: int) -> bytes:
    # meta payload includes fullbox header at [0:4]
    if len(meta_payload) < 4:
        return meta_payload

    i = 4
    end = len(meta_payload)
    while i < end:
        header = _parse_box_header(meta_payload, i, end)
        if header is None:
            return meta_payload
        size, header_size, box_type = header
        if box_type == b"iloc":
            iloc = bytearray(meta_payload[i : i + size])
            cursor = header_size + 4  # skip fullbox version/flags
            if len(iloc) < cursor + 2:
                return meta_payload

            version = iloc[8]
            if version not in (0, 1, 2):
                return meta_payload

            offset_size = iloc[cursor] >> 4
            length_size = iloc[cursor] & 0x0F
            base_offset_size = iloc[cursor + 1] >> 4
            index_size = iloc[cursor + 1] & 0x0F if version in (1, 2) else 0
            cursor += 2

            item_count_size = 2 if version < 2 else 4
            if len(iloc) < cursor + item_count_size:
                return meta_payload
            item_count = int.from_bytes(iloc[cursor : cursor + item_count_size], "big")
            cursor += item_count_size

            for _ in range(item_count):
                if version < 2:
                    if len(iloc) < cursor + 2:
                        return meta_payload
                    cursor += 2  # item_ID
                else:
                    if len(iloc) < cursor + 4:
                        return meta_payload
                    cursor += 4

                if version in (1, 2):
                    if len(iloc) < cursor + 2:
                        return meta_payload
                    cursor += 2  # construction_method/reserved

                if len(iloc) < cursor + 2:
                    return meta_payload
                cursor += 2  # data_reference_index

                if len(iloc) < cursor + base_offset_size:
                    return meta_payload
                cursor += base_offset_size

                if len(iloc) < cursor + 2:
                    return meta_payload
                extent_count = int.from_bytes(iloc[cursor : cursor + 2], "big")
                cursor += 2

                for _ in range(extent_count):
                    if version in (1, 2) and index_size > 0:
                        if len(iloc) < cursor + index_size:
                            return meta_payload
                        cursor += index_size

                    if len(iloc) < cursor + offset_size:
                        return meta_payload
                    if offset_size > 0:
                        old_offset = int.from_bytes(iloc[cursor : cursor + offset_size], "big")
                        new_offset = old_offset + delta
                        iloc[cursor : cursor + offset_size] = new_offset.to_bytes(offset_size, "big")
                    cursor += offset_size

                    if len(iloc) < cursor + length_size:
                        return meta_payload
                    cursor += length_size

            return meta_payload[:i] + bytes(iloc) + meta_payload[i + size :]

        i += size

    return meta_payload


def _inject_handler_description(avif_path: Path, description: bytes = b"libavif"):
    """
    Add Handler Description in meta/hdlr for AVIF files generated by pillow-avif.
    Silent no-op when structure is unsupported.
    """
    try:
        data = avif_path.read_bytes()
    except Exception:
        return

    top_end = len(data)
    i = 0
    meta_offset = None
    meta_size = None
    meta_header_size = None

    while i < top_end:
        header = _parse_box_header(data, i, top_end)
        if header is None:
            return
        size, header_size, box_type = header
        if box_type == b"meta":
            meta_offset, meta_size, meta_header_size = i, size, header_size
            break
        i += size

    if meta_offset is None:
        return

    meta_start = meta_offset + meta_header_size
    meta_end = meta_offset + meta_size
    if meta_end > len(data) or meta_start + 4 > meta_end:
        return

    meta_payload = data[meta_start:meta_end]
    j = 4  # skip fullbox header
    hdlr_local_offset = None
    hdlr_size = None
    hdlr_header_size = None
    while j < len(meta_payload):
        header = _parse_box_header(meta_payload, j, len(meta_payload))
        if header is None:
            return
        size, header_size, box_type = header
        if box_type == b"hdlr":
            hdlr_local_offset, hdlr_size, hdlr_header_size = j, size, header_size
            break
        j += size

    if hdlr_local_offset is None:
        return

    hdlr_payload_start = hdlr_local_offset + hdlr_header_size
    hdlr_payload_end = hdlr_local_offset + hdlr_size
    hdlr_payload = meta_payload[hdlr_payload_start:hdlr_payload_end]
    if len(hdlr_payload) < 24:
        return

    current_name = hdlr_payload[24:]
    if current_name not in (b"", b"\x00"):
        return

    new_name = description + b"\x00"
    delta = len(new_name) - len(current_name)
    if delta <= 0:
        return

    new_hdlr_payload = hdlr_payload[:24] + new_name
    new_hdlr_size = hdlr_size + delta
    new_hdlr_box = new_hdlr_size.to_bytes(4, "big") + b"hdlr" + new_hdlr_payload

    meta_before = meta_payload[:hdlr_local_offset]
    meta_after = meta_payload[hdlr_local_offset + hdlr_size :]
    updated_meta_payload = meta_before + new_hdlr_box + meta_after
    updated_meta_payload = _patch_iloc_offsets(updated_meta_payload, delta)

    new_meta_size = meta_size + delta
    new_meta_box = new_meta_size.to_bytes(4, "big") + b"meta" + updated_meta_payload

    updated = data[:meta_offset] + new_meta_box + data[meta_offset + meta_size :]

    try:
        avif_path.write_bytes(updated)
    except Exception:
        return


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
                    exif = Image.Exif()
                    exif[USER_COMMENT_TAG] = _to_user_comment_bytes(parameters)
                    save_kwargs["exif"] = exif.tobytes()
                img.save(avif_path, **save_kwargs)
                _inject_handler_description(avif_path)

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
