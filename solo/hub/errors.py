class SoloHubError(Exception):
    """Base exception for Solo Hub operations."""


class SoloAuthError(SoloHubError):
    """Raised when authentication fails or token is missing/expired."""


class SoloModelNotFoundError(SoloHubError):
    """Raised when a model identifier cannot be resolved."""


class SoloDownloadError(SoloHubError):
    """Raised when file download from presigned URL fails."""
