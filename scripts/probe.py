"""Bounded SSH check; metadata and diagnostics require --details."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

# User-adjustable defaults; host/account/key configuration lives in OpenSSH config.
CONNECT_TIMEOUT_SECONDS = 15
TOTAL_TIMEOUT_SECONDS = 45
SAFE_OPTIONS = [
    "ForwardAgent=no", "ForwardX11=no", "ClearAllForwardings=yes",
    "PermitLocalCommand=no", "ControlMaster=no", "ControlPath=none",
    "ControlPersist=no", "RequestTTY=no", "Tunnel=no", "GSSAPIDelegateCredentials=no",
]
PROBE = """set -eu
printf 'user='; id -un
printf 'host='; hostname
printf 'kernel='; uname -s
printf 'home=%s\\n' "$HOME"
for tool in bash python3 sbatch squeue sacct qsub qstat vasp_std vasp_gam vasp_ncl vaspkit; do
    if location=$(command -v "$tool" 2>/dev/null); then
        printf '%s=%s\\n' "$tool" "$location"
    else
        printf '%s=not_on_PATH\\n' "$tool"
    fi
done
"""


def ssh_command(alias, config=None):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", alias):
        raise ValueError("Use an SSH config alias containing letters, digits, _, . or -.")
    config_args = []
    if config is not None:
        config_path = Path(config).expanduser().resolve(strict=True)
        if not config_path.is_file():
            raise ValueError("SSH config must be a file.")
        config_args = ["-F", str(config_path)]
    return ["ssh", *config_args, "-T", *[arg for opt in SAFE_OPTIONS for arg in ("-o", opt)],
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", f"ConnectTimeout={CONNECT_TIMEOUT_SECONDS}",
            "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=2",
            alias, "sh", "-s"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("alias", help="Existing SSH config alias; never a password")
    parser.add_argument("--dry-run", action="store_true", help="Print command; do not connect")
    parser.add_argument("--config", help="Explicit trusted OpenSSH config, useful in Windows sandbox")
    parser.add_argument("--details", action="store_true", help="Expose remote identity, paths and SSH diagnostics")
    args = parser.parse_args(argv)
    try:
        command = ssh_command(args.alias, args.config)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    payload = PROBE if args.details else "true\n"
    if args.dry_run:
        print(json.dumps({"argv": command, "stdin": payload}, indent=2))
        return 0
    try:
        result = subprocess.run(command, input=payload.encode("utf-8"),
                                stdout=None if args.details else subprocess.DEVNULL,
                                stderr=None if args.details else subprocess.DEVNULL,
                                timeout=TOTAL_TIMEOUT_SECONDS, check=False)
    except FileNotFoundError:
        print("OpenSSH client not found on PATH.", file=sys.stderr)
        return 127
    except subprocess.TimeoutExpired:
        print("SSH probe timed out; check VPN, routing, authentication or remote shell.",
              file=sys.stderr)
        return 124
    if result.returncode:
        print("SSH check failed; diagnose in the local onboarding terminal before writes.", file=sys.stderr)
    else:
        print("SSH authentication verified.")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
