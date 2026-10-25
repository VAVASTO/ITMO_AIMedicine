"""Build a self-contained research report and portable evidence files."""
from html import escape
import json
from pathlib import Path
import re
import textwrap
import xml.etree.ElementTree as ET

import markdown
from report_presentation import decorate_report, label_prose

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text())


def test_summary(path):
    root = ET.parse(path).getroot()
    suites = list(root) if root.tag == 'testsuites' else [root]
    return {k: sum(int(s.attrib.get(k, 0)) for s in suites)
            for k in ('tests', 'failures', 'errors', 'skipped')}


def table(headers, rows, attrs='', caption=''):
    head = ''.join(f'<th scope="col">{escape(h)}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{c}</td>' for c in row) + '</tr>' for row in rows)
    label = f'<caption>{escape(caption)}</caption>' if caption else ''
    return f'<div class="table-wrap"><table {attrs}>{label}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def report_section(section_id, body):
    heading = re.match(r'<h2>(.*?)</h2>', body, re.S)
    if not heading:
        raise ValueError(f'Missing heading: {section_id}')
    return (f'<section class="chapter" id="{section_id}"><details class="chapter-body" open>'
            f'<summary><h2>{heading[1]}</h2></summary>{body[heading.end():]}</details></section>')


def generation_prompt(inputs):
    prompt = (ROOT / 'reports/generation/platform-template.txt').read_text()
    replacements = {
        '(not provided)': inputs['context'],
        '(choose a precise title based on the context)': f"Неделя {inputs['week']}. {inputs['title']}",
        '(no rows were provided: build the table skeleton and mark every empty cell with the badge "нужно уточнить")': json.dumps(inputs['rows'], ensure_ascii=False, indent=2),
        '(no extra sections were requested: derive sensible sections from the summary rows)': '\n'.join(inputs['sections']),
        '(no assets were uploaded: use only the data given in this prompt)': '\n'.join(f"- {a['path']}: {a['description']}" for a in inputs['assets']),
        '(none)': inputs['preferences'],
    }
    # Fill the platform's six placeholders; keep every fixed instruction verbatim.
    for placeholder, content in replacements.items():
        if prompt.count(placeholder) != 1:
            raise ValueError(f'Platform placeholder changed: {placeholder}')
        prompt = prompt.replace(placeholder, content, 1)
    prompt += '\n<local_materials>\n' + '\n'.join(
        f'\nFILE: {p.relative_to(ROOT)}\n{p.read_text()}' for p in sorted((ROOT / 'docs').glob('*.md'))
    ) + '\n</local_materials>\n'
    (ROOT / 'reports/generation/week-1-prompt.txt').write_text(prompt)


def case_walkthrough():
    case = next(c for c in read('data/research/variants.json') if c['id'] == 'research-03-late_result')
    expected = next(c for c in read('data/research/expectations.json') if c['case_id'] == case['id'])
    evidence = {'kind': 'authored_expected_behavior', 'is_model_output': False,
                'case': case, 'engineering_expectation': expected,
                'source': {'id': 'CAP', 'version': '2024', 'guideline_id': '654_2',
                           'section': '2.4', 'pdf_page': 18, 'current_validity_verified': False},
                'states': [
                    {'review_at': case['review_at'], 'available_documents': ['admission', 'discharge'],
                     'status': 'insufficient_evidence', 'message': 'Результат недоступен на момент проверки; запросить протокол.'},
                    {'review_at': '2026-10-07T10:01:00+03:00', 'available_documents': ['admission', 'result', 'discharge'],
                     'status': 'insufficient_evidence', 'message': 'Результат найден; проекции не указаны, нужен полный протокол.'}
                ]}
    (ROOT / 'reports/assets/feature-walkthrough.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
    return '''<div class="case-demo" aria-label="Проект результата проверки">
<p class="caption"><strong>Проект поведения.</strong> Переключатель показывает два заранее описанных состояния. Модель здесь не вызывается.</p>
<label class="demo-control" for="case-state">Момент проверки:</label>
<select class="demo-control" id="case-state"><option value="before">6 октября, 12:00: результат ещё недоступен</option><option value="after">7 октября, 10:01: результат уже получен</option></select>
<div id="case-state-live" aria-live="polite">
<article data-case-state="before"><h4>6 октября, 12:00 · Недостаточно сведений</h4>
<p><strong>Замечание:</strong> в документах, доступных на момент проверки, не найден результат рентгенографии. Проверьте полноту выгрузки и наличие протокола.</p>
<div class="evidence-pair"><div><h4>Основание в карте</h4><p>Доступны admission и discharge. У result время доступности 7 октября, 10:00, поэтому он исключён из этой проверки.</p></div>
<div><h4>Основание требования</h4><p>КР 654_2, версия 2024, раздел 2.4, страница PDF 18. Для примера рассматриваю рекомендацию о рентгенографии при подозрении на пневмонию; применимость требует проверки специалистом.</p></div></div>
<p><strong>Действие:</strong> запросить протокол. Вывод о невыполнении исследования не делать.</p></article>
<article data-case-state="after" hidden><h4>7 октября, 10:01 · Результат найден, сведения неполны</h4>
<p><strong>Изменение:</strong> замечание об отсутствии результата снимается. Для проверки проекций нужен полный протокол.</p>
<div class="evidence-pair"><div><h4>Основание в карте</h4><p>result: «Рентгенография: инфильтрация в нижней доле правого лёгкого». Доступен с 7 октября, 10:00; переднюю прямую и боковую проекции текст не описывает.</p></div>
<div><h4>Основание требования</h4><p>Та же КР 654_2, версия 2024, раздел 2.4. Наличие фрагмента результата ещё не подтверждает выполнение требования целиком.</p></div></div>
<p><strong>Действие:</strong> сверить полный протокол. Сохранить обе версии проверки; прежнюю не переписывать.</p></article></div>
<p class="caption">Все даты относятся к вымышленному случаю 2026 года; время UTC+3. <a href="assets/feature-walkthrough.json">Данные и ожидаемые состояния</a>.</p></div>'''


def feature_packet():
    cases = read('data/research/feature-cases.json')
    expectations = read('data/research/feature-expectations.json')
    by_id = {c['id']: c for c in cases}
    status = {'confirmed': 'Подтверждено по критерию', 'contradiction': 'Противоречие',
              'insufficient_evidence': 'Недостаточно сведений',
              'not_applicable': 'Неприменимо', 'requires_expert': 'Требуется эксперт'}
    rows, details = [], []
    for e in expectations:
        c = by_id[e['case_id']]
        anchor = c['id']
        setting = {'general_inpatient': 'обычный стационар', 'intensive_care': 'ОРИТ'}[c['care_setting']]
        source_note = ('КР 654_2, версия 2024; исследовательская копия, актуальность на дату случая не подтверждена'
                       if c['source_context'] else 'не задан')
        rows.append([f'<a href="#{anchor}">{escape(anchor)}</a>', escape(e['scenario']),
                     escape(e['criterion_id']), status[e['expected_status']], escape(e['reason'])])
        documents = ''.join(
            f'<p><strong>{escape(d["id"])}</strong> · доступен {escape(d["available_at"])}<br>{escape(d["text"])}' +
            (f'<br>Поле {escape(d["id"])}.diagnosis_code: <code>{escape(d["diagnosis_code"])}</code>'
             if 'diagnosis_code' in d else '') + '</p>'
            for d in c['documents'])
        details.append(f'<details id="{anchor}"><summary>{escape(anchor)}: {escape(e["scenario"])}</summary>'
                       f'<p>Семья: {escape(c["family_id"])}; возраст: {c["age"] if c["age"] is not None else "не указан"}; '
                       f'условия: {setting}. Проверка: {escape(c["review_at"])}.</p>'
                       f'{documents}<p>Код счёта: {escape(c["claim_draft"]["principal_diagnosis_code"])}. '
                       f'КР во входном наборе: {source_note}.</p>'
                       f'<p><strong>Ожидание для {escape(e["criterion_id"])}:</strong> {escape(e["reason"])} '
                       'Это авторская спецификация, не результат модели.</p></details>')
    packet = {'purpose': 'authored specification; labels must not be passed to the model',
              'cases': cases, 'expectations': expectations,
              'manifest': read('research/feature-packet-manifest.json')}
    (ROOT / 'reports/assets/feature-packet.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2)+'\n')
    return (table(['Вариант', 'Ситуация', 'Критерий', 'Ожидаемый статус', 'Ожидаемое действие'], rows) +
            '<p><a href="assets/feature-packet.json">Полные входы, отдельные ожидания и контрольные суммы</a>. '
            'Ниже можно раскрыть каждый вариант без внешних файлов.</p>' + ''.join(details))


def flow(steps, title):
    width = 960
    gap = 32
    box = (width - gap * (len(steps) - 1)) / len(steps)
    parts = [f'<svg role="img" aria-label="{escape(title)}" viewBox="0 0 960 110" xmlns="http://www.w3.org/2000/svg"><title>{escape(title)}</title>']
    for i, step in enumerate(steps):
        x = i * (box + gap)
        explanation = f'{title}. Шаг {i+1} из {len(steps)}: {step}.'
        points = f'{x:.1f},10 {x+box-18:.1f},10 {x+box:.1f},55 {x+box-18:.1f},100 {x:.1f},100 {x+18:.1f},55'
        parts.append(f'<g class="flow-step" tabindex="0" aria-label="{escape(explanation)}" data-explanation="{escape(explanation)}"><title>{escape(explanation)}</title><polygon points="{points}"/>')
        lines = textwrap.wrap(step, width=int(box / 8))
        for j, line in enumerate(lines):
            parts.append(f'<text x="{x+box/2:.1f}" y="{56-(len(lines)-1)*10+j*20}" text-anchor="middle" font-family="Arial,sans-serif" font-size="15" fill="#222">{escape(line)}</text>')
        parts.append('</g>')
        if i < len(steps) - 1:
            start = x + box + 4
            parts.append(f'<path d="M{start:.1f} 55 h24 m-6 -5 l6 5 -6 5" fill="none" stroke="#444"/>')
    parts.append('</svg>')
    return '<figure class="flow-figure"><div class="diagram">' + ''.join(parts) + '</div><figcaption>'+escape(title)+'</figcaption><p class="diagram-explanation" aria-live="polite">Наведите на шаг или выберите его клавишей Tab.</p></figure>'


def glm_results(trial):
    expectations = {r['case_id']: r for r in read('data/research/feature-expectations.json')}
    statuses = {'confirmed': 'Подтверждено по критерию', 'contradiction': 'Противоречие',
                'insufficient_evidence': 'Недостаточно сведений',
                'not_applicable': 'Неприменимо', 'requires_expert': 'Требуется эксперт'}
    rows = []
    for record in trial['development_trial']['results']:
        result = record['result']
        expected = expectations[record['case_id']]
        rows.append([escape(record['case_id']), escape(expected['scenario']),
                     escape(result['criterion_id']), statuses[result['status']],
                     'Да' if result['status'] == expected['expected_status'] else 'Нет',
                     f"{record['latency_ms'] / 1000:.2f}".replace('.', ',')])
    return table(['Вариант', 'Ситуация', 'Критерий', 'Ответ GLM', 'Совпал статус', 'Время, с'],
                 rows, 'id="glm-results"', 'Факт · ответы GLM-5.3 от 25.10.2026, одна исходная семья')


def comparison_results(trial):
    names={'glm_full':'GLM, вся карта','glm_filtered':'GLM, доступные документы',
           'mistral_filtered':'Mistral, доступные документы'}
    statuses={'confirmed':'Подтверждено','insufficient_evidence':'Недостаточно сведений',
              'requires_expert':'Требуется эксперт','not_applicable':'Неприменимо',
              'contradiction':'Противоречие'}
    rows=[]
    for condition,result in trial['conditions'].items():
        median=result['latency_median_ms']
        rows.append([names[condition],str(result['completed']),str(result['status_matches']),
                     str(result['all_automatic_checks_passed']),
                     f'{median/1000:.2f}'.replace('.',',') if median is not None else 'нет ответа',
                     str(result['total_tokens_reported'])])
    summary=table(['Условие','Ответов','Верных статусов','Все автоматические проверки','Медиана, с','Токенов по API'],rows,
                  'id="comparison-results"','Факт · новый набор из 12 учебных историй, по одному запуску на условие')
    expectations=read('data/research/comparison-v1/expectations.json')
    records={(r['case_id'],r['condition']):r for r in trial['records']}
    rows=[]
    for expected in expectations:
        cells=[escape(expected['case_id']),escape(expected['purpose']),statuses[expected['expected_status']]]
        for condition in names:
            r=records[(expected['case_id'],condition)]
            value=statuses[r['result']['status']] if r['state']=='completed' else escape(r['state'])
            if r['state']=='completed' and not r['checks']['all_automatic_checks']:
                value+=' · есть замечание'
            cells.append(value)
        rows.append(cells)
    return summary+table(['История','Проверяемая ситуация','Ожидание',*names.values()],rows,
                         'id="comparison-cases"','Факт · статусы по каждому условию; замечания разобраны ниже')


def retrieval_results(trial):
    names={'bm25_all':'BM25 по всем карточкам','bm25_scope_version_filter':'BM25 после фильтра области и версии',
           'exact_known_keys':'Точное извлечение по известным ключам'}
    return table(['Способ','Запросов','Нужная карточка первой','В первых трёх','Неподходящих карточек в первых трёх'],
                 [[names[k],str(v['queries']),str(v['top1_hits']),str(v['top3_hits']),str(v['inapplicable_top3_total'])] for k,v in trial['summary'].items()],
                 'id="retrieval-results"','Факт · 9 авторских карточек и 12 запросов; тема, область и версия заданы вручную')


def stat_chart(plan):
    labels = ['Кровообращение', 'Дыхание', 'Пищеварение', 'Эндокринные', 'Мочеполовые', 'Ухо и сосцевидный отросток']
    parts = ['<figure id="strata-chart"><h4 class="chart-title">Выбывшие пациенты по шести выбранным классам болезней</h4><button type="button" class="chart-legend" aria-pressed="true"><span class="legend-swatch" aria-hidden="true"></span>Выбывшие пациенты · 2024</button><div class="diagram"><svg role="img" aria-label="Выбывшие пациенты по классам, 2024 год, тысячи человек" viewBox="0 0 960 380" xmlns="http://www.w3.org/2000/svg"><title>Число выбывших пациентов, тысячи человек</title><text x="0" y="22" font-size="14">Класс болезней</text>']
    for tick in range(0, 5001, 1000):
        x = 285 + tick / 5000 * 510
        parts.append(f'<path d="M{x:.1f} 36 V312" stroke="#E4E0D6"/><text x="{x:.1f}" y="335" text-anchor="middle" font-size="13">{tick}</text>')
    parts.append('<text x="540" y="365" text-anchor="middle" font-size="14">Выбывшие пациенты, тыс. человек</text><g data-series="discharged">')
    for i, (s, label) in enumerate(zip(plan['strata'], labels)):
        y = 58 + i * 43
        n = s['discharged_thousand_2024']
        w = n / 5000 * 510
        parts.extend([f'<g class="chart-bar" tabindex="0" data-index="{i}" aria-label="{label}: {n} тыс. человек"><title>{label}: {n} тыс. человек</title><text x="0" y="{y}" font-size="16">{label}</text>',
                      f'<rect x="285" y="{y-19}" width="{w:.2f}" height="26" fill="#E2A12B"/>',
                      f'<text class="chart-value" x="{285+w+10:.2f}" y="{y}" font-size="16">{n:,}</text></g>'.replace(',', ' ')])
    parts.append('</g></svg></div><p class="chart-note" aria-live="polite">Наведите на столбец или выберите его клавишей Tab, чтобы увидеть точное значение.</p><figcaption>РФ, 2024 год. Все возраста и профили стационара; 6 выбранных классов, 13 415 тыс. выбывших пациентов. Это агрегированная статистика, не выборка проекта. Источник: Росстат, таблица 3.17, с. 97; <a href="assets/research-evidence.json">assets/research-evidence.json</a>, sampling_plan.</figcaption></figure>')
    return ''.join(parts)


def main():
    inputs = read('reports/generation/week-1-input.json')
    generation_prompt(inputs)
    sources = read('research/sources.json')
    by_source = {s['id']: s for s in sources}
    comparisons = read('research/competitors.json')
    plan = read('research/sampling-plan.json')
    cases = read('data/research/base-cases.json')
    seeds = {s['id']: s for s in read('data/research/scenario-seeds.json')}
    checks = test_summary(ROOT / 'reports/checks/pytest-revision.xml')
    strengthening = test_summary(ROOT / 'reports/checks/pytest-strengthening.xml')
    glm_checks = test_summary(ROOT / 'reports/checks/pytest-glm.xml')
    glm_trial = read('reports/checks/glm-trial-2026-10-25.json')
    comparison_checks = test_summary(ROOT / 'reports/checks/pytest-comparison.xml')
    comparison_trial = read('reports/checks/comparison-2026-10-25.json')
    retrieval_trial = read('reports/checks/retrieval-comparison-2026-10-25.json')
    old_checks = test_summary(ROOT / 'reports/checks/pytest.xml')
    reference = test_summary(ROOT / 'reports/checks/reference-mistral.xml')
    if any(r['failures'] or r['errors'] for r in (checks, strengthening, glm_checks, comparison_checks, old_checks, reference)):
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
              '<div data-table="competitors"></div>':comp_table,
              '<div data-table="feature-coverage"></div>':feature_packet(),
              '<div data-table="glm-trial"></div>':glm_results(glm_trial),
              '<div data-table="comparison-results"></div>':comparison_results(comparison_trial),
              '<div data-table="retrieval-results"></div>':retrieval_results(retrieval_trial),
              '<div data-demo="case"></div>':case_walkthrough()}
    for i,c in enumerate(comparisons):
        blocks[f"<div data-flow='{c['name']}'></div>"] = f'<div id="solution-{i}">'+flow(c['flow'], c['name'])+'</div>'
    chapters, nav, endings = [], [], []
    order = ['01-scope','02-research','09-documents','03-data','04-architecture','05-feature','06-evaluation','07-models','08-validation','10-next-steps']
    for n,name in enumerate(order,1):
        source = ROOT / 'docs' / (name+'.md')
        txt = source.read_text()
        if name == '10-next-steps':
            txt, failure, next_steps = re.split(r'(?m)^## (?:Что не получилось и почему|Следующие шаги: неделя 2)\n', txt)
            txt = txt.replace('# Выполнение первого этапа и следующие шаги', '# Выполнение первого этапа', 1)
            for section_id, heading, prose in [('failed','Что не получилось и почему',failure), ('next','Следующие шаги: неделя 2',next_steps)]:
                content = markdown.markdown(prose, extensions=['tables','fenced_code'])
                content = content.replace('<table>','<div class="table-wrap"><table>').replace('</table>','</table></div>')
                endings.append(report_section(section_id, f'<h2>{heading}</h2>'+content))
        title = txt.splitlines()[0].removeprefix('# ')
        body = markdown.markdown(txt,extensions=['tables','fenced_code'])
        body = re.sub(r'<(/?)h([1-5])>',lambda m:f'<{m[1]}h{int(m[2])+1}>',body)
        body = body.replace('</h2>', '</h2><p class="takeaway"><strong>Вывод:</strong> '+escape(inputs['takeaways'][name])+'</p>', 1)
        body = body.replace('<table>','<div class="table-wrap"><table>').replace('</table>','</table></div>')
        body = label_prose(body, name)
        for token,value in blocks.items():
            body=body.replace(token,value)
        chapter_id = f'chapter-{n}'
        chapters.append(report_section(chapter_id, body))
        nav.append(f'<li><a href="#{chapter_id}">{escape(title)}</a></li>')
    status_labels = {'worked':'Сработало','partial':'Частично','failed':'Не сработало'}
    results = [[escape(row[k]) for k in ('approach','action','result','conclusion')] +
               [f'<span class="status {row["status"]}">{status_labels[row["status"]]}</span>'] for row in inputs['rows']]
    summary = table(['Подход','Что делал','Результат','Вывод','Статус'], results,
                    'id="summary-table"', 'Что пробовали и что получилось')
    summary_index = iter(inputs['rows'])
    summary = re.sub(r'<tr>(?=<td>)', lambda _: f'<tr data-status="{next(summary_index)["status"]}">', summary)
    col_index = iter(range(5))
    summary = re.sub(r'<th scope="col">(.*?)</th>', lambda m: f'<th scope="col" aria-sort="none"><button class="sort" data-sort="{next(col_index)}" type="button">{m[1]} <span aria-hidden="true">↕</span></button></th>', summary)
    summary = '<div class="summary-filters" role="group" aria-label="Фильтр по статусу">'+''.join(
        f'<button type="button" data-status-filter="{k}" aria-pressed="{str(k=="all").lower()}">{v}</button>'
        for k,v in [('all','Все'),*status_labels.items()])+'</div>'+summary
    summary += f'<p id="summary-count" class="caption" aria-live="polite">Показано: {len(results)} из {len(results)}</p>'
    summary += '<p class="caption">Статусы относятся к выполнению задач исследования и технической подготовки. Они не означают, что клиническая функция уже работает. Даты сохранённых проверок указаны в строках.</p>'
    examples=[]
    for c in cases:
        s=seeds[c['id']]
        docs=''.join(f'<h4>{escape(d["id"])} · событие {escape(d["event_at"][:16])}</h4><p>{escape(d["text"])}</p><p class="meta">Доступно: {escape(d["available_at"])}</p>' for d in c['documents'])
        examples.append(f'<details><summary>{escape(c["id"])} · {escape(c["diagnosis"]["text"])} · возраст: {c["age"]}</summary><p>Код в учебном примере: {escape(c["diagnosis"]["code"])}. Проверка: {escape(c["review_at"])}.</p>{docs}<p><strong>Вопрос эксперту:</strong> {escape(s["expert_question"])}</p></details>')
    source_rows = [[escape(s['id']),f'<a href="{escape(s["url"])}">{escape(s["title"])}</a><br>{escape(s["kind"])}',escape(s['locator']),escape(s['limits'])] for s in sources]
    css = (ROOT / 'scripts/report.css').read_text()
    js = (ROOT / 'scripts/report.js').read_text()
    evidence = {'revision_date':'2026-10-25','revision_tests':checks,'original_tests_2026_10_18':old_checks,
                'strengthening_tests':strengthening,'feature_packet':read('research/feature-packet-manifest.json'),
                'glm_tests':glm_checks,'glm_trial_2026_10_25':glm_trial,
                'comparison_tests':comparison_checks,'comparison_trial_2026_10_25':comparison_trial,
                'comparison_manual_review':read('reports/checks/comparison-manual-review.json'),
                'retrieval_trial_2026_10_25':retrieval_trial,
                'cohort_provenance':read('research/cap-cohort-provenance.json'),
                'reference_tests_2026_10_18':reference,'mistral_live_2026_10_18':live,'mock_smoke_2026_10_18':smoke,
                'sampling_plan':plan,'sources':sources,'source_provenance':read('research/rosstat-provenance.json')}
    html=f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Первая неделя: клинический помощник и экспертиза ОМС</title><style>{css}</style></head><body>
<header id="top"><h1>Отчёт за первую неделю</h1><p class="subtitle">{escape(inputs["title"])}</p><p class="meta">{escape(inputs["author"])} · Доработка от 25 октября 2026 года<br>Репозиторий: <a href="https://github.com/VAVASTO/ITMO_AIMedicine">VAVASTO/ITMO_AIMedicine</a></p><p>{escape(inputs["summary"])}</p></header>
<main><section id="summary"><h2>Что пробовали и что получилось</h2>{summary}<p><strong>Решение:</strong> {escape(inputs["verdict"])}</p></section><div class="toolbar" role="group" aria-label="Чтение отчёта"><a href="#contents">Содержание</a><button id="expand-all" type="button">Развернуть всё</button><button id="collapse-all" type="button">Свернуть всё</button><button id="print-report" type="button">Печать / PDF</button></div><p id="print-help" class="caption" aria-live="polite"></p><nav id="contents" aria-label="Содержание"><h2>Содержание</h2><ol>{''.join(nav)}<li><a href="#examples">Примеры для согласования</a></li><li><a href="#sources">Источники и ограничения</a></li><li><a href="#checks">Подтверждение технических проверок</a></li><li><a href="#failed">Что не получилось и почему</a></li><li><a href="#next">Следующие шаги: неделя 2</a></li></ol></nav>
{''.join(chapters)}
<section class="chapter" id="examples"><h2>Примеры для согласования</h2><p>12 вымышленных заготовок для обсуждения с врачом и экспертом. В них показана часть документов, а не полная история болезни. Показания к госпитализации, кодирование и клиническая достаточность ещё не подтверждены. Ожидаемые инженерные реакции хранятся отдельно от входных данных.</p>{''.join(examples)}</section>
<section class="chapter" id="sources"><h2>Источники и ограничения</h2><p>Дата обращения: 25 октября 2026 года. Для каждого источника указал, что именно проверял и какие выводы из него делать нельзя. Нормативный документ перед использованием нужно связать с датой конкретного случая.</p>{table(['ID','Источник','Место подтверждения','Ограничение'],source_rows)}</section>
<section class="chapter" id="checks"><h2>Подтверждение технических проверок</h2><p>Приложения: <a href="assets/research-evidence.json">источники, расчёт выборки и результаты проверок</a>; <a href="assets/review-examples.json">примеры и вопросы эксперту</a>; <a href="assets/feature-packet.json">14 вариантов первой функции с ожиданиями</a>; <a href="checks/glm-trial-2026-10-25.json">первая проба GLM</a>; <a href="checks/comparison-2026-10-25.json">сравнение GLM и Mistral</a>; <a href="checks/comparison-manual-review.json">разбор объяснений</a>. Порядок воспроизведения приведён в <a href="https://github.com/VAVASTO/ITMO_AIMedicine#проверки-и-сборка-отчёта">README репозитория</a>.</p><p>Предыдущая доработка: {checks['tests']} тестов. После усиления отчёта: {strengthening['tests']}. После подключения GLM: {glm_checks['tests']}. После сравнения моделей: {comparison_checks['tests']}, ошибок {comparison_checks['errors']}, падений {comparison_checks['failures']}. Предупреждение HTTPX осталось прежним. Отдельная проба GLM дала 14 совпавших целевых статусов, но выявила сведения из будущего документа в одном объяснении. Затем провёл 36 новых запросов на 12 историях: GLM дала 12/12 ожидаемых статусов, Mistral 10/12. Клиническую точность и полный контракт функции пока не оценивал.</p><details><summary>Результаты и версии в JSON</summary><pre>{escape(json.dumps(evidence,ensure_ascii=False,indent=2))}</pre></details></section>
{''.join(endings)}</main>
<footer><p>Собрал 25 октября 2026 года. Проверки приложения, запрос Mistral и проба GLM приведены с датами исходных запусков. Воспроизведение: <code>python scripts/build_report.py</code> из корня репозитория с установленными зависимостями; сборка не вызывает модели. <a href="https://github.com/VAVASTO/ITMO_AIMedicine#проверки-и-сборка-отчёта">Порядок установки и проверок</a>.</p><p>Для печати из изолированного окна можно скачать HTML и открыть его отдельно.</p></footer>
<dialog id="diagram-dialog" aria-labelledby="zoom-title"><button type="button" id="close-diagram">Закрыть схему</button><h2 id="zoom-title">Схема</h2><div id="zoom-content"></div></dialog>
<script>{js}</script></body></html>'''
    html = re.sub(r'<section class="chapter" id="([^"]+)">(<h2>.*?</section>)',
                  lambda m: report_section(m[1], m[2].removesuffix('</section>')), html, flags=re.S)
    html = decorate_report(html, inputs, evidence, cases, seeds)
    if re.search(r'data-(?:diagram|table|flow|demo)=',html) or '[@' in html:
        raise ValueError('Unresolved report placeholders')
    for name in ('week-1-report.html','Отчёт_за_первую_неделю.html'):
        (ROOT/'reports'/name).write_text(html)
    (ROOT/'reports/assets/research-evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'reports/assets/review-examples.json').write_text(json.dumps({'purpose':'synthetic examples for expert review; not clinical ground truth','cases':cases,'questions':{k:v['expert_question'] for k,v in seeds.items()}},ensure_ascii=False,indent=2)+'\n')
    print(f'Built week-1-report.html: {len(html.encode())} bytes, {len(sources)} sources, {len(comparisons)} comparisons, {len(cases)} review examples')


if __name__ == '__main__':
    main()
