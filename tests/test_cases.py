import json
from pathlib import Path

from itmo_aimedicine.schemas import PatientRecord

ROOT = Path(__file__).resolve().parents[1]


def test_fixtures_are_synthetic_and_cover_time_and_unknown_states():
    records = [PatientRecord.model_validate(x) for x in json.loads((ROOT / "data/cases.json").read_text())]
    cases = {r.id: r for r in records}
    assert len(cases) == len(records) == 8
    assert all(r.synthetic is True for r in records)
    assert cases["case-01"].allergy_status == "denied"
    assert cases["case-03"].allergy_status == "unknown"
    assert cases["case-04"].observations[-1].status == "ordered"
    assert cases["case-04"].observations[-1].value is None
    assert cases["case-05"].observations[-1].available_at > cases["case-05"].review_at
    assert cases["case-07"].age < 18
    assert cases["case-08"].severe is True
    labels = json.loads((ROOT / "data/expectations.json").read_text())
    assert {row["case_id"] for row in labels} == set(cases)
    assert all(row["label_status"] == "engineering_only_not_clinician_reviewed" for row in labels)
