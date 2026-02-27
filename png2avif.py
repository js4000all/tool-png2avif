import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from PIL import Image
import pillow_avif  # noqa: F401  # Enables AVIF support in Pillow
from tqdm import tqdm


def iter_png_files(target: Path):
    if target.is_file():
        if target.suffix.lower() == ".png":
            yield target
        return

    # Recursive search
    yield from target.rglob("*.png")


def _worker_convert(png_path_str: str, quality: int, dryrun: bool):
    """
    Convert one PNG to AVIF in a worker process.
    Returns (success, png_path_str, avif_path_str).
    """
    png_path = Path(png_path_str)
    avif_path = png_path.with_suffix(".avif")

    try:
        with Image.open(png_path) as img:
            # Keep alpha if present; Pillow+plugin handles RGBA -> AVIF.
            if not dryrun:
                img.save(avif_path, format="AVIF", quality=quality)

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
