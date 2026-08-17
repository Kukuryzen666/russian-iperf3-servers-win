#!/usr/bin/env bash
set -e

# Russian iPerf3 SpeedTest — Bash One-Liner Runner
if ! command -v python3 &> /dev/null; then
    echo -e "\033[31m[!] Python 3 is required but not installed.\033[0m"
    exit 1
fi

# Ensure rich is installed
python3 -c "import rich" 2>/dev/null || {
    echo -e "\033[36m[*] Installing 'rich' library...\033[0m"
    python3 -m pip install --quiet rich
}

TMP_SCRIPT=$(mktemp /tmp/speedtest_XXXXXX.py)
curl -fsSL https://raw.githubusercontent.com/Kukuryzen666/russian-iperf3-servers-win/main/speedtest.py -o "$TMP_SCRIPT"
python3 "$TMP_SCRIPT" "$@"
rm -f "$TMP_SCRIPT"
