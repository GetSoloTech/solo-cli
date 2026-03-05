import hashlib
import os
import shutil
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from fnmatch import fnmatch
from pathlib import Path

import requests
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TransferSpeedColumn

from solo.hub.constants import REPO_ID_SEPARATOR, SOLO_CACHE_DIR
from solo.hub.errors import SoloDownloadError

# Download tuning constants
DOWNLOAD_CHUNK_SIZE = 10 * 1024 * 1024  # 10 MB stream chunks
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024  # 100 MB - use chunked download above this
CHUNK_CONNECTIONS = 4  # parallel connections per large file
MAX_RETRIES = 3
REQUEST_TIMEOUT = (10, 60)  # (connect, read) seconds

# Global semaphore to cap total concurrent HTTP connections
_connection_semaphore = threading.Semaphore(16)


_SIZE_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}


def parse_file_size(size_value) -> int | None:
    """Parse a file size that may be an int, numeric string, or human-readable string like '3.19 KB'."""
    if size_value is None:
        return None
    if isinstance(size_value, (int, float)):
        return int(size_value)
    s = str(size_value).strip()
    if not s:
        return None
    # Try plain numeric first
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return int(float(s))
    except ValueError:
        pass
    # Parse human-readable format: "3.19 KB", "100MB", etc.
    s_upper = s.upper()
    for unit, multiplier in sorted(_SIZE_UNITS.items(), key=lambda x: -len(x[0])):
        if s_upper.endswith(unit):
            num_part = s_upper[: -len(unit)].strip()
            try:
                return int(float(num_part) * multiplier)
            except ValueError:
                return None
    return None


def _filename_slug(filename: str) -> str:
    """Convert a filename (possibly with /) into a safe slug for temp files."""
    return filename.replace("/", "_").replace("\\", "_") or "file"


def get_cache_dir(org: str, model_name: str, cache_root: str | None = None) -> Path:
    """Return the cache directory for a model: ~/.solo/hub/models--{org}--{model_name}"""
    root = Path(cache_root or SOLO_CACHE_DIR)
    folder = f"models{REPO_ID_SEPARATOR}{org}{REPO_ID_SEPARATOR}{model_name}"
    return root / folder


def _ensure_dirs(cache_dir: Path) -> None:
    """Create blobs/, snapshots/, and refs/ subdirectories."""
    (cache_dir / "blobs").mkdir(parents=True, exist_ok=True)
    (cache_dir / "snapshots").mkdir(parents=True, exist_ok=True)
    (cache_dir / "refs").mkdir(parents=True, exist_ok=True)


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(DOWNLOAD_CHUNK_SIZE), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def make_progress_bar() -> Progress:
    """Create a standard download progress bar."""
    return Progress(
        TextColumn("[bold blue]{task.fields[filename]}"),
        BarColumn(bar_width=40, complete_style="green", finished_style="green"),
        "{task.percentage:>3.0f}%",
        DownloadColumn(),
        TransferSpeedColumn(),
    )


def _download_stream(
    url: str,
    dest_path: Path,
    *,
    range_start: int = 0,
    range_end: int | None = None,
    progress: Progress | None = None,
    task_id: int | None = None,
) -> None:
    """
    Download a byte range from url to dest_path with resume support.

    If dest_path exists, resumes from its current size (within the assigned range).
    Acquires the global connection semaphore for the duration of the stream.
    """
    existing_size = dest_path.stat().st_size if dest_path.exists() else 0
    actual_start = range_start + existing_size

    # Already complete for this range
    if range_end is not None and actual_start >= range_end:
        # Account for already-downloaded bytes in progress
        if existing_size > 0 and progress is not None and task_id is not None:
            progress.update(task_id, advance=existing_size)
        return

    headers = {}
    if range_end is not None:
        headers["Range"] = f"bytes={actual_start}-{range_end - 1}"
    elif actual_start > 0:
        headers["Range"] = f"bytes={actual_start}-"

    _connection_semaphore.acquire()
    try:
        resp = requests.get(url, stream=True, timeout=REQUEST_TIMEOUT, headers=headers)
        resp.raise_for_status()

        # Server ignored Range header — start fresh
        if actual_start > 0 and resp.status_code == 200:
            existing_size = 0
            mode = "wb"
        else:
            mode = "ab" if existing_size > 0 else "wb"

        # Account for already-downloaded bytes in progress
        if existing_size > 0 and progress is not None and task_id is not None:
            progress.update(task_id, advance=existing_size)

        with open(dest_path, mode) as f:
            for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                f.write(chunk)
                if progress is not None and task_id is not None:
                    progress.update(task_id, advance=len(chunk))
    finally:
        _connection_semaphore.release()


def download_file_to_blob(
    url: str,
    cache_dir: Path,
    filename: str = "",
    expected_hash: str | None = None,
    force: bool = False,
    file_size: int | None = None,
    progress: Progress | None = None,
    task_id: int | None = None,
) -> Path:
    """
    Download a file from a presigned URL into the blobs/ directory.

    Supports resume (via deterministic .incomplete files) and retry with backoff.
    Large files (>100MB) are automatically routed to multi-connection chunked download.

    When progress/task_id are provided, updates a shared progress bar instead of creating one.

    Returns the path to the blob file.
    """
    _ensure_dirs(cache_dir)
    blobs_dir = cache_dir / "blobs"
    display_name = filename or "file"

    # Fast path: blob already exists
    if expected_hash and not force:
        blob_path = blobs_dir / expected_hash
        if blob_path.exists():
            return blob_path

    # Determine total size for progress
    total = file_size or None

    # Create own progress bar if none provided (single-file download path)
    own_progress = progress is None
    if own_progress:
        progress = make_progress_bar()
        progress.start()
        task_id = progress.add_task("download", total=total, filename=display_name)

    try:
        # Route large files to chunked downloader
        if file_size and file_size > LARGE_FILE_THRESHOLD:
            return _download_file_chunked(
                url, cache_dir, filename, file_size,
                force=force, progress=progress, task_id=task_id,
            )

        # Deterministic incomplete path for resume
        slug = _filename_slug(display_name)
        incomplete_path = blobs_dir / f"{slug}.incomplete"

        if force and incomplete_path.exists():
            incomplete_path.unlink()

        for attempt in range(MAX_RETRIES):
            try:
                _download_stream(
                    url, incomplete_path,
                    progress=progress, task_id=task_id,
                )
                break  # success
            except (requests.ConnectionError, requests.Timeout) as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except requests.RequestException as e:
                status = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
                if status == 403:
                    incomplete_path.unlink(missing_ok=True)
                    raise SoloDownloadError(
                        f"Download link for '{display_name}' has expired. Please retry the download."
                    ) from e
                raise

        # Compute hash and move to final location
        file_hash = compute_file_hash(incomplete_path)
        blob_path = blobs_dir / file_hash

        if blob_path.exists() and not force:
            incomplete_path.unlink()
        else:
            shutil.move(str(incomplete_path), str(blob_path))

        return blob_path

    except SoloDownloadError:
        raise
    except requests.RequestException as e:
        # Don't delete incomplete file — allows resume on next run
        if isinstance(e, (requests.ConnectionError, requests.Timeout)):
            raise SoloDownloadError(
                f"Connection lost while downloading '{display_name}'. "
                f"Check your network and try again (download will resume)."
            ) from e
        raise SoloDownloadError(f"Failed to download '{display_name}': {e}") from e
    except OSError as e:
        raise SoloDownloadError(
            f"Failed to save '{display_name}': {e}. Check disk space and permissions."
        ) from e
    finally:
        if own_progress and progress is not None:
            progress.stop()


def _download_file_chunked(
    url: str,
    cache_dir: Path,
    filename: str,
    file_size: int,
    *,
    force: bool = False,
    progress: Progress | None = None,
    task_id: int | None = None,
) -> Path:
    """
    Download a large file using multiple parallel connections.

    Splits the file into CHUNK_CONNECTIONS byte ranges, downloads each in parallel,
    then assembles and hashes the result.
    """
    blobs_dir = cache_dir / "blobs"
    slug = _filename_slug(filename or "file")
    display_name = filename or "file"

    # Create own progress bar if none provided
    own_progress = progress is None
    if own_progress:
        progress = make_progress_bar()
        progress.start()
        task_id = progress.add_task("download", total=file_size, filename=display_name)

    # Calculate byte ranges for each chunk
    chunk_size = file_size // CHUNK_CONNECTIONS
    ranges = []
    for i in range(CHUNK_CONNECTIONS):
        start = i * chunk_size
        end = file_size if i == CHUNK_CONNECTIONS - 1 else (i + 1) * chunk_size
        part_path = blobs_dir / f"{slug}.part{i}"
        if force and part_path.exists():
            part_path.unlink()
        ranges.append((start, end, part_path))

    try:
        # Download chunks in parallel
        with ThreadPoolExecutor(max_workers=CHUNK_CONNECTIONS) as pool:
            futures = {}
            for start, end, part_path in ranges:
                fut = pool.submit(
                    _download_chunk_with_retry,
                    url, part_path, start, end,
                    progress=progress, task_id=task_id,
                    display_name=display_name,
                )
                futures[fut] = part_path

            for fut in as_completed(futures):
                fut.result()  # raises on failure

        # Assemble chunks into incomplete file
        incomplete_path = blobs_dir / f"{slug}.incomplete"
        try:
            with open(incomplete_path, "wb") as out:
                for _, _, part_path in ranges:
                    with open(part_path, "rb") as inp:
                        shutil.copyfileobj(inp, out, length=DOWNLOAD_CHUNK_SIZE)
                    part_path.unlink()
        except OSError as e:
            raise SoloDownloadError(
                f"Failed to save '{display_name}': {e}. Check disk space and permissions."
            ) from e

        # Hash and move to final blob location
        file_hash = compute_file_hash(incomplete_path)
        blob_path = blobs_dir / file_hash

        if blob_path.exists() and not force:
            incomplete_path.unlink()
        else:
            shutil.move(str(incomplete_path), str(blob_path))

        return blob_path

    except SoloDownloadError:
        # Leave .part files for resume on next run
        raise
    except OSError as e:
        raise SoloDownloadError(
            f"Failed to save '{display_name}': {e}. Check disk space and permissions."
        ) from e
    finally:
        if own_progress and progress is not None:
            progress.stop()


def _download_chunk_with_retry(
    url: str,
    dest_path: Path,
    start: int,
    end: int,
    *,
    progress: Progress | None = None,
    task_id: int | None = None,
    display_name: str = "file",
) -> None:
    """Download a single chunk with retry logic."""
    for attempt in range(MAX_RETRIES):
        try:
            _download_stream(
                url, dest_path,
                range_start=start, range_end=end,
                progress=progress, task_id=task_id,
            )
            return
        except (requests.ConnectionError, requests.Timeout):
            if attempt < MAX_RETRIES - 1:
                time.sleep(2 ** attempt)
                continue
            raise SoloDownloadError(
                f"Connection lost while downloading '{display_name}'. "
                f"Check your network and try again (download will resume)."
            )
        except requests.RequestException as e:
            status = getattr(e.response, "status_code", None) if hasattr(e, "response") else None
            if status == 403:
                raise SoloDownloadError(
                    f"Download link for '{display_name}' has expired. Please retry the download."
                ) from e
            raise SoloDownloadError(f"Failed to download '{display_name}': {e}") from e


def create_snapshot_symlinks(
    cache_dir: Path,
    revision: str,
    file_map: dict[str, Path],
) -> Path:
    """
    Create symlinks in snapshots/{revision}/ pointing to blobs.

    file_map: {filename: blob_path}
    Returns the snapshot directory path.
    """
    _ensure_dirs(cache_dir)
    snapshot_dir = cache_dir / "snapshots" / revision
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    for filename, blob_path in file_map.items():
        # Support nested filenames (e.g. "subdir/file.txt")
        link_path = snapshot_dir / filename
        link_path.parent.mkdir(parents=True, exist_ok=True)

        # Create relative symlink: snapshots/{rev}/{file} -> ../../blobs/{hash}
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()

        rel_target = os.path.relpath(blob_path, link_path.parent)
        link_path.symlink_to(rel_target)

    return snapshot_dir


def update_ref(cache_dir: Path, ref_name: str, revision: str) -> None:
    """Write revision string to refs/{ref_name}."""
    _ensure_dirs(cache_dir)
    ref_path = cache_dir / "refs" / ref_name
    ref_path.write_text(revision)


def get_cached_file(
    org: str,
    model_name: str,
    filename: str,
    revision: str = "latest",
    cache_root: str | None = None,
) -> Path | None:
    """
    Check if a file exists in cache for the given model/revision.
    Returns the symlink path in snapshots/ if it exists, else None.
    """
    cache_dir = get_cache_dir(org, model_name, cache_root)
    file_path = cache_dir / "snapshots" / revision / filename
    if file_path.exists():
        return file_path
    return None


def filter_files(
    filenames: list[str],
    allow_patterns: list[str] | str | None = None,
    ignore_patterns: list[str] | str | None = None,
) -> list[str]:
    """Filter filenames using allow/ignore glob patterns."""
    if isinstance(allow_patterns, str):
        allow_patterns = [allow_patterns]
    if isinstance(ignore_patterns, str):
        ignore_patterns = [ignore_patterns]

    result = filenames

    if allow_patterns:
        result = [f for f in result if any(fnmatch(f, p) for p in allow_patterns)]

    if ignore_patterns:
        result = [f for f in result if not any(fnmatch(f, p) for p in ignore_patterns)]

    return result
