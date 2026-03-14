## Prerequisites

### 1. Git LFS

Git LFS is required to install solo-cli's robotics dependencies. Install it before proceeding:

```bash
# Mac
brew install git-lfs

# Ubuntu / Debian
sudo apt-get install git-lfs

# Windows (pick one)
winget install GitHub.GitLFS
# or download the installer from https://git-lfs.com
```

Then run once to set up the hooks:

```bash
git lfs install
```

### 2. uv Package Manager

```bash
# Mac & Linux
curl -LsSf https://astral.sh/uv/install.sh | sh  
# Windows Powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. Python Virtual Environment

```bash
# Create virtual environment (recommended Python 3.12)
uv venv --python 3.12
# Mac & Linux
source .venv/bin/activate
# Windows
source .venv/scripts/activate
```