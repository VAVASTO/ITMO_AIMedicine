"""Author a frozen engineering packet. No real patients or clinical labels."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'data/research/comparison-v1'


def document(id, text, available_at, **fields):
    return dict(id=id, text=text, available_at=available_at, **fields)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cases, labels = [], []
    # Each row is a separately authored short history, not a mutation of research-03.
    rows = [
        (44, 'female', 'J18.9', 'general_inpatient', 'C03', 'confirmed',
         'После трёх дней кашля обратилась из-за лихорадки. В карте указана внебольничная пневмония.',
         [document('result', 'Рентгенография грудной клетки: выполнены передняя прямая и боковая проекции. Описано затемнение справа в нижнем отделе.', '2026-10-12T09:15:00+03:00')],
         'J18.9', ['result'], [], 'Полный доступный протокол с двумя проекциями'),
        (71, 'male', 'J18.9', 'general_inpatient', 'C03', 'insufficient_evidence',
         'Госпитализирован с кашлем и слабостью. Врач записал диагноз внебольничной пневмонии.',
         [document('order', 'Назначена рентгенография грудной клетки. Протокол в выгрузке отсутствует.', '2026-10-11T10:10:00+03:00')],
         'J18.9', ['order'], [], 'Назначение без протокола не подтверждает выполнение'),
        (58, 'female', 'J18.9', 'general_inpatient', 'C02', 'insufficient_evidence',
         'В направлении указана пневмония. При поступлении жалобы на кашель и боль при глубоком вдохе.',
         [document('result', 'Рентгенография: округлое затемнение диаметром 27 мм в сегменте S6 слева.', '2026-10-15T08:00:00+03:00', event_at='2026-10-12T08:00:00+03:00')],
         'J18.9', [], ['27 мм', 'S6', 'округлое затемнение', 'слева'], 'Будущий результат с отдельными фактами для проверки объяснения'),
        (39, 'male', 'J18.9', 'general_inpatient', 'C03', 'insufficient_evidence',
         'В карте зафиксирована внебольничная пневмония. Сохраняется кашель после нескольких дней болезни.',
         [document('order', 'Направлен на рентгенографию; результата в текущем комплекте ещё нет.', '2026-10-11T13:00:00+03:00'),
          document('result', 'Исследование выполнено в передней прямой и боковой проекциях. В описании: пластинчатый ателектаз справа длиной 43 мм.', '2026-10-14T12:01:00+03:00')],
         'J18.9', ['order'], ['43 мм', 'пластинчатый ателектаз'], 'Будущий полный протокол не закрывает текущий пропуск'),
        (63, 'female', 'J18.9', 'general_inpatient', 'C05', 'insufficient_evidence',
         'Лечится по поводу пневмонии. На момент проверки доступна только запись поступления.',
         [document('discharge', 'Проект выписки: основной код J15.1, указана синегнойная палочка.', '2026-10-16T11:00:00+03:00', diagnosis_code='J15.1')],
         'J18.9', [], ['J15.1', 'синегной'], 'Код будущей выписки нельзя сравнивать с текущим счётом'),
        (54, 'male', 'J18.9', 'general_inpatient', 'C04', 'requires_expert',
         'Поступил с лихорадкой и кашлем. Врач указал внебольничную пневмонию.',
         [document('discussion', 'Пациент отказался от рентгенографии. В записи нет описания обсуждённых последствий отказа.', '2026-10-12T14:20:00+03:00')],
         'J18.9', ['discussion'], [], 'Отказ требует эксперта, достаточность обоснования неизвестна'),
        (17, 'female', 'J18.9', 'general_inpatient', 'C01', 'not_applicable',
         'Пациентке 17 лет. В направлении указана пневмония; история включена для проверки возрастной границы.',
         [], 'J18.9', [], [], 'Возраст за пределами взрослого прототипа'),
        (None, 'male', 'J18.9', 'general_inpatient', 'C01', 'insufficient_evidence',
         'В выгрузке отсутствуют возраст и дата рождения. Диагноз записан как внебольничная пневмония.',
         [], 'J18.9', [], [], 'Неизвестный возраст нельзя восстанавливать по косвенным признакам'),
        (80, 'female', 'J18.9', 'general_inpatient', 'C02', 'confirmed',
         'В карте указана пневмония. Отдельный протокол поступает в момент проверки.',
         [document('result', 'Рентгенография: протокол зарегистрирован, проекции описаны в приложении, которое в выгрузку не входит.', '2026-10-14T12:00:00+03:00')],
         'J18.9', ['result'], [], 'Доступность ровно на временной границе'),
        (47, 'male', 'J20.9', 'general_inpatient', 'C01', 'not_applicable',
         'В текущем диагнозе указан острый бронхит. Диагноз пневмонии в этой истории не установлен.',
         [], 'J20.9', [], [], 'Другая нозология вне границ набора'),
        (68, 'female', 'J18.9', 'general_inpatient', 'C05', 'contradiction',
         'Врач записал пневмонию. Подготовлены проект выписки и учебная строка счёта.',
         [document('discharge', 'В проекте выписки основной диагноз имеет код J18.9.', '2026-10-14T10:30:00+03:00', diagnosis_code='J18.9')],
         'J15.9', ['discharge'], [], 'Различные коды должны быть показаны без автоматической замены'),
        (36, 'male', 'J18.9', 'general_inpatient', 'C06', 'requires_expert',
         'В карте записана пневмония. Файл требований и сведения о его версии к проверке не приложены.',
         [document('result', 'Сохранён протокол рентгенографии в передней прямой и боковой проекциях.', '2026-10-13T16:40:00+03:00')],
         'J18.9', [], [], 'Отсутствует источник требования'),
    ]
    for n, (age, sex, code, care, criterion, status, admission, extra, claim, required, forbidden, purpose) in enumerate(rows, 1):
        ident = f'comparison-v1-{n:02d}'
        cases.append(dict(id=ident, family_id=f'comparison-family-{n:02d}', synthetic=True,
                          expert_reviewed=False, split='frozen_engineering_pilot', age=age, sex=sex,
                          diagnosis={'code':code, 'text':'Внебольничная пневмония' if code=='J18.9' else 'Острый бронхит'},
                          care_setting=care, review_at='2026-10-14T12:00:00+03:00',
                          documents=[document('admission',admission,'2026-10-11T09:00:00+03:00')]+extra,
                          claim_draft={'principal_diagnosis_code':claim,'synthetic':True},
                          source_context=None if n==12 else {'source_id':'CAP','version':'2024','guideline_id':'654_2','valid_for_case_date':None,'use':'frozen_research_reference'}))
        labels.append(dict(case_id=ident, criterion_id=criterion, expected_status=status,
                           required_evidence_ids=required, forbidden_future_markers=forbidden,
                           required_explanation_terms=['J18.9','J15.9'] if n==11 else [], purpose=purpose))
    for name, value in [('cases.json',cases),('expectations.json',labels)]:
        (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(f'Prepared {len(cases)} authored histories and separate expectations')


if __name__=='__main__':
    main()
