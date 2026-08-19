import json

from harness.record import AdapterRecord
from scripts.emit_record import main


def test_emitted_record_satisfies_the_schema(tmp_path):
    out = tmp_path / "vfa_t1.json"

    main([
        "--out", str(out), "--target", "qmrust@main", "--software", "qmrust",
        "--version", "main", "--model", "vfa_t1", "--status", "ok",
        "--fit-seconds", "1.5", "--fit-seconds", "1.4", "--n-voxels", "10",
        "--map", "T1:s:maps/vfa_t1/T1.nii.gz",
    ])

    record = AdapterRecord.from_dict(json.loads(out.read_text()))
    assert record.timing["repeats"] == 2
    assert record.maps[0] == {"name": "T1", "unit": "s", "path": "maps/vfa_t1/T1.nii.gz"}


def test_failed_status_carries_the_error(tmp_path):
    out = tmp_path / "vfa_t1.json"

    main([
        "--out", str(out), "--target", "qmrust@main", "--software", "qmrust",
        "--version", "main", "--model", "vfa_t1", "--status", "failed",
        "--error", "fit returned non-zero",
    ])

    assert AdapterRecord.from_dict(json.loads(out.read_text())).status == "failed"
