import json

from harness.drift import append_run, target_digests

DOC = {
    "reference": "a@1",
    "records": [
        {"target": "a@1", "model": "vfa_t1", "status": "ok",
         "maps": [{"name": "T1", "voxel_sha256": "aaa"}]},
        {"target": "b@1", "model": "vfa_t1", "status": "ok",
         "maps": [{"name": "T1", "voxel_sha256": "bbb"}]},
    ],
}


def test_each_target_gets_one_digest():
    assert set(target_digests(DOC)) == {"a@1", "b@1"}


def test_digest_is_stable_across_record_ordering():
    reordered = {**DOC, "records": list(reversed(DOC["records"]))}

    assert target_digests(DOC)["a@1"] == target_digests(reordered)["a@1"]


def test_digest_moves_when_a_map_hash_moves():
    changed = json.loads(json.dumps(DOC))
    changed["records"][0]["maps"][0]["voxel_sha256"] = "zzz"

    assert target_digests(DOC)["a@1"] != target_digests(changed)["a@1"]


def test_append_adds_exactly_one_line_per_run(tmp_path):
    history = tmp_path / "history.jsonl"

    append_run(history, DOC, run_started_utc="2026-08-19T04:00:00Z")
    append_run(history, DOC, run_started_utc="2026-08-26T04:00:00Z")

    lines = history.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["run_started_utc"] == "2026-08-19T04:00:00Z"
    assert json.loads(lines[1])["digests"]["a@1"] == target_digests(DOC)["a@1"]
