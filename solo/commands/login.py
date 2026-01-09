"""
Login command for Solo CLI using device code flow.
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.spinner import Spinner
from rich import box

from solo.auth.auth import (
    generate_device_code,
    poll_for_token,
    save_token,
    is_authenticated,
    API_BASE_URL,
)

console = Console()


def _handle_error(error_msg: str) -> None:
    """Consolidated error handling with user-friendly messages."""
    error_lower = error_msg.lower()
    
    if "already used" in error_lower or "bad request" in error_lower or "400" in error_lower:
        console.print(f"\n❌ {error_msg}", style="red")
        console.print("Please run 'solo login' again to generate a new code.", style="yellow")
    elif "timed out" in error_lower or "timeout" in error_lower or "connection" in error_lower:
        console.print(f"\n❌ {error_msg}", style="red")
        console.print("Please check your internet connection and try again.", style="yellow")
    elif "server error" in error_lower or "500" in error_msg:
        console.print(f"\n❌ {error_msg}", style="red")
        console.print("The authentication server is experiencing issues. Please try again later.", style="yellow")
    else:
        console.print(f"\n❌ An error occurred during login: {error_msg}", style="red")
        console.print("Please try again or contact support if the issue persists.", style="yellow")


def login():
    """
    Login to Solo CLI using device code flow.
    
    Displays a user code and verification URL, then polls for authorization.
    """
    # Check if already authenticated
    if is_authenticated():
        console.print("✅ You are already logged in.", style="green")
        return
    
    try:
        # Generate device code
        console.print("\n🔐 Generating authentication code...\n")
        
        device_response = generate_device_code()
        
        device_code = device_response.get('deviceCode')
        user_code = device_response.get('userCode')
        verification_url = device_response.get('verification_url', f"{API_BASE_URL}/activate")
        expires_in = device_response.get('expires_in', 600000)  # Default 600 seconds
        intervals = device_response.get('intervals', 5)  # Default 5 seconds
        
        # Display authentication instructions
        auth_content = f"""Please visit the following URL and enter the code:

🔗 {verification_url}

Enter this code:
   {user_code}

Waiting for authorization..."""
        
        console.print(Panel(
            auth_content,
            title="[bold magenta]🔐 Authentication Required[/]",
            border_style="bright_blue",
            box=box.ROUNDED,
            padding=(1, 2)
        ))
        console.print()
        
        # Poll for token with progress indicator (poll_for_token handles polling internally)
        def update_progress(elapsed: int, remaining: int):
            """Update progress spinner"""
            live.update(
                Spinner(
                    "dots",
                    text=f"Polling for authorization... ({elapsed}s elapsed, {remaining}s remaining)"
                )
            )
        
        with Live(Spinner("dots", text="Polling for authorization..."), refresh_per_second=10) as live:
            try:
                token_response = poll_for_token(device_code, expires_in, intervals, update_progress)
                
                if token_response:
                    save_token(token_response)
                    user = token_response.get('user', {})
                    user_email = user.get('email', 'Unknown')
                    org_id = user.get('org_id', '')
                    
                    success_content = f"✅ Authentication successful!\n\nLogged in as: {user_email}"
                    if org_id:
                        success_content += f"\nOrganization: {org_id}"
                    
                    live.stop()
                    console.print(Panel(
                        success_content,
                        title="[bold green]Success[/]",
                        border_style="green",
                        box=box.ROUNDED,
                        padding=(1, 2)
                    ))
                    return
                else:
                    live.stop()
                    _handle_error("Authentication timeout. The code has expired.")
                    raise typer.Exit(1)
            except typer.Exit:
                live.stop()
                raise  # Re-raise to exit properly
            except Exception as e:
                live.stop()
                error_msg = str(e)
                # Don't show error if it's just an exit code
                if error_msg and error_msg != "1" and not error_msg.isdigit():
                    _handle_error(error_msg)
                raise typer.Exit(1)
        
    except KeyboardInterrupt:
        console.print("\n\n⚠️  Login cancelled by user.", style="yellow")
        raise typer.Exit(0)
    except typer.Exit:
        # Re-raise typer.Exit to avoid catching it as a generic exception
        raise
    except Exception as e:
        _handle_error(str(e))
        raise typer.Exit(1)

