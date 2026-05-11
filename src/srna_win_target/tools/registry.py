from __future__ import annotations

from srna_win_target.core.models import ToolConfig
from srna_win_target.tools.base import ToolRunner
from srna_win_target.tools.intarna import IntaRNARunner
from srna_win_target.tools.miranda import MirandaRunner
from srna_win_target.tools.pita import PitaRunner
from srna_win_target.tools.rnahybrid import RNAhybridRunner

RUNNERS: dict[str, type[ToolRunner]] = {
    "miranda": MirandaRunner,
    "rnahybrid": RNAhybridRunner,
    "pita": PitaRunner,
    "intarna": IntaRNARunner,
}


def build_runner(config: ToolConfig) -> ToolRunner:
    try:
        runner_cls = RUNNERS[config.name]
    except KeyError as exc:
        raise ValueError(f"Unsupported tool: {config.name}") from exc
    return runner_cls(config)
