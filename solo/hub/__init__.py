from solo.hub.constants import SOLO_PREFIX, SOLO_URL_PREFIX


def is_solo_ref(identifier: str) -> bool:
    """Check if identifier starts with 'solo:' or 'solo://'."""
    s = str(identifier)
    return s.startswith(SOLO_PREFIX) or s.startswith(SOLO_URL_PREFIX)


def parse_solo_ref(identifier: str) -> str:
    """Strip 'solo:' or 'solo://' prefix, return the raw identifier."""
    s = str(identifier)
    if s.startswith(SOLO_URL_PREFIX):
        return s[len(SOLO_URL_PREFIX):]
    if s.startswith(SOLO_PREFIX):
        return s[len(SOLO_PREFIX):]
    return s


def _check_model_status(model_info: dict, repo_id: str) -> None:
    """Raise SoloHubError if the model is not ready for download."""
    from solo.hub.errors import SoloHubError

    status = (model_info.get("status") or "").lower()
    if status and status != "completed":
        status_display = status.replace("_", " ").title()
        raise SoloHubError(
            f"Model '{repo_id}' is not ready for download (status: {status_display}). "
            f"Run 'solo status {repo_id}' to track training progress."
        )


def _flatten_files_response(files_data: dict) -> list[dict]:
    """
    Flatten the files API response (dict of folder->file_list) into a flat list.
    Each item gets a 'path' field with the filename.

    """
    flat = []
    for _folder, files in files_data.items():
        for f in files:
            name = f.get("name", "")
            flat.append({**f, "path": name})
    return flat


def solo_hub_download(
    repo_id: str,
    filename: str,
    *,
    revision: str | None = None,
    cache_dir: str | None = None,
    force_download: bool = False,
    token: str | None = None,
) -> str:
    """
    Download a single file from Solo Hub. Drop-in replacement for hf_hub_download.

    Args:
        repo_id: Model identifier as 'org/model_name' (without solo: prefix).
        filename: The file to download (e.g. 'model.safetensors', 'config.json').
        revision: Version/revision (defaults to 'latest').
        cache_dir: Override default cache directory.
        force_download: Re-download even if cached.
        token: Override stored auth token.

    Returns:
        Local path to the downloaded file.
    """
    from solo.hub.cache import (
        create_snapshot_symlinks,
        download_file_to_blob,
        get_cache_dir,
        get_cached_file,
        parse_file_size,
        update_ref,
    )
    from solo.hub.client import SoloHubClient
    from solo.hub.errors import SoloModelNotFoundError

    revision = revision or "latest"

    # Parse org/model_name
    parts = repo_id.split("/", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid model identifier '{repo_id}'. Expected format: 'org/model_name'."
        )
    org, model_name = parts

    # Check cache first
    if not force_download:
        cached = get_cached_file(org, model_name, filename, revision, cache_dir)
        if cached:
            return str(cached)

    # Fetch model info using just the model name (API doesn't use org prefix in path)
    client = SoloHubClient(token=token)
    model_info = client.get_model_info(model_name)
    _check_model_status(model_info, repo_id)

    model_id = model_info.get("id")
    org_id = model_info.get("organizationId") or model_info.get("organization", {}).get("id", "")

    if not model_id or not org_id:
        raise SoloModelNotFoundError(
            f"Could not resolve model '{repo_id}'. Missing model ID or organization ID."
        )

    files_data = client.get_model_files(org_id, model_id)
    flat_files = _flatten_files_response(files_data)

    # Find the requested file
    target = None
    for f in flat_files:
        if f["path"] == filename or f.get("name") == filename:
            target = f
            break

    if not target:
        available = [f["path"] for f in flat_files]
        raise FileNotFoundError(
            f"File '{filename}' not found in model '{repo_id}' on Solo Hub.\n"
            f"Available files: {available}"
        )

    # Download to cache
    cache = get_cache_dir(org, model_name, cache_dir)
    blob_path = download_file_to_blob(
        url=target["url"],
        cache_dir=cache,
        filename=filename,
        force=force_download,
        file_size=parse_file_size(target.get("fileSize")),
    )

    # Create symlink and update ref
    snapshot_dir = create_snapshot_symlinks(cache, revision, {filename: blob_path})
    update_ref(cache, "main", revision)

    return str(snapshot_dir / filename)


def solo_snapshot_download(
    repo_id: str,
    *,
    revision: str | None = None,
    cache_dir: str | None = None,
    force_download: bool = False,
    token: str | None = None,
    allow_patterns: list[str] | str | None = None,
    ignore_patterns: list[str] | str | None = None,
) -> str:
    """
    Download all files for a model from Solo Hub. Drop-in replacement for snapshot_download.

    Args:
        repo_id: Model identifier as 'org/model_name' (without solo: prefix).
        revision: Version/revision (defaults to 'latest').
        cache_dir: Override default cache directory.
        force_download: Re-download even if cached.
        token: Override stored auth token.
        allow_patterns: Only download files matching these patterns.
        ignore_patterns: Skip files matching these patterns.

    Returns:
        Local path to the snapshot directory containing all files.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from solo.hub.cache import (
        create_snapshot_symlinks,
        download_file_to_blob,
        filter_files,
        get_cache_dir,
        get_cached_file,
        make_progress_bar,
        parse_file_size,
        update_ref,
    )
    from solo.hub.client import SoloHubClient
    from solo.hub.errors import SoloDownloadError, SoloModelNotFoundError

    MAX_WORKERS = 8
    revision = revision or "latest"

    # Parse org/model_name
    parts = repo_id.split("/", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid model identifier '{repo_id}'. Expected format: 'org/model_name'."
        )
    org, model_name = parts

    # Fetch model info using just the model name (API doesn't use org prefix in path)
    client = SoloHubClient(token=token)
    model_info = client.get_model_info(model_name)
    _check_model_status(model_info, repo_id)

    model_id = model_info.get("id")
    org_id = model_info.get("organizationId") or model_info.get("organization", {}).get("id", "")

    if not model_id or not org_id:
        raise SoloModelNotFoundError(
            f"Could not resolve model '{repo_id}'. Missing model ID or organization ID."
        )

    files_data = client.get_model_files(org_id, model_id)
    flat_files = _flatten_files_response(files_data)

    if not flat_files:
        raise SoloModelNotFoundError(f"No files found for model '{repo_id}' on Solo Hub.")

    # Filter files
    all_paths = [f["path"] for f in flat_files]
    filtered_paths = filter_files(all_paths, allow_patterns, ignore_patterns)
    files_to_download = [f for f in flat_files if f["path"] in filtered_paths]

    # Check cache and separate cached vs uncached files
    cache = get_cache_dir(org, model_name, cache_dir)
    file_map: dict[str, str] = {}
    uncached_files = []

    for f in files_to_download:
        if not force_download:
            cached = get_cached_file(org, model_name, f["path"], revision, cache_dir)
            if cached and cached.resolve().exists():
                file_map[f["path"]] = cached.resolve()
                continue
        uncached_files.append(f)

    if not uncached_files:
        from rich.console import Console
        Console().print(f"Model [cyan]{repo_id}[/cyan] is already cached.")
    else:
        # Download uncached files in parallel with shared progress bar
        errors: list[str] = []

        with make_progress_bar() as progress:
            with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
                future_to_file = {}
                for f in uncached_files:
                    file_size = parse_file_size(f.get("fileSize")) or 0
                    tid = progress.add_task(
                        "download",
                        total=file_size or None,
                        filename=f["path"],
                    )
                    future = pool.submit(
                        download_file_to_blob,
                        url=f["url"],
                        cache_dir=cache,
                        filename=f["path"],
                        force=force_download,
                        file_size=file_size or None,
                        progress=progress,
                        task_id=tid,
                    )
                    future_to_file[future] = f

                for future in as_completed(future_to_file):
                    f = future_to_file[future]
                    try:
                        blob_path = future.result()
                        file_map[f["path"]] = blob_path
                    except Exception as e:
                        errors.append(f"{f['path']}: {e}")

        if errors:
            raise SoloDownloadError(
                f"Failed to download {len(errors)} file(s):\n" + "\n".join(f"  - {e}" for e in errors)
            )

    # Create symlinks and update ref
    snapshot_dir = create_snapshot_symlinks(cache, revision, file_map)
    update_ref(cache, "main", revision)

    return str(snapshot_dir)
