"""Offline check: python -B TEST/test_probe.py. Does not contact any server."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "probe", Path(__file__).resolve().parents[1] / "scripts" / "probe.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

template = json.loads((Path(__file__).resolve().parents[1] / "assets" /
                       "profile.example.json").read_text(encoding="utf-8"))
for field in ("alias", "host", "port", "user", "ssh_config_file", "identity_file",
              "proxy_jump", "verified_host_key_sha256", "remote_work_root"):
    assert template[field] is None, f"Connection field must be supplied by user: {field}"
assert template["authorization"]["confirmed_at"] is None
assert template["authorization"]["user_statement"] is None
assert template["workspaces"] == []
assert template["connection_privacy"] == "alias_only"
assert template["installation_approvals"] == []
preferences = json.loads((Path(__file__).resolve().parents[1] / "assets" /
                          "preferences.example.json").read_text(encoding="utf-8"))
assert preferences["memory_consent"]["enabled"] is False
assert preferences["memory_consent"]["confirmed_at"] is None
assert preferences["memory_consent"]["user_statement"] is None
assert preferences["preferences"] == []

assert probe.ssh_command("vasp-cluster")[-3:] == ["vasp-cluster", "sh", "-s"]
with tempfile.TemporaryDirectory() as folder:
    config = Path(folder) / "ssh config"
    config.write_text("Host vasp-cluster\n  HostName example.invalid\n", encoding="utf-8")
    assert probe.ssh_command("vasp-cluster", config)[1:3] == ["-F", str(config.resolve())]
    try:
        probe.ssh_command("vasp-cluster", Path(folder) / "missing")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("Missing explicit config accepted")
for alias in ["", "-oProxyCommand=bad", "host;id", "host\nother", "user@host", "a b"]:
    try:
        probe.ssh_command(alias)
    except ValueError:
        pass
    else:
        raise AssertionError(f"Unsafe alias accepted: {alias!r}")

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    with patch.object(probe.subprocess, "run") as run:
        assert probe.main(["vasp-cluster", "--dry-run"]) == 0
        run.assert_not_called()
    with patch.object(probe.subprocess, "run") as run:
        run.return_value.returncode = 0
        assert probe.main(["vasp-cluster"]) == 0
        args, kwargs = run.call_args
        assert "BatchMode=yes" in args[0] and "StrictHostKeyChecking=yes" in args[0]
        assert kwargs["input"] == b"true\n"
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        for option in probe.SAFE_OPTIONS:
            assert option in args[0]
        assert b"\r" not in kwargs["input"]
        assert kwargs["timeout"] == probe.TOTAL_TIMEOUT_SECONDS
        assert not kwargs.get("shell", False)
        run.return_value.returncode = 255
        assert probe.main(["vasp-cluster"]) == 255
        run.return_value.returncode = 0
        assert probe.main(["vasp-cluster", "--details"]) == 0
        assert run.call_args.kwargs["input"] == probe.PROBE.encode("utf-8")
        assert run.call_args.kwargs["stdout"] is None
        assert run.call_args.kwargs["stderr"] is None
    for error, expected in [(FileNotFoundError(), 127),
                            (subprocess.TimeoutExpired("ssh", 45), 124)]:
        with patch.object(probe.subprocess, "run", side_effect=error):
            assert probe.main(["vasp-cluster"]) == expected

print("PASS: alias validation, dry-run isolation, SSH options, LF input, failures and timeout")
