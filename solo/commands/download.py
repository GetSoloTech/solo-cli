from rich.console import Console

console = Console()


def download(model: str, local_dir: str | None = None) -> None:
    """
    Downloads a model from Solo Hub.
    Accepts both 'org/model_name' and 'solo:org/model_name' formats.
    """
    import os
    import shutil

    from solo.hub import parse_solo_ref, solo_snapshot_download
    from solo.hub.errors import SoloAuthError, SoloHubError

    # Strip solo: prefix if present (both formats go to Solo Hub)
    clean_id = parse_solo_ref(model)

    console.print(f"Downloading from Solo Hub: [bold]{clean_id}[/bold]...")
    try:
        model_path = solo_snapshot_download(repo_id=clean_id)

        # Copy to local directory if requested
        if local_dir is not None:
            dest = os.path.abspath(local_dir)
            os.makedirs(dest, exist_ok=True)
            for entry in os.scandir(model_path):
                src = entry.path
                dst = os.path.join(dest, entry.name)
                if entry.is_dir(follow_symlinks=True):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                else:
                    # Resolve symlinks so we copy the actual file
                    shutil.copy2(os.path.realpath(src), dst)
            console.print(f"Model saved to: [bold]{dest}[/bold]")
        else:
            console.print(f"Model downloaded to: [bold]{model_path}[/bold]")
    except SoloAuthError as e:
        console.print(f"{e}", style="bold red")
    except SoloHubError as e:
        console.print(f"Download failed: {e}", style="bold red")
    except ValueError as e:
        console.print(f"{e}", style="bold red")
        console.print("Expected format: [bold]org/model_name[/bold] or [bold]solo:org/model_name[/bold]")
    except KeyboardInterrupt:
        console.print("\nDownload cancelled by user.", style="bold red")
    except Exception as e:
        console.print(f"Unexpected error: {e}", style="bold red")
        console.print("If this persists, please run [bold]solo login --force[/bold] or contact support.")
