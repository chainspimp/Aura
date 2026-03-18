#!/usr/bin/env bash
# =============================================================================
# AURA v2 — Linux / macOS Setup Script
# Usage:  bash setup_unix.sh
# =============================================================================

set -e
PYTHON=${PYTHON:-python3}
PIP=${PIP:-pip3}

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║       AURA v2 — Unix Setup Script        ║"
echo "╚══════════════════════════════════════════╝"
echo ""

OS=$(uname -s)
echo "Detected OS: $OS"
echo ""

# ── 1. System dependencies ────────────────────────────────────────────────────
echo "━━━ [1/5] Installing system dependencies ━━━"

if [[ "$OS" == "Linux" ]]; then
    if command -v apt-get &>/dev/null; then
        echo "→ Using apt-get (Debian/Ubuntu)"
        sudo apt-get update -q
        sudo apt-get install -y \
            portaudio19-dev \
            python3-dev \
            espeak-ng \
            ffmpeg \
            scrot \
            pkg-config \
            libssl-dev \
            libffi-dev
    elif command -v dnf &>/dev/null; then
        echo "→ Using dnf (Fedora/RHEL)"
        sudo dnf install -y \
            portaudio-devel \
            python3-devel \
            espeak-ng \
            ffmpeg \
            scrot
    elif command -v pacman &>/dev/null; then
        echo "→ Using pacman (Arch)"
        sudo pacman -S --noconfirm \
            portaudio \
            python \
            espeak-ng \
            ffmpeg \
            scrot
    else
        echo "⚠️  Unknown package manager — skipping system deps. Install manually:"
        echo "   portaudio-dev, espeak-ng, ffmpeg, scrot"
    fi
elif [[ "$OS" == "Darwin" ]]; then
    echo "→ Using Homebrew (macOS)"
    if ! command -v brew &>/dev/null; then
        echo "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install portaudio espeak ffmpeg
fi

echo "✅ System dependencies done"
echo ""

# ── 2. Python dependencies ────────────────────────────────────────────────────
echo "━━━ [2/5] Installing Python packages ━━━"
$PIP install --upgrade pip
$PIP install -r requirements_updated.txt
echo "✅ Python packages done"
echo ""

# ── 3. Playwright browsers ────────────────────────────────────────────────────
echo "━━━ [3/5] Installing Playwright browsers ━━━"
$PYTHON -m playwright install chromium
echo "✅ Playwright done"
echo ""

# ── 4. Vosk model ─────────────────────────────────────────────────────────────
echo "━━━ [4/5] Checking Vosk speech model ━━━"
VOSK_DIR="vosk-model-small-en-us-0.15"
if [ ! -d "$VOSK_DIR" ]; then
    echo "→ Downloading Vosk small English model (~40MB)..."
    curl -LO "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    unzip -q vosk-model-small-en-us-0.15.zip
    rm vosk-model-small-en-us-0.15.zip
    echo "✅ Vosk model downloaded: $VOSK_DIR"
else
    echo "✅ Vosk model already present: $VOSK_DIR"
fi
echo ""

# ── 5. Piper TTS ──────────────────────────────────────────────────────────────
echo "━━━ [5/5] Checking Piper TTS ━━━"
PIPER_DIR="$HOME/.local/share/piper"
if ! command -v piper &>/dev/null && [ ! -f "$PIPER_DIR/piper" ]; then
    mkdir -p "$PIPER_DIR/voices"
    echo "→ Downloading Piper TTS binary..."
    if [[ "$OS" == "Darwin" ]]; then
        PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_macos_x64.tar.gz"
    else
        PIPER_URL="https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_linux_x86_64.tar.gz"
    fi
    curl -L "$PIPER_URL" | tar -xz -C "$PIPER_DIR"
    chmod +x "$PIPER_DIR/piper"

    echo "→ Downloading default voice model (hfc_female)..."
    VOICE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/hfc_female/medium/en_US-hfc_female-medium.onnx"
    curl -L "$VOICE_URL" -o "$PIPER_DIR/voices/en_US-hfc_female-medium.onnx"

    # Add to PATH
    if [[ ":$PATH:" != *":$PIPER_DIR:"* ]]; then
        echo "export PATH=\"$PIPER_DIR:\$PATH\"" >> ~/.bashrc
        echo "export PATH=\"$PIPER_DIR:\$PATH\"" >> ~/.zshrc 2>/dev/null || true
    fi

    # Add to .env
    echo "PIPER_PATH=$PIPER_DIR/piper" >> .env
    echo "PIPER_MODEL=$PIPER_DIR/voices/en_US-hfc_female-medium.onnx" >> .env
    echo "✅ Piper TTS installed: $PIPER_DIR"
else
    echo "✅ Piper TTS already available"
fi
echo ""

# ── Verify ─────────────────────────────────────────────────────────────────────
echo "━━━ Dependency verification ━━━"
$PYTHON platform_compat.py
echo ""

echo "╔══════════════════════════════════════════╗"
echo "║              Setup complete!             ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Launch AURA:  python main_gui.py        ║"
echo "║                                          ║"
echo "║  Optional: add to .env                   ║"
echo "║    TELEGRAM_TOKEN=<your_bot_token>       ║"
echo "║    TELEGRAM_ALLOWED_IDS=<your_user_id>   ║"
echo "╚══════════════════════════════════════════╝"
echo ""
