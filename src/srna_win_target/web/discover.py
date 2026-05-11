"""Auto-discovery of bundled tool binaries next to the executable.

In the portable Windows release the on-disk layout is:

    srna-win-target-portable/
    ├── srna-win-target-web.exe
    ├── bundled_tools/
    │   ├── miranda/miranda.exe
    │   ├── rnahybrid/RNAhybrid.exe
    │   └── pita/{pita_prediction.pl, perl/bin/perl.exe, RNAduplex.exe, lib/}
    └── examples/input/{mirna.fa, targets.fa}

This module is the single source of truth that figures out where the app is
running from (frozen exe vs source checkout) and which tools are ready.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class DiscoveredTool:
    name: str
    ready: bool
    executable: Optional[Path] = None
    script: Optional[Path] = None
    bundled_perl: Optional[Path] = None
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "ready": self.ready,
            "executable": str(self.executable) if self.executable else None,
            "script": str(self.script) if self.script else None,
            "bundled_perl": str(self.bundled_perl) if self.bundled_perl else None,
            "reason": self.reason,
        }


def get_app_dir() -> Path:
    """Directory that should contain bundled_tools/ and examples/.

    - PyInstaller frozen: parent of the running executable.
    - Source checkout: repo root (four levels up from this file).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[3]


def _candidate_names(stem: str) -> list[str]:
    if sys.platform.startswith("win"):
        return [f"{stem}.exe", stem]
    return [stem, f"{stem}.exe"]


def _find_executable(root: Path, stems: list[str]) -> Optional[Path]:
    if not root.is_dir():
        return None
    for stem in stems:
        for name in _candidate_names(stem):
            candidate = root / name
            if candidate.is_file():
                return candidate
    return None


def discover_bundled_tools(app_dir: Optional[Path] = None) -> dict[str, DiscoveredTool]:
    """Scan <app_dir>/bundled_tools/<tool>/ and return status per known tool.

    Always returns all three keys (miranda/rnahybrid/pita); a tool that is
    not yet bundled simply comes back with `ready=False` and a reason.
    """
    app_dir = app_dir or get_app_dir()
    bundled = app_dir / "bundled_tools"

    result: dict[str, DiscoveredTool] = {}

    miranda_dir = bundled / "miranda"
    miranda_exe = _find_executable(miranda_dir, ["miranda"])
    if miranda_exe:
        result["miranda"] = DiscoveredTool(
            name="miranda", ready=True, executable=miranda_exe
        )
    else:
        result["miranda"] = DiscoveredTool(
            name="miranda",
            ready=False,
            reason=f"no miranda binary under {miranda_dir}",
        )

    rh_dir = bundled / "rnahybrid"
    rh_exe = _find_executable(rh_dir, ["RNAhybrid", "rnahybrid"])
    if rh_exe:
        result["rnahybrid"] = DiscoveredTool(
            name="rnahybrid", ready=True, executable=rh_exe
        )
    else:
        result["rnahybrid"] = DiscoveredTool(
            name="rnahybrid",
            ready=False,
            reason=f"no RNAhybrid binary under {rh_dir}",
        )

    pita_dir = bundled / "pita"
    pita_script = pita_dir / "pita_prediction.pl"
    pita_perl = _find_executable(pita_dir / "perl" / "bin", ["perl"])
    pita_rnaduplex = _find_executable(pita_dir, ["RNAduplex"])
    # PITA v2 (patched Vienna-1.6) needs RNAddG4 + default.par to compute real ΔG.
    # Without these, RNAddG_compute.pl falls back to -1 placeholders silently.
    pita_rnaddg4 = _find_executable(pita_dir, ["RNAddG4"])
    pita_paramfile = pita_dir / "default.par"
    missing: list[str] = []
    if not pita_dir.is_dir():
        missing.append(str(pita_dir))
    else:
        if not pita_script.is_file():
            missing.append("pita_prediction.pl")
        if pita_perl is None:
            missing.append("perl/bin/perl(.exe)")
        if pita_rnaduplex is None:
            missing.append("RNAduplex(.exe)")
        if pita_rnaddg4 is None:
            missing.append("RNAddG4(.exe) — ΔG would be -1 fallback")
        if not pita_paramfile.is_file():
            missing.append("default.par — ΔG would be -1 fallback")
    if not missing:
        result["pita"] = DiscoveredTool(
            name="pita",
            ready=True,
            script=pita_script,
            bundled_perl=pita_perl,
        )
    else:
        result["pita"] = DiscoveredTool(
            name="pita",
            ready=False,
            reason="missing: " + ", ".join(missing),
        )

    return result


def default_output_dir() -> Path:
    """A sensible per-OS default landing zone for results.

    Windows: %USERPROFILE%\\Desktop\\srna-target-results
    POSIX:   $HOME/srna-target-results
    """
    if sys.platform.startswith("win"):
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            desktop = Path(userprofile) / "Desktop"
            if desktop.is_dir():
                return desktop / "srna-target-results"
            return Path(userprofile) / "srna-target-results"
    desktop = Path.home() / "Desktop"
    if desktop.is_dir():
        return desktop / "srna-target-results"
    return Path.home() / "srna-target-results"


def example_inputs(app_dir: Optional[Path] = None) -> Optional[dict[str, Path]]:
    """Return paths to the bundled examples/input/{mirna.fa,targets.fa}, if present."""
    app_dir = app_dir or get_app_dir()
    examples = app_dir / "examples" / "input"
    mirna = examples / "mirna.fa"
    targets = examples / "targets.fa"
    if mirna.is_file() and targets.is_file():
        return {"mirna": mirna, "targets": targets}
    return None


def environment_summary() -> dict:
    """Pack everything the front-end needs on first paint into one payload."""
    app_dir = get_app_dir()
    tools = discover_bundled_tools(app_dir)
    examples = example_inputs(app_dir)
    return {
        "app_dir": str(app_dir),
        "frozen": bool(getattr(sys, "frozen", False)),
        "platform": sys.platform,
        "tools": {name: t.to_dict() for name, t in tools.items()},
        "ready_count": sum(1 for t in tools.values() if t.ready),
        "total_count": len(tools),
        "default_output_dir": str(default_output_dir()),
        "examples": (
            {k: str(v) for k, v in examples.items()} if examples else None
        ),
    }
