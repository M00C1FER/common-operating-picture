## Recommended Tools

### Core Runtime

| Tool | Purpose | Install |
|------|---------|---------|
| [Python 3.10+](https://python.org) | Runtime | `apt install python3` / `pkg install python` |
| [pip](https://pip.pypa.io) | Package manager | Bundled with Python 3.10+ |
| [git](https://git-scm.com) | Version control | `apt install git` / `pkg install git` |
| [uv](https://github.com/astral-sh/uv) | Faster pip + venv | `pip install uv` |

### Development Tools

| Tool | Purpose | Install |
|------|---------|---------|
| [ruff](https://github.com/astral-sh/ruff) | Fast Python linter + formatter | `pip install ruff` |
| [mypy](https://mypy-lang.org) | Static type checking | `pip install mypy` |
| [pytest](https://pytest.org) | Test framework | `pip install pytest` |
| [pytest-cov](https://pytest-cov.readthedocs.io) | Coverage reports | `pip install pytest-cov` |

### Installation Walkthrough

#### Linux / WSL
```bash
# 1. Ensure Python 3.10+
python3 --version

# 2. Clone and install
git clone https://github.com/M00C1FER/common-operating-picture
cd common-operating-picture
bash install.sh

# 3. Verify
cop --version
```

#### Termux (Android)
```bash
# 1. Update and install deps (no sudo needed)
pkg update && pkg install python git

# 2. Clone and install
git clone https://github.com/M00C1FER/common-operating-picture
cd common-operating-picture
bash install.sh

# 3. Add to PATH if needed
export PATH="$HOME/.local/bin:$PATH"
```

#### Manual pip install
```bash
git clone https://github.com/M00C1FER/common-operating-picture
cd common-operating-picture
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

### Optional Integrations

| Tool | Purpose | Install |
|------|---------|---------|
| [jq](https://stedolan.github.io/jq/) | Parse JSON output in shell scripts | `apt install jq` |
| [yq](https://github.com/mikefarah/yq) | Parse YAML configs | `pip install yq` |
| [rich](https://rich.readthedocs.io) | Prettier terminal output | `pip install rich` |

