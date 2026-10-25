"""Prepare counterfactual review fixtures, not model answers or clinical labels."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/research'


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def build():
    base = next(c for c in json.loads((DATA / 'base-cases.json').read_text())
                if c['id'] == 'research-03')
    template = copy.deepcopy(base)
    template['care_setting'] = 'general_inpatient'
    template['source_context'] = {
        'source_id': 'CAP', 'version': '2024', 'guideline_id': '654_2',
        'use': 'frozen_research_reference', 'valid_for_case_date': None,
    }
    template['documents'][1]['text'] = (
        'Рентгенография органов грудной клетки выполнена в передней прямой '
        'и боковой проекциях. В нижней доле правого лёгкого описана инфильтрация.')
    specs = [
        ('Полный протокол', 'C03', 'confirmed', 'result',
         'В протоколе явно названы обе проекции; по этому признаку замечания нет.'),
        ('Результат отсутствует', 'C03', 'insufficient_evidence', None,
         'Запросить протокол; отсутствие файла не доказывает невыполнение исследования.'),
        ('Поздний результат', 'C02', 'insufficient_evidence', None,
         'Исключить result из доступных оснований; запросить документ на момент проверки.'),
        ('Не указаны проекции', 'C03', 'insufficient_evidence', 'result',
         'Результат есть, сведений о проекциях недостаточно.'),
        ('Только назначение', 'C03', 'insufficient_evidence', 'order',
         'Назначение не подтверждает выполнение; запросить протокол.'),
        ('Документирован отказ', 'C04', 'requires_expert', 'exception',
         'Показать отказ специалисту; не превращать его в автоматически подтверждённое исключение.'),
        ('Отметка об ограничении без причины', 'C04', 'requires_expert', 'exception',
         'Запросить основание ограничения; противопоказание не считать установленным.'),
        ('Возраст вне границ', 'C01', 'not_applicable', 'admission',
         'Возраст 17 лет: взрослый набор критериев не применять.'),
        ('Случай в реанимации', 'C01', 'not_applicable', 'transfer',
         'Случай за границами первой версии; передать специалисту.'),
        ('Другая нозология', 'C01', 'not_applicable', 'admission',
         'В карте указана ХСН без установленной пневмонии; критерий пневмонии не применять.'),
        ('Расхождение кодов', 'C05', 'contradiction', 'discharge',
         'Показать J18.9 в выписке и I50.9 в счёте; запросить проверку кодирования.'),
        ('Не задан источник', 'C06', 'requires_expert', None,
         'Отсутствует версия требования; нормативный вывод заблокирован.'),
        ('Неизвестен возраст', 'C01', 'insufficient_evidence', 'admission',
         'Запросить возраст; неизвестность не заменять взрослым возрастом.'),
        ('Результат ровно в момент проверки', 'C02', 'confirmed', 'result',
         'Доступность равна моменту проверки: документ включается по правилу <=.'),
    ]
    cases, expected = [], []
    for i, (scenario, criterion, status, evidence, reason) in enumerate(specs, 1):
        c = copy.deepcopy(template)
        c['id'] = f'feature-v1-{i:02d}'
        c['split'] = 'development_specification'
        if i in (2, 5, 6, 7):
            c['documents'] = [d for d in c['documents'] if d['id'] != 'result']
        if i == 3:
            c['documents'][1]['available_at'] = '2026-10-07T10:00:00+03:00'
        if i == 4:
            c['documents'][1]['text'] = base['documents'][1]['text']
        if i in (5, 6, 7):
            text = {
                5: 'Назначена рентгенография органов грудной клетки. Отметки о выполнении нет.',
                6: 'Пациент отказался от рентгенографии. Запись об отказе сохранена; требуется оценка специалиста.',
                7: 'Врач отметил ограничение к исследованию. Причина ограничения и решение о дальнейших действиях в выгрузке отсутствуют.',
            }[i]
            c['documents'].append({
                'id': 'order' if i == 5 else 'exception',
                'kind': 'order' if i == 5 else 'exception_note',
                'event_at': '2026-10-02T09:00:00+03:00',
                'available_at': '2026-10-02T09:05:00+03:00', 'text': text,
            })
        if i == 8:
            c['age'] = 17
        if i == 9:
            c['care_setting'] = 'intensive_care'
            c['documents'].append({
                'id': 'transfer', 'kind': 'transfer_note',
                'event_at': '2026-10-04T10:00:00+03:00',
                'available_at': '2026-10-04T10:05:00+03:00',
                'text': 'Переведён в ОРИТ; на момент проверки находится в ОРИТ.',
            })
            c['documents'] = [d for d in c['documents'] if d['id'] != 'discharge']
        if i == 10:
            c['stratum'] = 'circulatory'
            c['diagnosis'] = {'code': 'I50.9', 'text': 'Хроническая сердечная недостаточность'}
            c['documents'][0]['text'] = 'В карте указана ХСН. Жалобы на одышку и отёки. Диагноз пневмонии не установлен.'
            c['documents'][1]['text'] = 'Консультация кардиолога: требуется уточнение состояния по поводу ХСН.'
            c['documents'][2]['text'] = 'Учебный проект выписки по поводу ХСН. Пневмония не указана.'
            c['documents'][2]['diagnosis_code'] = 'I50.9'
            c['claim_draft']['principal_diagnosis_code'] = 'I50.9'
        if i == 11:
            c['claim_draft']['principal_diagnosis_code'] = 'I50.9'
        if i == 12:
            c['source_context'] = None
        if i == 13:
            c['age'] = None
        if i == 14:
            c['documents'][1]['available_at'] = c['review_at']
        cases.append(c)
        expected.append({
            'case_id': c['id'], 'family_id': c['family_id'], 'scenario': scenario,
            'criterion_id': criterion, 'expected_status': status, 'reason': reason,
            'evidence_document_ids': [evidence] if evidence else [],
            'clinical_ground_truth': False, 'is_model_output': False,
            'scope': 'one_target_criterion_only',
        })
    save(DATA / 'feature-cases.json', cases)
    save(DATA / 'feature-expectations.json', expected)
    manifest = {
        'purpose': 'specification fixtures; not an independent clinical sample',
        'new_cases': len(cases), 'parent_family_ids': sorted({c['family_id'] for c in cases}),
        'independent_family_count_added': 0, 'feature_executed': False,
        'files': {name: hashlib.sha256((DATA / name).read_bytes()).hexdigest()
                  for name in ('feature-cases.json', 'feature-expectations.json')},
    }
    save(ROOT / 'research/feature-packet-manifest.json', manifest)
    return cases, expected, manifest


if __name__ == '__main__':
    cases, _, _ = build()
    print(f'Prepared {len(cases)} specification variants from one existing family; no model calls')
