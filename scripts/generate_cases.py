"""Generate engineering examples, not an epidemiologically representative cohort."""
from copy import deepcopy
import json
from pathlib import Path

from itmo_aimedicine.schemas import PatientRecord

ROOT = Path(__file__).resolve().parents[1]


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    baseline = {
        "id": "case-01", "synthetic": True, "age": 46,
        "diagnosis": "Внебольничная пневмония, диагноз задан в учебном сценарии",
        "encounter": "inpatient", "review_at": "2026-10-01T12:00:00+03:00",
        "severe": False, "allergy_status": "denied",
        "observations": [
            {"id": "obs-1", "kind": "temperature", "status": "available", "value": "38.2", "unit": "C", "available_at": "2026-10-01T10:00:00+03:00"},
            {"id": "obs-2", "kind": "spo2", "status": "available", "value": "96", "unit": "%", "available_at": "2026-10-01T10:00:00+03:00"},
            {"id": "obs-3", "kind": "respiratory_rate", "status": "available", "value": "20", "unit": "/min", "available_at": "2026-10-01T10:00:00+03:00"},
            {"id": "obs-4", "kind": "blood_pressure", "status": "available", "value": "125/80", "unit": "mmHg", "available_at": "2026-10-01T10:00:00+03:00"},
            {"id": "obs-5", "kind": "chest_imaging", "status": "available", "value": "Описание исследования приложено к учебной записи.", "unit": None, "available_at": "2026-10-01T11:00:00+03:00"},
        ],
        "note": "Полностью вымышленный пример. Проверяется только заданный набор сведений.",
    }
    cases, expectations = [], []
    targets = [
        ("control", "Контроль в пределах выбранных полей", []),
        ("missing_spo2", "Не указан результат пульсоксиметрии", ["spo2_not_documented"]),
        ("unknown_allergy", "Аллергологический анамнез неизвестен", ["allergy_unknown"]),
        ("ordered_imaging", "Назначение исследования без результата", ["imaging_result_not_available"]),
        ("future_result", "Результат доступен после момента проверки", ["imaging_result_not_available"]),
        ("conflict", "Два значения одного показателя в один момент", ["spo2_conflict"]),
        ("child", "Возраст за пределами первой версии", ["out_of_scope"]),
        ("severe", "Тяжёлое течение за пределами первой версии", ["out_of_scope"]),
    ]
    for i, (kind, title, expected) in enumerate(targets, 1):
        case = deepcopy(baseline)
        case["id"] = f"case-{i:02d}"
        if kind == "missing_spo2":
            case["observations"] = [o for o in case["observations"] if o["kind"] != "spo2"]
        elif kind == "unknown_allergy":
            case["allergy_status"] = "unknown"
        elif kind == "ordered_imaging":
            case["observations"][-1].update(status="ordered", value=None, available_at=None)
        elif kind == "future_result":
            case["observations"][-1]["available_at"] = "2026-10-01T15:00:00+03:00"
        elif kind == "conflict":
            conflicting = deepcopy(case["observations"][1])
            conflicting.update(id="obs-6", value="92")
            case["observations"].append(conflicting)
        elif kind == "child":
            case["age"] = 16
        elif kind == "severe":
            case["severe"] = True
        cases.append(PatientRecord.model_validate(case).model_dump(mode="json"))
        expectations.append({"case_id": case["id"], "family": "baseline-01", "title": title,
                             "expected_codes": expected, "label_status": "engineering_only_not_clinician_reviewed"})
    write(ROOT / "data/cases.json", cases)
    write(ROOT / "data/expectations.json", expectations)
    write(ROOT / "schemas/patient.schema.json", PatientRecord.model_json_schema())


if __name__ == "__main__":
    main()
