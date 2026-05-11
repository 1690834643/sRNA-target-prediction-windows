from pathlib import Path

from srna_win_target.core.models import ToolConfig
from srna_win_target.tools.base import RawToolOutput
from srna_win_target.tools.rnahybrid import RNAhybridRunner


def test_rnahybrid_parse_output_reads_golden_file():
    golden = Path(__file__).parent / "golden" / "rnahybrid" / "sample.txt"
    raw = RawToolOutput(
        tool_name="rnahybrid",
        chunk_id="chunk0",
        stdout="",
        stderr="",
        output_file=golden,
        returncode=0,
    )
    runner = RNAhybridRunner(ToolConfig(name="rnahybrid", executable=Path("/bin/true")))

    hits = runner.parse_output(raw)

    assert len(hits) == 3
    assert hits[0].mirna_id == "hsa-miR-1"
    assert hits[0].target_id == "NM_001"
    assert hits[0].energy == -24.5
    assert hits[0].tool == "rnahybrid"
    assert hits[0].chunk_id == "chunk0"
    assert hits[0].raw_file == golden
    assert hits[-1].mirna_id == "hsa-miR-3"
    assert hits[-1].target_id == "NM_003"
    assert hits[-1].start == 450
    assert hits[-1].pvalue == 0.001
    assert hits[-1].score is None
    assert hits[-1].end is None
    assert hits[-1].tool == "rnahybrid"
    assert hits[-1].chunk_id == "chunk0"
    assert hits[-1].raw_file == golden
