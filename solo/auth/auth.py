"""
Authentication utilities for Solo CLI using device code flow.
"""

import os
import json
import time
import requests
from typing import Optional, Dict, Callable
from solo.config import CONFIG_DIR

# API Configuration
API_ENV = os.getenv('SOLO_API_ENV', 'prod')
API_BASE_URLS = {
    'prod': 'https://hub.getsolo.tech',
    'dev': 'https://devhub.getsolo.tech'
}
API_BASE_URL = API_BASE_URLS.get(API_ENV, API_BASE_URLS['prod'])

# Auth file path
AUTH_FILE = os.path.join(CONFIG_DIR, 'auth.json')


def _handle_request_error(e: Exception, default_msg: str) -> Exception:
    """Consolidate request error handling."""
    if isinstance(e, requests.exceptions.Timeout):
        return Exception("Request timed out. Please check your internet connection and try again.")
    elif isinstance(e, requests.exceptions.ConnectionError):
        return Exception("Failed to connect to authentication server. Please check your internet connection.")
    elif isinstance(e, requests.exceptions.HTTPError):
        if e.response is not None:
            status_code = e.response.status_code
            if status_code == 500:
                return Exception("Authentication server error. Please try again later.")
            elif status_code == 401:
                return Exception("Unauthorized. Please check your API configuration.")
            return Exception(f"HTTP error {status_code}: {default_msg}")
        return Exception(f"HTTP error: {default_msg}")
    elif isinstance(e, json.JSONDecodeError):
        return Exception("Invalid response from authentication server.")
    else:
        return Exception(f"{default_msg}: {str(e)}")


def generate_device_code() -> Dict:
    """
    Generate device code for authentication flow.
    
    Returns:
        dict: Response containing deviceCode, userCode, token, expires_in, intervals, verification_url
        
    Raises:
        Exception: If the API request fails with detailed error message
    """
    url = f"{API_BASE_URL}/api/v1/internal/device-code"
    
    try:
        response = requests.post(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        raise _handle_request_error(e, "Failed to generate device code")


def poll_for_token(device_code: str, expires_in: int, intervals: int, progress_callback: Optional[Callable[[int, int], None]] = None) -> Optional[Dict]:
    """
    Poll for device token after user authorization.
    
    Args:
        device_code: The device code from generate_device_code
        expires_in: Expiration time in milliseconds
        intervals: Polling interval in seconds
        progress_callback: Optional callback(elapsed, remaining) called on each poll
        
    Returns:
        dict: Token response with token, userCode, expires_in, user info, or None if timeout
        
    Raises:
        Exception: If the API request fails with specific error messages
    """
    url = f"{API_BASE_URL}/api/v1/internal/device-token"
    payload = {"deviceCode": device_code}
    
    # Convert expires_in from milliseconds to seconds
    timeout_seconds = expires_in / 1000
    start_time = time.time()
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    while time.time() - start_time < timeout_seconds:
        # Call progress callback if provided
        if progress_callback:
            elapsed = int(time.time() - start_time)
            remaining = int(timeout_seconds - elapsed)
            progress_callback(elapsed, remaining)
        try:
            response = requests.post(url, json=payload, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", "")
                    error_lower = error_msg.lower().replace(":", "").replace("_", "").replace(" ", "")
                    
                    # Only stop immediately if code is already used (can't recover)
                    if "alreadyused" in error_lower:
                        raise Exception("Device code has already been used. Please generate a new code.")
                    
                    # For all other 400 errors (like "ERROR: createTokenForDevice"), 
                    # continue polling - these are normal responses before user enters code
                    # The backend will return 200 once user enters the code, or we'll timeout naturally
                    consecutive_errors = 0  # Reset error count on expected 400
                except json.JSONDecodeError:
                    # If we can't parse JSON, continue polling (might be temporary)
                    consecutive_errors = 0
            elif response.status_code == 404:
                # Device code not found yet, continue polling (this is expected)
                consecutive_errors = 0  # Reset error count on expected 404
            elif response.status_code == 500:
                # Server error, retry with exponential backoff
                consecutive_errors += 1
                if consecutive_errors >= max_consecutive_errors:
                    raise Exception("Authentication server error. Please try again later.")
                backoff_time = min(intervals * (2 ** min(consecutive_errors, 3)), 30)
                time.sleep(backoff_time)
                continue
            else:
                response.raise_for_status()
                
        except requests.exceptions.Timeout:
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                raise Exception("Request timed out. Please check your internet connection.")
            # Continue polling after timeout
        except requests.exceptions.ConnectionError:
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                raise Exception("Failed to connect to authentication server. Please check your internet connection.")
            # Continue polling after connection error
        except requests.exceptions.HTTPError as e:
            # For other HTTP errors, raise immediately
            if e.response is not None:
                status_code = e.response.status_code
                raise Exception(f"HTTP error {status_code}: Authentication failed.")
            raise Exception("HTTP error: Authentication failed.")
        except Exception as e:
            error_str = str(e).lower()
            # Re-raise known exceptions that should stop immediately
            if "already used" in error_str:
                raise
            # For other exceptions, log and continue polling
            consecutive_errors += 1
            if consecutive_errors >= max_consecutive_errors:
                raise Exception(f"Unexpected error during authentication: {str(e)}")
        
        # Wait before next poll
        time.sleep(intervals)
    
    # Timeout reached
    return None


def get_stored_token() -> Optional[Dict]:
    """
    Get stored authentication token from auth.json.
    
    Returns:
        dict: Token data including token, user info, expires_at, created_at, or None if not found
    """
    if not os.path.exists(AUTH_FILE):
        return None
    
    try:
        with open(AUTH_FILE, 'r') as f:
            auth_data = json.load(f)
            # Validate token structure
            if not isinstance(auth_data, dict):
                return None
            if 'token' not in auth_data:
                return None
            return auth_data
    except (json.JSONDecodeError, FileNotFoundError, IOError, OSError):
        return None


def save_token(token_data: Dict) -> None:
    """
    Save authentication token to auth.json.
    
    Args:
        token_data: Token response from poll_for_token containing token, user, expires_in
    """
    # Ensure config directory exists
    os.makedirs(os.path.dirname(AUTH_FILE), exist_ok=True)
    
    # Calculate expiration timestamp
    expires_in = token_data.get('expires_in', 0)
    current_time = int(time.time())
    
    # Handle edge cases for expiration
    # If expires_in is negative, zero, or missing, set a reasonable default (30 days)
    if expires_in <= 0:
        expires_in = 30 * 24 * 60 * 60  # 30 days in seconds
    
    auth_data = {
        'token': token_data.get('token'),
        'user': token_data.get('user', {}),
        'expires_at': current_time + expires_in,
        'created_at': current_time
    }
    
    try:
        with open(AUTH_FILE, 'w') as f:
            json.dump(auth_data, f, indent=2)
    except (IOError, OSError) as e:
        raise Exception(f"Failed to save authentication token: {str(e)}")


def is_authenticated() -> bool:
    """
    Check if user is authenticated with a valid token.
    
    Returns:
        bool: True if valid token exists and hasn't expired
    """
    try:
        auth_data = get_stored_token()
        if not auth_data:
            return False
        
        # Check if token exists and is not empty
        token = auth_data.get('token')
        if not token or not isinstance(token, str) or len(token.strip()) == 0:
            return False
        
        # Check expiration
        expires_at = auth_data.get('expires_at', 0)
        current_time = int(time.time())
        
        # If expires_at is 0, token doesn't expire (treat as valid)
        if expires_at == 0:
            return True
        
        # Check if token has expired
        if expires_at > 0 and current_time >= expires_at:
            return False
        
        return True
    except Exception:
        # If any error occurs during validation, assume not authenticated
        return False


def get_auth_token() -> Optional[str]:
    """
    Get the current authentication token (optimized to read file once).
    
    Returns:
        str: The authentication token, or None if not authenticated
    """
    # Use is_authenticated to ensure consistency
    if not is_authenticated():
        return None
    
    auth_data = get_stored_token()
    if not auth_data:
        return None
    
    return auth_data.get('token')


def clear_auth_token() -> None:
    """Clear the stored authentication token."""
    if os.path.exists(AUTH_FILE):
        os.remove(AUTH_FILE)

