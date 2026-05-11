from pathlib import Path

from srna_win_target.core.models import ToolConfig
from srna_win_target.tools.base import RawToolOutput
from srna_win_target.tools.pita import PitaRunner


def test_pita_parse_output_reads_golden_file():
    golden = Path(__file__).parent / "golden" / "pita" / "sample_pita_results.tab"
    raw = RawToolOutput(
        tool_name="pita",
        chunk_id="chunk0",
        stdout="",
        stderr="",
        output_file=golden,
        returncode=0,
    )
    runner = PitaRunner(ToolConfig(name="pita", executable=Path("/bin/true")))

    hits = runner.parse_output(raw)

    assert len(hits) == 3
    assert hits[0].mirna_id == "hsa-miR-1"
    assert hits[0].target_id == "NM_001"
    assert hits[0].score == -7.25
    assert hits[0].start == 105
    assert hits[0].tool == "pita"
    assert hits[0].chunk_id == "chunk0"
    assert hits[0].raw_file == golden
    assert hits[-1].mirna_id == "hsa-miR-3"
    assert hits[-1].target_id == "NM_003"
    assert hits[-1].score == -9.75
    assert hits[-1].energy == -25.75
    assert hits[-1].start == 450
    assert hits[-1].end is None
    assert hits[-1].pvalue is None
    assert hits[-1].tool == "pita"
    assert hits[-1].chunk_id == "chunk0"
    assert hits[-1].raw_file == golden
