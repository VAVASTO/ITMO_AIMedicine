"""Freeze an authored extraction pilot; topic metadata is supplied, not inferred."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    rows=[]
    for line in (ROOT/'docs/05-feature.md').read_text().splitlines():
        if not line.startswith('| C0'):
            continue
        cells=[x.strip() for x in line.split('|')[1:-1]]
        rows.append({'id':f'current-{cells[0]}','topic':cells[0],'scope':'adult_cap','revision':'current',
                     'text':' '.join(cells[1:]),'source':'docs/05-feature.md','source_kind':'authored_engineering_specification'})
    rows.extend([
        {'id':'archive-C02','topic':'C02','scope':'adult_cap','revision':'archive',
         'text':'Учебная архивная версия правила доступности. Результат ровно в момент проверки исключается: available_at < review_at. Эта версия специально не применяется в текущей спецификации.',
         'source':'authored distractor','source_kind':'synthetic_distractor'},
        {'id':'pediatric-C01','topic':'C01','scope':'pediatric','revision':'current',
         'text':'Учебная карточка детского набора. Пневмония у ребёнка, границы по возрасту. Не относится к взрослому прототипу.',
         'source':'authored distractor','source_kind':'synthetic_distractor'},
    ])
    questions=[
        ('C01','Как проверить возрастную границу взрослого прототипа?'),
        ('C01','Возраст не указан. Какой статус сохранить?'),
        ('C02','Результат появился завтра, но исследование выполнено вчера. Учитывать ли его?'),
        ('C02','Результат ровно в момент проверки: исключать или включать?'),
        ('C03','В протоколе не названы проекции снимка. Можно ли подтвердить критерий?'),
        ('C03','Есть только направление на снимок, а описание отсутствует.'),
        ('C04','Пациент отказался от обследования. Можно ли автоматически снять замечание?'),
        ('C04','Как оценить документированное ограничение и основание исключения?'),
        ('C05','Коды основного диагноза в выписке и счёте расходятся.'),
        ('C06','Версия требования на дату случая не подтверждена.'),
        ('C06','Файл клинической рекомендации не передан. Разрешён ли нормативный вывод?'),
        ('C07','Как проверить точность цитаты и существование ссылки в ответе?'),
    ]
    packet={'purpose':'extraction_with_supplied_metadata_not_router_or_clinical_search_validation',
            'corpus':rows,'queries':[{'id':f'retrieval-{i:02d}','query':text,'topic':topic,'scope':'adult_cap','revision':'current'} for i,(topic,text) in enumerate(questions,1)]}
    labels=[{'query_id':q['id'],'relevant_ids':[f"current-{q['topic']}"]} for q in packet['queries']]
    folder=ROOT/'data/research/comparison-v1'
    for name,value in [('retrieval.json',packet),('retrieval-expectations.json',labels)]:
        path=folder/name
        with path.open('x') as stream:
            stream.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print('Frozen 9 authored cards and 12 queries; no API calls')


if __name__=='__main__':main()
