#!/usr/bin/env bash
# One-time setup of the Digit Defender Android build box (an Ubuntu WSL distro
# on D:, run as root by android/sync.py setup). Installs the buildozer /
# python-for-android toolchain. Idempotent: a marker file skips a second run.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
MARK=/root/.dd-setup-done
if [ -f "$MARK" ]; then
    echo "build box already set up ($(cat "$MARK")) - delete $MARK to redo"
    exit 0
fi
echo "== apt packages =="
apt-get update
apt-get install -y --no-install-recommends \
    git zip unzip openjdk-17-jdk-headless \
    python3 python3-pip python3-venv python3-setuptools python3-dev \
    autoconf automake libtool libltdl-dev pkg-config zlib1g-dev libncurses-dev cmake \
    libffi-dev libssl-dev build-essential ccache rsync patch curl wget \
    ca-certificates lsb-release file
echo "== pip: buildozer + cython =="
# Ubuntu 24.04 pip refuses system installs unless told so (PEP 668)
export PIP_BREAK_SYSTEM_PACKAGES=1
python3 -m pip install --user --upgrade pip
python3 -m pip install --user --upgrade buildozer cython virtualenv
if ! grep -q PIP_BREAK_SYSTEM_PACKAGES /root/.bashrc; then
    cat >> /root/.bashrc <<'EOF'
export PIP_BREAK_SYSTEM_PACKAGES=1
export PATH="$HOME/.local/bin:$PATH"
EOF
fi
export PATH="$HOME/.local/bin:$PATH"
buildozer --version
date > "$MARK"
echo "== build box ready =="
