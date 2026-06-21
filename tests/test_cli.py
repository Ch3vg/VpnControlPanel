from __future__ import annotations

import shutil
import subprocess
import sys

import pytest


@pytest.mark.parametrize(
    ("module",),
    [
        ("panel.api.main",),
        ("broker_run.main",),
        ("panel.worker.main",),
        ("panel.cli.create_admin",),
    ],
)
def test_cli_help(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", module, "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout.lower()


@pytest.mark.parametrize("command", ["vpn-api", "vpn-broker", "vpn-worker", "vpn-create-admin"])
def test_installed_entrypoint_help(command: str) -> None:
    exe = shutil.which(command)
    if exe is None:
        pytest.skip(f"{command} not installed in PATH")
    result = subprocess.run([exe, "--help"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
