import os

# API base URL
SOLO_HUB_DEFAULT_URL = "https://hub.getsolo.tech"
SOLO_HUB_API_BASE = os.environ.get("SOLO_HUB_URL", SOLO_HUB_DEFAULT_URL)

# Local paths
SOLO_CONFIG_DIR = os.path.expanduser("~/.solo")
SOLO_TOKEN_PATH = os.path.join(SOLO_CONFIG_DIR, "token")
SOLO_USER_PATH = os.path.join(SOLO_CONFIG_DIR, "user.json")
SOLO_CACHE_DIR = os.path.join(SOLO_CONFIG_DIR, "hub")

# Identifier prefixes
SOLO_PREFIX = "solo:"
SOLO_URL_PREFIX = "solo://"

# Repo ID separator for cache directory names
REPO_ID_SEPARATOR = "--"

# API endpoints
DEVICE_CODE_ENDPOINT = "/api/v1/internal/device-code"
DEVICE_TOKEN_ENDPOINT = "/api/v1/internal/device-token"
MODEL_INFO_ENDPOINT = "/api/v1/internal/models/{identifier}"
MODEL_LIST_ENDPOINT = "/api/v1/internal/models"
MODEL_FILES_ENDPOINT = "/api/v1/org/{org_id}/model/{model_id}/files"
USER_PROFILE_ENDPOINT = "/api/v1/user/my-profile"
