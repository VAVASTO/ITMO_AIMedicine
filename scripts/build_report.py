"""Build a self-contained research report and portable evidence files."""
from html import escape
import json
from pathlib import Path
import re
import textwrap
import xml.etree.ElementTree as ET

import markdown

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text())


def test_summary(path):
    root = ET.parse(path).getroot()
    suites = list(root) if root.tag == 'testsuites' else [root]
    return {k: sum(int(s.attrib.get(k, 0)) for s in suites)
            for k in ('tests', 'failures', 'errors', 'skipped')}


def table(headers, rows, attrs=''):
    head = ''.join(f'<th scope="col">{escape(h)}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in rows)
    return f'<div class="table-wrap"><table {attrs}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def flow(steps, title):
    width = 960
    gap = 32
    box = (width - gap * (len(steps) - 1)) / len(steps)
    parts = [f'<svg role="img" aria-label="{escape(title)}" viewBox="0 0 960 110" xmlns="http://www.w3.org/2000/svg"><title>{escape(title)}</title>']
    for i, step in enumerate(steps):
        x = i * (box + gap)
        parts.append(f'<rect x="{x:.1f}" y="10" width="{box:.1f}" height="90" rx="3" fill="#f6f6f6" stroke="#777"/>')
        lines = textwrap.wrap(step, width=int(box / 8))
        for j, line in enumerate(lines):
            parts.append(f'<text x="{x+box/2:.1f}" y="{56-(len(lines)-1)*10+j*20}" text-anchor="middle" font-family="Arial,sans-serif" font-size="15" fill="#222">{escape(line)}</text>')
        if i < len(steps) - 1:
            start = x + box + 4
            parts.append(f'<path d="M{start:.1f} 55 h24 m-6 -5 l6 5 -6 5" fill="none" stroke="#444"/>')
    parts.append('</svg>')
    return '<div class="diagram">' + ''.join(parts) + '</div>'


def stat_chart(plan):
    labels = ['Кровообращение', 'Дыхание', 'Пищеварение', 'Эндокринные', 'Мочеполовые', 'Ухо и сосцевидный отросток']
    parts = ['<svg role="img" aria-label="Число выбывших пациентов по выбранным классам, 2024 год, тысячи человек" viewBox="0 0 960 300" xmlns="http://www.w3.org/2000/svg"><title>Данные Росстата: тысячи выбывших пациентов, 2024 год</title>']
    for i, (s, label) in enumerate(zip(plan['strata'], labels)):
        y = 34 + i * 43
        n = s['discharged_thousand_2024']
        w = n / 4928 * 490
        parts.extend([f'<text x="0" y="{y}" font-family="Arial" font-size="16">{label}</text>',
                      f'<rect x="285" y="{y-19}" width="{w:.2f}" height="26" fill="#606060"/>',
                      f'<text x="{285+w+10:.2f}" y="{y}" font-family="Arial" font-size="16">{str(n // 1000) + " " + str(n % 1000).zfill(3) if n >= 1000 else str(n)}</text>'])
    parts.append('</svg>')
    return '<figure><div class="diagram">'+''.join(parts)+'</div><figcaption>РФ, 2024 год. Все возраста и профили стационара. Показаны только шесть выбранных классов; единица: тысяча человек. Источник: Росстат, таблица 3.17, с. 97.</figcaption></figure>'


def main():
    sources = read('research/sources.json')
    by_source = {s['id']: s for s in sources}
    comparisons = read('research/competitors.json')
    plan = read('research/sampling-plan.json')
    cases = read('data/research/base-cases.json')
    seeds = {s['id']: s for s in read('data/research/scenario-seeds.json')}
    checks = test_summary(ROOT / 'reports/checks/pytest-revision.xml')
    old_checks = test_summary(ROOT / 'reports/checks/pytest.xml')
    reference = test_summary(ROOT / 'reports/checks/reference-mistral.xml')
    if any(r['failures'] or r['errors'] for r in (checks, old_checks, reference)):
        raise ValueError('Failing checks cannot be published as passing')
    live = read('reports/checks/mistral-live.json')
    smoke = read('reports/checks/mock-smoke.json')
    if smoke['mode'] != 'mock' or smoke['attempts'] != 0:
        raise ValueError('Expected recorded offline smoke evidence')
    if not live['success']:
        raise ValueError('Invalid recorded live evidence')
    groups = {'baseline': 'Ручной процесс и правила', 'direct': 'Российские аналоги',
              'adjacent': 'Экспертиза в другой юрисдикции', 'knowledge': 'Поиск знаний', 'documentation': 'Подготовка записей'}
    options = '<option value="all">Все подходы</option>'+''.join(f'<option value="{k}">{v}</option>' for k,v in groups.items())
    competitor_rows = []
    for i, c in enumerate(comparisons):
        refs = ' '.join(f'<a href="{escape(by_source[s]["url"])}">{s}</a>' for s in c['sources'])
        competitor_rows.append([f'<a href="#solution-{i}">{escape(c["name"])}</a>', groups[c['group']], escape(c['evidence']), refs])
    comp_table = table(['Подход / продукт', 'Задача', 'Доказательства эффективности', 'Источники'], competitor_rows, 'id="competitor-table"')
    # Group metadata is attached to body rows in the same order as the registry.
    index = iter(comparisons)
    comp_table = re.sub(r'<tr>(?=<td>)', lambda _: f'<tr data-group="{next(index)["group"]}">', comp_table)
    comp_table = f'<label class="filter">Показать: <select id="group-filter">{options}</select></label><p id="filter-count" aria-live="polite">Показано: {len(comparisons)}</p>'+comp_table
    sampling = table(['Класс', 'Выбыло, тыс.', 'Доля всех, %', 'Доля выбранных, %', 'План из 60'], [
        [escape(s['label']),str(s['discharged_thousand_2024']),f'{s["share_all_percent"]:.2f}',f'{s["share_selected_percent"]:.2f}',str(s['planned_cases'])] for s in plan['strata']])
    workflow = ''.join('<h4>'+name+'</h4>'+flow(steps,name) for name,steps in [
        ('Работа врача',['Поступление и первичная оценка','Обследования и лечение','Динамика и обоснования','Карта и выписка']),
        ('Внутренняя проверка',['Карта и локальные правила','Сопоставление и исключения','Уточнения у врача','Закрытие случая и счёт']),
        ('Экспертиза ОМС',['Счёт и первичные документы','МЭЭ / ЭКМП по процедуре','Заключение с основаниями','Возражения и разбор']),
    ])
    workflow += '<p class="caption">Передача: врач → внутренний эксперт → учёт и счёт → внешний контроль. Замечания возвращаются ответственному специалисту. МЭК выполняется отдельно по реестрам счетов.</p>'
    architecture = ''.join('<h4>'+name+'</h4>'+flow(steps,name) for name,steps in [
        ('Общая подготовка',['Файлы / МИС / OCR','Факты и хронология','Онтология и версии знаний','Поиск и правила']),
        ('Клиническая ветвь',['Состояние пациента','Проект плана и основания','Оценка динамики','Решение врача и запись']),
        ('Экспертная ветвь',['Карта и счёт','Критерии и исключения','Замечания и доказательства','Решение эксперта']),
        ('Общий контроль',['Проверка ссылок и фактов','Vue: две панели оснований','Решение и комментарий','Журнал версий и экспорт']),
    ])
    blocks = {'<div data-diagram="workflow"></div>':workflow,
              '<div data-diagram="architecture"></div>':architecture,
              '<div data-diagram="strata"></div>':stat_chart(plan),
              '<div data-table="sampling"></div>':sampling,
              '<div data-table="competitors"></div>':comp_table}
    for i,c in enumerate(comparisons):
        blocks[f"<div data-flow='{c['name']}'></div>"] = f'<div id="solution-{i}">'+flow(c['flow'], c['name'])+'</div>'
    chapters, nav = [], []
    order = ['01-scope','02-research','09-documents','03-data','04-architecture','05-feature','06-evaluation','07-models','08-validation','10-next-steps']
    for n,name in enumerate(order,1):
        source = ROOT / 'docs' / (name+'.md')
        txt = source.read_text()
        title = txt.splitlines()[0].removeprefix('# ')
        body = markdown.markdown(txt,extensions=['tables','fenced_code'])
        body = re.sub(r'<(/?)h([1-5])>',lambda m:f'<{m[1]}h{int(m[2])+1}>',body)
        body = body.replace('<table>','<div class="table-wrap"><table>').replace('</table>','</table></div>')
        for token,value in blocks.items():
            body=body.replace(token,value)
        chapter_id = f'chapter-{n}'
        chapters.append(f'<section class="chapter" id="{chapter_id}">{body}</section>')
        nav.append(f'<li><a href="#{chapter_id}">{escape(title)}</a></li>')
    results=[
        ['Исследовал рабочий процесс','3 роли; 3 вида контроля ОМС','Нужны разные основания для клинического и финансового вывода','По открытым документам'],
        ['Сравнил решения','12 подходов и продуктов; схемы каждого','Ближайшие аналоги: ОМС-Эксперт и контроль КР Webiomed','Исследование выполнено'],
        ['Разобрал документы','24 типа; '+str(len(sources))+' источников в реестре','Выделены версии, применение и недостающие документы организации','Реестр подготовлен'],
        ['Подготовил методику и примеры','6 статистических классов; 12 заготовок + 24 варианта','План на 60 историй рассчитан; клиническая разметка ещё нужна','Для согласования'],
        ['Спроектировал систему','2 ветви; 12 модулей; спецификация первой функции','Общий учёт фактов, времени и источников','Проект'],
        ['Проверил доработку',f'{checks["tests"]} локальных тестов, 0 ошибок','Целостность данных и техническая часть; не клиническая точность','25.10.2026'],
        ['Сохранил результаты подключения','1 успешный запрос Mistral, 73 токена; 34 теста старого клиента','Повторных живых запросов при доработке не было','Результаты 18.10.2026'],
        ['Проверил ограничения','0 экспертно размеченных клинических карт','Нужны врач, эксперт ОМС и документы выбранной организации','Открытые вопросы'],
    ]
    summary=table(['Что сделал','Результат','Вывод','Статус'],[[escape(x) for x in row] for row in results])
    examples=[]
    for c in cases:
        s=seeds[c['id']]
        docs=''.join(f'<h4>{escape(d["id"])} · событие {escape(d["event_at"][:16])}</h4><p>{escape(d["text"])}</p><p class="meta">Доступно: {escape(d["available_at"])}</p>' for d in c['documents'])
        examples.append(f'<details><summary>{escape(c["id"])} · {escape(c["diagnosis"]["text"])} · возраст: {c["age"]}</summary><p>Код в учебном примере: {escape(c["diagnosis"]["code"])}. Проверка: {escape(c["review_at"])}.</p>{docs}<p><strong>Вопрос эксперту:</strong> {escape(s["expert_question"])}</p></details>')
    source_rows = [[escape(s['id']),f'<a href="{escape(s["url"])}">{escape(s["title"])}</a><br>{escape(s["kind"])}',escape(s['locator']),escape(s['limits'])] for s in sources]
    css='''
*{box-sizing:border-box}html{background:#fff;color:#222;font:16px/1.6 Arial,sans-serif}body{max-width:1120px;margin:auto;padding:40px 30px 70px}h1{font-size:30px;line-height:1.25;margin:0 0 12px}h2{font-size:25px;line-height:1.35}h3{font-size:20px;margin-top:28px}h4{font-size:16px;margin:18px 0 8px}header{border-bottom:1px solid #aaa;padding-bottom:22px}.meta,figcaption,.caption{font-size:14px;color:#555}.subtitle{font-size:20px}p{margin:12px 0 18px}a{color:inherit;text-underline-offset:3px;overflow-wrap:anywhere}a:focus-visible,select:focus-visible,summary:focus-visible{outline:2px solid #333;outline-offset:3px}nav{padding:12px 0 28px}nav li{margin:5px 0}.chapter{border-top:1px solid #bbb;padding:24px 0;scroll-margin-top:20px}.table-wrap{overflow-x:auto;margin:18px 0 26px}table{border-collapse:collapse;width:100%;font-size:14px;text-align:left}td,th{border:1px solid #c9c9c9;padding:10px 12px;vertical-align:top}th{background:#f1f1f1}td{min-width:110px}tr[hidden]{display:none}code{font-size:.9em;overflow-wrap:anywhere}pre{background:#f5f5f5;border:1px solid #ddd;white-space:pre-wrap;overflow-wrap:anywhere;padding:15px;font-size:13px}li{margin:6px 0}.diagram{overflow-x:auto;margin:10px 0 18px}.diagram svg{display:block;width:100%;min-width:640px;height:auto}figure{margin:22px 0}details{border-bottom:1px solid #ddd;padding:12px 0}summary{cursor:pointer;font-weight:600}select{font:inherit;padding:7px;max-width:100%;background:#fff;border:1px solid #888}#filter-count{font-size:14px;color:#555}button{font:inherit}footer{border-top:1px solid #aaa;padding-top:18px;color:#555;font-size:14px}.filter{display:block} @media(max-width:700px){body{padding:24px 16px 40px}h1{font-size:26px}h2{font-size:22px}td,th{min-width:145px}.table-wrap{font-size:13px}.diagram{border-bottom:1px solid #ddd}}
@media print{html{font-size:10pt}body{max-width:none;padding:0}nav,.filter,#filter-count{display:none}h1{font-size:22pt}h2{font-size:17pt;break-after:avoid}h3,h4{break-after:avoid}.chapter{padding:15px 0}.table-wrap,.diagram{overflow:visible}table{font-size:8pt}td,th{min-width:0;padding:5px}tr{break-inside:avoid}tr[hidden]{display:table-row}.diagram svg{min-width:0;width:100%}details{break-inside:auto}details::details-content{content-visibility:visible}summary{margin-top:10px}pre{font-size:8pt}}
'''
    js='''
const group = document.getElementById('group-filter');
group.addEventListener('change', () => {
 let count = 0;
 for (const row of document.querySelectorAll('#competitor-table tbody tr')) {
  row.hidden = group.value !== 'all' && row.dataset.group !== group.value;
  if (!row.hidden) count++;
 }
 document.getElementById('filter-count').textContent = 'Показано: ' + count;
});
let printOpen = [];
window.addEventListener('beforeprint', () => { printOpen = [...document.querySelectorAll('details')].map(d => d.open); document.querySelectorAll('details').forEach(d => d.open = true); });
window.addEventListener('afterprint', () => { document.querySelectorAll('details').forEach((d,i) => d.open = printOpen[i] || false); });
'''
    evidence = {'revision_date':'2026-10-25','revision_tests':checks,'original_tests_2026_10_18':old_checks,
                'reference_tests_2026_10_18':reference,'mistral_live_2026_10_18':live,'mock_smoke_2026_10_18':smoke,
                'sampling_plan':plan,'sources':sources,'source_provenance':read('research/rosstat-provenance.json')}
    html=f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Первая неделя: клинический помощник и экспертиза ОМС</title><style>{css}</style></head><body>
<header><h1>Отчёт за первую неделю</h1><p class="subtitle">Клинический помощник и экспертиза медицинской документации</p><p class="meta">Доработка от 25 октября 2026 года<br>Репозиторий: <a href="https://github.com/VAVASTO/ITMO_AIMedicine">VAVASTO/ITMO_AIMedicine</a></p></header>
<main><h2>Что сделано</h2>{summary}<nav aria-label="Содержание"><h2>Содержание</h2><ol>{''.join(nav)}<li><a href="#examples">Примеры для согласования</a></li><li><a href="#sources">Источники и ограничения</a></li><li><a href="#checks">Подтверждение технических проверок</a></li></ol></nav>
{''.join(chapters)}
<section class="chapter" id="examples"><h2>Примеры для согласования</h2><p>12 вымышленных заготовок для обсуждения с врачом и экспертом. В них показана часть документов, а не полная история болезни. Показания к госпитализации, кодирование и клиническая достаточность ещё не подтверждены. Ожидаемые инженерные реакции хранятся отдельно от входных данных.</p>{''.join(examples)}</section>
<section class="chapter" id="sources"><h2>Источники и ограничения</h2><p>Дата обращения: 25 октября 2026 года. Для каждого источника указал, что именно проверял и какие выводы из него делать нельзя. Нормативный документ перед использованием нужно связать с датой конкретного случая.</p>{table(['ID','Источник','Место подтверждения','Ограничение'],source_rows)}</section>
<section class="chapter" id="checks"><h2>Подтверждение технических проверок</h2><p>Приложения: <a href="assets/research-evidence.json">источники, расчёт выборки и результаты проверок</a>; <a href="assets/review-examples.json">примеры и вопросы эксперту</a>. Порядок воспроизведения приведён в <a href="https://github.com/VAVASTO/ITMO_AIMedicine#проверки-и-сборка-отчёта">README репозитория</a>.</p><p>Доработка: {checks['tests']} тестов пройдено, ошибок {checks['errors']}, падений {checks['failures']}. Предупреждение об устаревающем способе подключения HTTPX осталось прежним. Клиническую точность не измерял.</p><details><summary>Результаты и версии в JSON</summary><pre>{escape(json.dumps(evidence,ensure_ascii=False,indent=2))}</pre></details></section></main><script>{js}</script></body></html>'''
    if re.search(r'data-(?:diagram|table|flow)=',html) or '[@' in html:
        raise ValueError('Unresolved report placeholders')
    for name in ('week-1-report.html','Отчёт_за_первую_неделю.html'):
        (ROOT/'reports'/name).write_text(html)
    (ROOT/'reports/assets/research-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'reports/assets/review-examples.json').write_text(json.dumps({'purpose':'synthetic examples for expert review; not clinical ground truth','cases':cases,'questions':{k:v['expert_question'] for k,v in seeds.items()}},ensure_ascii=False,indent=2)+'\n')
    print(f'Built week-1-report.html: {len(html.encode())} bytes, {len(sources)} sources, {len(comparisons)} comparisons, {len(cases)} review examples')


if __name__ == '__main__':
    main()
