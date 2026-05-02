#!/usr/bin/env bash
# Common Operating Picture — install wizard
# Supports: Linux, WSL, Termux (Android)
set -euo pipefail

BLUE='\033[0;34m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR]${NC}   $*"; exit 1; }
prompt()  { echo -e "${YELLOW}[INPUT]${NC} $*"; }

detect_platform() {
    if [ -n "${TERMUX_VERSION:-}" ] || [ -d "/data/data/com.termux" ]; then echo "termux"
    elif grep -qi microsoft /proc/version 2>/dev/null; then echo "wsl"
    else echo "linux"; fi
}

install_deps_system() {
    local plat="$1"
    info "Installing system dependencies ($plat)..."
    case "$plat" in
        termux)
            pkg update -y
            pkg install -y python git
            ;;
        wsl|linux)
            if command -v apt-get &>/dev/null; then
                sudo apt-get update -qq
                sudo apt-get install -y python3 python3-venv python3-pip git
            elif command -v dnf &>/dev/null; then
                sudo dnf install -y python3 python3-virtualenv git
            elif command -v pacman &>/dev/null; then
                sudo pacman -Sy --noconfirm python git
            fi
            ;;
    esac
}

PLATFORM=$(detect_platform)
INSTALL_DIR="${HOME}/.local/share/common-operating-picture"
VENV_DIR="${INSTALL_DIR}/.venv"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║    Common Operating Picture  v1.0.0      ║"
echo "║   Shared state bus for multi-agent ops   ║"
echo "╚══════════════════════════════════════════╝"
echo ""
info "Platform detected: $PLATFORM"

install_deps_system "$PLATFORM"

mkdir -p "$INSTALL_DIR"
if [ "$PLATFORM" = "termux" ]; then
    python -m venv "$VENV_DIR"
else
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install . -q

ENV_FILE="${INSTALL_DIR}/.env"
touch "$ENV_FILE"
chmod 600 "$ENV_FILE"

echo ""
echo "────────────────────────────────────────────"
echo " Credential & Path Configuration"
echo "────────────────────────────────────────────"

prompt "COP state file path (default: ~/.local/share/common-operating-picture/cop_state.json):"
read -r cop_state_path
if [ -n "$cop_state_path" ]; then
    echo "COP_STATE_FILE=${cop_state_path}" >> "$ENV_FILE"
fi

prompt "COP home directory (default: ~/.local/share/common-operating-picture):"
read -r cop_home
if [ -n "$cop_home" ]; then
    echo "COP_HOME=${cop_home}" >> "$ENV_FILE"
fi

success "Config saved to $ENV_FILE"

WRAPPER="${HOME}/.local/bin/cop"
mkdir -p "$(dirname "$WRAPPER")"
cat > "$WRAPPER" << WRAPEOF
#!/usr/bin/env bash
set -a; [ -f "${ENV_FILE}" ] && . "${ENV_FILE}"; set +a
exec "${VENV_DIR}/bin/cop" "\$@"
WRAPEOF
chmod +x "$WRAPPER"

echo ""
success "Installation complete!"
echo ""
echo "  Usage:  cop --help"
echo "  Config: $ENV_FILE"
echo "  Docs:   https://github.com/M00C1FER/common-operating-picture"
