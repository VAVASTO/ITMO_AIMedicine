"""Build one offline HTML report using the unchanged platform prompt template."""
from datetime import datetime
from html import escape as esc
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from itmo_aimedicine.longitudinal import Case, cards, cases, formal_checks, snapshot
from build_report import table, flow
ROOT=Path(__file__).resolve().parents[1]
read=lambda p:json.loads((ROOT/p).read_text())
STATUS={'worked':'Получилось','partial':'Частично','failed':'Не получилось'}

def main():
    report_date=datetime.now(ZoneInfo('Europe/Moscow'))
    summary=read('reports/therapy/summary.json')
    models=summary['models']
    records=[read(str(p.relative_to(ROOT))) for p in sorted((ROOT/'reports/therapy').glob('*--*.json'))]
    if any(r['status'] in {'submitting','submitted'} for r in records):
        raise SystemExit('Experiment is still running; do not build a final report.')
    tests=ET.parse(ROOT/'reports/checks/pytest-therapy-2026-11-04.xml').getroot()
    suites=list(tests) if tests.tag=='testsuites' else [tests]
    test_count=sum(int(s.attrib['tests']) for s in suites)
    failed=sum(int(s.attrib.get('failures',0))+int(s.attrib.get('errors',0)) for s in suites)
    checks=read('reports/checks/therapy-verification.json')
    parsing=read('research/therapy/parsing-check.json')
    stats=read('research/therapy/statistical-hypotheses.json')
    documents=read('research/therapy/documents.json')
    revision=read('reports/therapy-revision/summary.json')
    revision_records=[read(str(p.relative_to(ROOT))) for p in sorted((ROOT/'reports/therapy-revision').glob('*--*.json'))]
    if any(r['status'] in {'submitting','submitted'} for r in revision_records):
        raise SystemExit('Revision jobs still pending. Reconcile submitted jobs before building the report.')
    retrieval=read('research/therapy/search-check.json')
    search_positive=[r for r in retrieval['results'] if r['pages']]
    search_hits=sum(r['revised_hit3'] for r in search_positive)
    total=sum(m['attempted_jobs'] for m in models.values())
    valid=sum(m['validated_jobs'] for m in models.values())
    metrics='; '.join(f"{name}: {m['audit_correct_checks']}/{m['audit_total_checks']} статусов, {m['plan_exact_snapshots']}/{m['plan_snapshots']} наборов действий" for name,m in models.items())
    rows=[
        {'approach':'Область проекта','action':'Сосредоточился на терапии взрослых; реализовал первый сценарий ВП','result':'1 заболевание, 4 проверки, 20 синтетических историй','conclusion':'Другие терапевтические заболевания добавлю после согласования','status':'worked'},
        {'approach':'Сквозной сценарий','action':'Связал рекомендации, назначения, начало терапии, динамику и проверку','result':'2 роли модели; 22 временных среза; T01 в 3 моментах','conclusion':'Обработка состояния работает; причинная симуляция лечения ещё не реализована','status':'partial'},
        {'approach':'База знаний','action':'Разобрал источник и создал индекс с привязкой к страницам','result':f"73 страницы, {parsing['chunks']} фрагментов, 4 карточки; 2 пустые страницы проверены визуально",'conclusion':'Статус применения редакции проверен в рубрикаторе; формализация и расширение корпуса ожидают согласования','status':'partial'},
        {'approach':'Поиск по PDF','action':'Добавил фильтр разделов, варианты терминов и привязку фрагментов к страницам','result':f"302 фрагмента; нужная страница в первой тройке для {search_hits}/{len(search_positive)} запросов",'conclusion':'Это набор для разработки и повторных проверок; независимая оценка поиска ещё нужна','status':'partial'},
        {'approach':'Статистические основания','action':'Описал выборки, ограничения и гипотезы по трём российским исследованиям','result':'3 источника; 152 пациента в одном, группы 100/300 в другом','conclusion':'Частоты и совместное распределение для генератора пока не восстановлены','status':'partial'},
        {'approach':'Gemini и Gemma','action':'Подключил обе модели через учебный Router, отключил подмену модели и повторы','result':'2 успешных технических запроса; 0 запросов к GLM','conclusion':'Подключение работает; прямой ключ AI Studio пока не получен','status':'worked'},
        {'approach':'Сравнение моделей','action':'Выполнил одинаковые два шага на зафиксированных срезах','result':f'{total} заданий; {valid} ответов прошли схему и проверку ссылок. '+metrics,'conclusion':'Ошибки сохранены; показатели относятся к инженерным ожиданиям','status':'partial'},
        {'approach':'Контроль ответов','action':'Сопоставил выводы моделей с расчётом сроков и области правил','result':'Проверяю 4 статуса и набор действий; расхождения видны в интерфейсе','conclusion':'Корректный JSON не гарантирует правильного решения','status':'worked'},
        {'approach':'Приложение и проверки','action':'Собрал интерфейс с временной шкалой и тремя режимами','result':f'{test_count} тестов, {failed} ошибок; сборка интерфейса: '+('успешна' if checks['frontend_build'] else 'не выполнена'),'conclusion':'Локальная демонстрация готова; внешнего адреса пока нет','status':'partial'},
        {'approach':'Повторный опыт','action':'Сопоставил исходный вариант с готовыми интервалами и независимой проверкой на 8 новых случаях','result':f"{revision['attempted']} заданий; 61 ответ прошёл строгую проверку, 3 отклонены; полный разбор приведён ниже",'conclusion':'Эффект относится к совокупности трёх изменений; одиночные прогоны не доказывают устойчивость','status':'partial'},
        {'approach':'Управляемый сценарий','action':'Добавил действия врача и перевод времени вперёд без API','result':'Назначение, начало лечения, повторный осмотр и пересмотр меняют события и проверки','conclusion':'Ветка состояния задана автором; вероятность исхода и эффект препарата не рассчитываются','status':'partial'},
        {'approach':'Подготовка размещения','action':'Добавил пароль, запрет живых запросов по умолчанию и дневной лимит; подготовил Dockerfile','result':'Защита проверена локально; образ контейнера не собирался, Docker отсутствует','conclusion':'Нужны сервер, HTTPS и согласование раскрытия материалов','status':'partial'},
    ]
    sections=[]
    def section(id,title,takeaway,content,limits,kind='Факт'):
        number=len(sections)+2
        sections.append((id,title,f'<section class="chapter" id="{id}"><details class="chapter-body" open><summary><span class="section-tag">{number:02d} / ЭТАП 2</span><h2>{esc(title)}</h2></summary><p class="takeaway"><span class="claim-kind">{kind}</span><strong>Вывод:</strong> {esc(takeaway)}</p>{content}<div class="limitations"><h3>Ограничения</h3><p>{esc(limits)}</p></div></details></section>'))
    section('scope','Что изменил после замечаний','Первая реализация объединяет две задачи внутри одного терапевтического случая.',
        '<p>Я ограничил проект терапией взрослых. Для первого сквозного опыта выбрал нетяжёлую внебольничную пневмонию в терапевтическом стационаре. Отдельно храню диагноз, назначения врача, начало лечения, повторную оценку и пересмотр тактики.</p>'+
        table(['Замечание','Результат','Что ещё нужно'],[
            ['Фокус на терапии','Явные ограничения возраста, отделения и тяжести','Согласовать очередь заболеваний'],
            ['Единый процесс','Две роли модели, расчёт сроков и управляемая последовательность действий','Построить и проверить клиническую модель эффекта лечения'],
            ['Документы и база знаний','PDF, индекс, карточки и реестр для согласования','Статус 654_2 проверен; получить согласование правил и следующих источников'],
            ['Статистика для симуляции','Три исследования с разными дизайнами','Оценить совместные признаки и переходы'],
            ['Gemini и Gemma','Реальное подключение через Router','Сравнить на независимой врачебной разметке']]),
        'Первый сценарий не покрывает всю терапию. Интервью с врачом и независимой клинической проверки пока нет.')
    section('pipeline','Состояние пациента, рекомендации и проверка','Каждый ответ опирается только на сведения, доступные в выбранный момент.',
        flow(['История и время','Доступные события','Карточки и интервалы','Две роли модели','Сверка программой'],'Схема обработки одного временного среза')+
        '<p>У события есть occurred_at и available_at. Оба времени должны быть не позже момента проверки. Назначение антибиотика и начало терапии хранятся отдельно. Предложение модели не становится фактом назначения и не используется как эталон проверки.</p><p>В T01 можно пройти три момента: до назначения, после начала терапии и после оценки ответа. Для каждого момента обе модели выполнили отдельную пару запросов. Код сравнивает результаты с формальными правилами и показывает расхождения.</p>',
        'Эксперимент использует фиксированные истории; в приложении дополнительно работает управляемая последовательность действий. Медицинский эффект лечения и извлечение событий из свободного текста карт ещё не реализованы.')
    section('knowledge','Документы и база знаний','Начал с одного проверяемого источника и четырёх ограниченных правил.',
        table(['Правило','Положение','Страница','Основание'],[[esc(c['rule_id']),esc(c['title']),str(c['page']),f'<a href="{esc(c["url"])}" target="_blank" rel="noopener">КР 2024</a>'] for c in cards()])+
        f'<p>Источник: «Внебольничная пневмония у взрослых», ID 654_2, 2024. Текст извлечён из 73 страниц; получено {parsing["chunks"]} фрагментов по 1800 символов с шагом 1500. У каждого сохранены страница, смещение и SHA-256. Страницы 72 и 73 визуально пустые.</p>'+
        '<p>Контекст моделей состоит из коротких авторских карточек. Полный текст остаётся в локальном индексе. В первом поиске стр. 13 была третьей после приложения на стр. 65. Новый индекс содержит 302 фрагмента до 1200 символов с перекрытием 200, фильтрует разделы, учитывает начало слова и несколько вариантов терминов. Ссылка и смещение сохраняются для каждого фрагмента. В приложении поиск доступен отдельно; неподтверждённые найденные фрагменты автоматически в модель не подаются.</p>'+
        table(['Запрос','Нужные страницы','Первая тройка нового поиска'],[[esc(r['query']),esc(', '.join(map(str,r['pages'])) or 'Нет релевантного положения'),esc(', '.join(map(str,r['revised_pages'][:3])) or 'Нет результатов')] for r in retrieval['results']])+
        f'<p>На восьми запросах по четырём положениям нужная страница попала в первую тройку {search_hits} раз. По двум посторонним запросам результатов нет. После первой проверки я исправил обработку чисел, сокращений и фильтр стационара, поэтому этот набор считаю регрессионным. Независимого нового набора для поиска пока нет.</p>'+
        '<p>Статус редакции проверил в <a href="https://cr.minzdrav.gov.ru/clin-rec" target="_blank" rel="noopener">каталоге Минздрава</a>: 654_2, «Применяется», дата размещения 23.12.2024. В <a href="https://spulmo.ru/obrazovatelnye-resursy/federalnye-klinicheskie-rekomendatsii/" target="_blank" rel="noopener">каталоге РРО</a> также указана редакция 2024. Проверка выполнена 04.11.2026.</p>'+
        table(['Документ для пилота','Состояние'],[[esc(d['document']),esc(d['status'])] for d in documents['required_for_pilot']])+
        '<p><span class="claim-kind">Гипотеза</span>Следующими документами могут стать КР по ХОБЛ, хронической сердечной недостаточности и сахарному диабету 2 типа. Очередь ещё не согласована.</p>',
        'Визуально проверены используемые положения на стр. 13, 24 и 28. Весь PDF не вычитан. 04.11.2026 в каталоге Минздрава по ID 654 найдена строка 654_2 со статусом «Применяется» и датой размещения 23.12.2024. Это статус на дату просмотра; согласования правил прототипа пока нет.')
    section('data','Статистика и синтетические истории','Источники помогают задать факторы и ограничения; текущий набор проверяет инженерную логику.',
        table(['Источник и выборка','Гипотеза для сценариев','Ограничение'],[[f'<a href="{esc(s["url"])}" target="_blank" rel="noopener">{esc(s["doi"])}</a><p>{esc(s["population"])}</p>',esc(s['hypothesis']),esc(s['limits'])] for s in stats['sources']])+
        '<p>Составил 12 новых историй и 14 временных срезов. Проверяю позднее назначение, отсутствие времени начала терапии, раннюю и поздно внесённую оценку, будущие записи, ухудшение с пересмотром и без него, исключение, отсутствие SpO2 и выход за область применимости. T01 представлена тремя срезами. Ещё восемь случаев добавлены для сравнения версий; всего в проекте 20 историй и 22 временных среза.</p>',
        'Случаи авторские и не являются статистически репрезентативной выборкой. Три среза одной истории зависимы. Совместные распределения, сложная коморбидность и вероятности исходов пока не моделируются.')
    section('harness','Протокол исходного опыта','Зафиксировал входы до запуска и ограничил первый бюджет 56 заданиями.',
        '<p>Для каждого среза сначала вызывается роль рекомендаций, затем роль проверки. Системные инструкции написаны по-английски; ответы нужны по-русски. JSON Schema задаёт перечисления действий и статусов, обязательные поля и порядок правил. Входные записи считаются данными, а не инструкциями.</p><p>Ожидаемые статусы хранятся отдельно и не передаются моделям. Подмена модели отключена. Журнал создаётся до отправки запроса; идентификатор задания сохраняется сразу после получения. Проверка состояния выполняется раз в 10 секунд. Повторных POST-запросов нет.</p><pre><code>schema → one POST /api/v1/jobs → job_id → GET status → validate → compare</code></pre><button class="copy-code">Копировать схему</button>',
        'Один запуск на условие; seed не задаётся. Задержка включает очередь Router. Корректная структура и существующие ссылки не подтверждают смысловую или клиническую правильность ответа.')
    metric_rows=[]
    for name,m in models.items():
        metric_rows.append([esc(name),str(m['attempted_jobs']),f"{m['validated_jobs']}/{m['attempted_jobs']}",f"{m['audit_correct_checks']}/{m['audit_total_checks']}",f"{m['audit_exact_snapshots']}/{m['audit_snapshots']}",f"{m['plan_exact_snapshots']}/{m['plan_snapshots']}",f"{m['latency_median_ms']/1000:.2f}",str(m['tokens'])])
    section('results','Исходные результаты Gemini и Gemma','Сохранил все ответы, включая ошибки в сроках, применимости и действиях.',
        table(['Модель','Заданий','Схема и ссылки','Статусы','Все 4 статуса','Набор действий','Медиана, с/задание','Токены'],metric_rows,caption='Факт · один запуск; 14 срезов на модель, 4 правила на срез')+
        '<figure><h3>Совпадение с инженерными ожиданиями</h3><div id="legend" class="toolbar"></div><svg id="quality-chart" role="img" aria-label="Доля совпадений по двум метрикам, в процентах" viewBox="0 0 700 310"></svg><figcaption>Ось X: доля совпадений, %. Ось Y: модель и метрика. Источник: summary.json, встроен в отчёт. Статусы: до 56 на модель; действия: до 14 наборов. Кнопки скрывают серии.</figcaption></figure>'+
        '<p><span class="claim-kind">Интерпретация</span>Для следующей итерации предварительно выбрал Gemma: 54/56 статусов и 13/14 наборов действий против 51/56 и 7/14 у Gemini. Медиана одного задания выше: 51,47 с против 20,69 с. В локальном интерфейсе Gemma выбрана по умолчанию. Ошибки времени у неё тоже остаются.</p><p><span class="claim-kind">Интерпретация</span>Счётчик статусов проверяет выполнение заданной формализации. Полное совпадение точки требует всех четырёх правильных статусов. Набор действий совпадает только при отсутствии пропусков и лишних рекомендаций. Клиническая правильность объяснений отдельным экспертом не оценивалась.</p>',
        'Небольшой авторский набор; одни и те же случаи использованы для разработки правил. Проверка не даёт оценки обобщения на реальные карты. Во второй роли модели видят свои предыдущие рекомендации, поэтому ошибки шагов могут быть связаны.')
    error_rows=[]
    for name,m in models.items():
        for row in m['audit_details']:
            for err in row['errors']:
                error_rows.append([esc(name),esc(row['case_id']),esc(err['rule']),esc({'met':'Подтверждено','attention':'Нужен разбор','pending':'Срок ещё идёт','unknown':'Недостаточно данных','not_applicable':'Не применяется'}[err['expected']]),esc({'met':'Подтверждено','attention':'Нужен разбор','pending':'Срок ещё идёт','unknown':'Недостаточно данных','not_applicable':'Не применяется'}[err['actual']])])
        for row in m['errors']:
            error_rows.append([esc(name),esc(row['case_id']),esc(row['role']),'Успешный ответ',esc(row['status'])])
    section('errors','Разбор расхождений','Ошибки модели не исправлял в сохранённых результатах.',
        table(['Модель','Случай','Правило / шаг','Ожидание','Ответ'],error_rows or [['Обе модели','Все случаи','Все правила','Совпадение','Расхождений статусов нет']])+
        '<p>В T02 Gemini сочла назначение через 6 часов укладывающимся в 4 часа. В T04 она поставила «Нужен разбор» вместо «Недостаточно данных» для отсутствующей оценки в нужном интервале. В T07 продолжила ожидать после завершения интервала. В T09 распространила исключение CAP02 на другие правила. У Gemma в T05 вместо 52 часов получилось 76; в T08 она сочла ровно 72 часа превышением срока. В T08 набор действий совпал, хотя объяснение содержало ошибку времени. Эти ответы сохранены в исходном виде.</p><p><span class="claim-kind">Интерпретация</span>Вычисление сроков и область исключений нужно проверять кодом. После этого опыта я добавил готовые интервалы в запрос и провёл отдельное сравнение версий, описанное ниже. Сохранённые ответы первого опыта не переписывал.</p>',
        'Ручной разбор сосредоточен на найденных расхождениях и нескольких согласованных ответах. Полного независимого аудита объяснений нет; совпавший статус может сопровождаться неточным рассуждением.')
    revision_error_rows=[]
    result_names={'met':'Подтверждено','attention':'Нужен разбор','pending':'Срок ещё идёт','unknown':'Недостаточно данных','not_applicable':'Не применяется',
                  'measure_spo2':'Уточнить SpO2','review_antibiotic_order':'Проверить назначение','clarify_treatment_start':'Уточнить начало лечения',
                  'schedule_reassessment':'Запланировать оценку','assess_response':'Оценить ответ','review_treatment':'Пересмотреть тактику',
                  'specialist_review':'Разобрать исключение','none':'Нет действия'}
    for group in revision['groups']:
        for item in group['errors']:
            for rule in sorted(set(item['expected']) | set(item['actual'])):
                expected=item['expected'].get(rule,'none'); actual=item['actual'].get(rule,'none')
                if expected!=actual:
                    revision_error_rows.append([esc(group['model']),group['condition'],esc(item['case_id']),
                        'Проверка' if item['role']=='audit' else 'Действия',esc(rule),esc(result_names.get(expected,expected)),esc(result_names.get(actual,actual))])
    section('revision','Повторный опыт: расчёт сроков и независимая проверка','Новую версию сравниваю с исходной на одних и тех же восьми новых случаях.',
        '<p>Добавил рассчитанные программой интервалы в секундах, напоминание о границах конкретного исключения и проверку без черновика рекомендаций. Времена учитывают часовые пояса; ровно 4, 48 и 72 часа и отклонение на одну секунду проверяются отдельно. Ожидаемые статусы и действия записал до запусков; в запрос их не включаю.</p><p>Для каждой модели чередовал порядок версий между случаями. Бюджет составляет 64 задания, по 32 на модель; повторной отправки и подмены модели нет. GLM и Mistral не вызываются. Исходные 56 заданий и два запроса подключения учитываются отдельно.</p>'+
        table(['Модель','Версия','Успешно / отправлено','Статусы среди успешных','Все статусы среза','Наборы действий','Медиана, с'],[[esc(g['model']),esc(g['condition']),f"{g['valid']}/{g['attempted']}",f"{g['audit_checks']}/{g['audit_total']}",f"{g['audit_exact']}/{g['audit_snapshots']}",f"{g['plan_exact']}/{g['plan_snapshots']}",f"{g['latency_median_ms']/1000:.2f}" if g['latency_median_ms'] else 'Нет данных'] for g in revision['groups']])+
        '<h3>Сравнение на общих завершённых случаях</h3>'+
        table(['Модель','Метрика','Общий знаменатель','Исходная версия','Новая версия'],[[esc(p['model']),'Статусы' if p['role']=='audit' else 'Наборы действий',str(p['total']),str(p['scores']['v1']),str(p['scores']['v2'])] for p in revision['paired_complete_cases']])+
        '<h3>Ошибки выполнения и структуры</h3>'+
        table(['Модель','Версия','Случай','Шаг','Причина'],[[esc(g['model']),g['condition'],esc(e['case_id']),esc(e['role']),esc(e.get('error') or e['status'])] for g in revision['groups'] for e in g['technical_errors']])+
        '<p>У Gemma в V04/v1, V05/v2 и V08/v2 ответы завершились в Router, но содержали лишнюю закрывающую Markdown-метку. В V04/v1 также дважды указан CAP02 и отсутствует CAP04. Для приложения добавил узкую очистку внешней разметки и проверил её локально на сохранённых ответах: V05 и V08 после очистки проходят структуру и ссылки, V04 всё ещё отклоняется. Строгие результаты эксперимента не пересчитывал и задания повторно не отправлял. Для V05/v2 и V08/v2 отдельно выполнил ещё не отправленные проверки: в новой версии они не зависят от успешности рекомендаций. Общий бюджет 64 не превышен. Очистка записывается в журнал; в экспериментальном адаптере она по умолчанию отключена.</p>'+
        table(['Модель','Версия','Случай','Шаг','Правило','Ожидание','Ответ'],revision_error_rows)+
        '<p>В первой таблице показаны фактические знаменатели завершённых ответов. Для сопоставления версий отдельно беру только случаи, где завершились обе версии соответствующего шага. Это условное сравнение: ошибки структуры также показаны и не считаются верным ответом. План предусматривал 32 статуса и 8 наборов действий для каждой модели и версии. Новые интервалы помогают проверять арифметику, но не гарантируют правильного выбора статуса или действия.</p>',
        'Проверяется совокупность трёх изменений; вклад каждого отдельно не измерен. Восемь авторских случаев специально нагружают границы сроков, часовые пояса и неполные записи; это не типичная клиническая выборка. Один запуск на условие, независимой врачебной разметки и статистической проверки устойчивости нет. Абсолютные показатели первого и второго наборов напрямую не сравниваю: случаи разные.')
    section('simulation','Действия врача в учебном сценарии','Теперь последовательность действий можно менять в интерфейсе и сразу видеть результат.',
        '<p>Добавил измерение SpO2, запись назначения, начало лечения, повторный осмотр, пересмотр тактики и перевод времени на 2, 24 или 48 часов. Начало лечения доступно после назначения. От этого события отсчитывается интервал повторной оценки. Будущие действия, обратный ход времени и повторное начальное назначение отклоняются.</p><p>В браузере прошёл ветку ухудшения: назначение и начало лечения в 0 ч, повторный осмотр в 48 ч, затем пересмотр. Флаг CAP04 появляется после ухудшения и закрывается записью пересмотра. В тестах повторное ухудшение снова открывает флаг. Пересмотр не меняет саму отметку состояния на улучшение. Все действия выполняются локально без API.</p>',
        'Улучшение, отсутствие изменений или ухудшение выбираются как авторская ветка. Это симуляция последовательности работы; вероятности исходов и физиологический эффект препарата не рассчитаны.')
    section('demo','Пример сквозного запуска','В отчёте можно просмотреть реальные сохранённые ответы по каждому временному срезу.',
        '<div class="demo-controls"><label for="demo-case">История</label><select id="demo-case"></select><label for="demo-point">Момент и версия, МСК</label><select id="demo-point"></select><label for="demo-model">Модель</label><select id="demo-model"></select></div><div id="demo-output" aria-live="polite"></div><p>Это просмотр сохранённых результатов, запросов к API нет. Полное локальное приложение также умеет считать правила и выполнять новый запуск по кнопке.</p>',
        'Публичного адреса пока нет. Локальный сервер привязан к 127.0.0.1. Согласование содержания раскрываемых материалов и аффилиации по NDA остаётся отдельным шагом перед публикацией.')
    section('verification','Проверки и воспроизведение',f'Локальные проверки: {test_count} тестов, {failed} ошибок; сборка интерфейса выполнена.',
        table(['Проверка','Результат'],[[str(k),esc(str(v))] for k,v in checks['visible_checks'].items()])+
        '<pre><code>python -m pytest -q\npython scripts/run_therapy_experiment.py --summarize\npython scripts/build_week2_report.py\nuvicorn itmo_aimedicine.api:app --host 127.0.0.1 --port 8001</code></pre><button class="copy-code">Копировать команды</button>'+
        '<p>Повторная сборка отчёта не вызывает модели. Команда эксперимента с --live разрешает новые запросы только для ещё не отправленных журналов при неизменном протоколе. Ключ хранится вне исходников; в настройках приложения указан путь к локальному файлу.</p>',
        'Автоматические тесты проверяют программные свойства и формальную логику. Клиническая валидация, тест на реальных картах и оценка пользы для врача не выполнены.')
    section('failures','Что не получилось и почему','Доступ к моделям появился, но качество рекомендаций и полнота данных требуют следующей итерации.',
        '<ul><li>Прямой ключ Google AI Studio получить не удалось, в том числе после попытки через VPN. Причина ограничения аккаунта не установлена; для проекта работает доступ через Router.</li><li>Поиск доработан на небольшом наборе по одному документу; независимой оценки на новых вопросах и широкого корпуса пока нет.</li><li>Модели допускают ошибки в статусах и действиях. Совпадение с формальными правилами и корректность объяснений требуют раздельной проверки.</li><li>Статистическая модель течения болезни пока не построена. Три исследования описывают разные выборки и не дают готового совместного распределения.</li><li>Не получены согласование списка документов, экспертная разметка и внешний адрес демонстрации. Для согласования подготовил конкретные вопросы и шаблон разметки в docs/15-clinical-review.md.</li><li>Для размещения подготовил Dockerfile, вход по паролю и лимит запросов. Docker здесь отсутствует, контейнер не проверен; сервер, домен и HTTPS ещё не выбраны.</li></ul>',
        'Готовность локального прототипа не означает, что все требования к сдаче этапа уже закрыты.')
    section('next','Следующие шаги','Технические доработки подготовлены; дальше нужны независимая разметка, данные для динамики и размещение.',
        '<ol><li>Получить подтверждение списка документов, редакции КР и четырёх правил.</li><li>Дать врачу 20 историй и правила без авторских ответов; получить независимую разметку, затем разобрать расхождения.</li><li>Выбрать данные о совместных признаках и исходах для вероятностной модели; пока использовать управляемые авторские ветки.</li><li>Разобрать оставшиеся ошибки моделей, добавить независимые случаи и повторные прогоны в пределах квоты Router.</li><li>Проверить поиск на новых вопросах и расширить корпус после согласования редакций.</li><li>Выбрать сервер, проверить контейнер и HTTPS; согласовать раскрываемые материалы, авторство и аффилиацию по NDA.</li><li>После этих проверок загрузить HTML, ссылки на репозиторий и демонстрацию на платформу.</li></ol>',
        'В этом отчёте фиксирую выполненное; перечисленные действия не обозначены как завершённые.',kind='Интерпретация')
    summary_html='<section class="card" id="summary"><span class="section-tag">01 / ОБЗОР</span><h2>Что пробовали и что получилось</h2><div class="toolbar" id="summary-filter">'+''.join(f'<button data-status="{k}" aria-pressed="{str(k=="all").lower()}">{v}</button>' for k,v in [('all','Все'),*STATUS.items()])+'</div><label>Сортировка <select id="summary-sort"><option value="original">По порядку работы</option><option value="approach">По подходу</option><option value="status">По статусу</option></select></label>'+table(['Подход','Что сделал','Результат','Вывод','Статус'],[[esc(r['approach']),esc(r['action']),esc(r['result']),esc(r['conclusion']),f'<span class="status {r["status"]}">{STATUS[r["status"]]}</span>'] for r in rows],attrs='id="summary-table"')+'<p><strong>Итог:</strong> локальный сквозной прототип и сравнение двух моделей готовы; согласование и внешняя демонстрация остаются открытыми.</p></section>'
    replay=[]
    for case in cases():
        for i,t in enumerate(case.review_times):
            item={'case_id':case.id,'title':case.title,'checkpoint':i,'review_at':t.isoformat(),'state':snapshot(case,t),'formal':formal_checks(snapshot(case,t)).model_dump(),'models':{}}
            for name in models:
                item['models'][name]={r['role']:r.get('completion',{}).get('result') for r in records if r['case_id']==case.id and r['checkpoint']==i and r['model']==name and r['status']=='ok'}
            replay.append(item)
    for raw in read('data/therapy/revision-cases.json'):
        case=Case.model_validate(raw); t=case.review_times[0]
        for index,condition in enumerate(('v1','v2')):
            item={'case_id':case.id,'title':case.title,'checkpoint':index,'condition':condition,
                  'review_at':t.isoformat(),'state':snapshot(case,t),'formal':formal_checks(snapshot(case,t)).model_dump(),'models':{}}
            for name in models:
                item['models'][name]={r['role']:r.get('completion',{}).get('result') for r in revision_records
                    if r['case_id']==case.id and r['condition']==condition and r['model']==name and r['status']=='ok'}
            replay.append(item)
    evidence={'summary':summary,'revision':revision,'retrieval':retrieval,'rows':rows,'replay':replay,'cards':cards(),'stats':stats,'documents':documents,'verification':checks}
    encoded=json.dumps(evidence,ensure_ascii=False).replace('<','\\u003c')
    css=(ROOT/'scripts/report.css').read_text()+'\n.demo-controls{display:grid;gap:8px;margin-bottom:20px}.demo-controls select{max-width:100%;width:100%}#quality-chart{width:100%;height:auto}.chart-legend[aria-pressed="false"]{opacity:.5}pre{max-width:100%;overflow:auto}.status{display:inline-block;padding:4px 8px;border-radius:5px}.status.worked{background:#E6F4F1;color:#17685c}.status.partial{background:#FCF3E1;color:#80560b}.status.failed{background:#FBEAE8;color:#B3261E}body{overflow-wrap:anywhere}@media print{.toolbar,.demo-controls,.copy-code{display:none}.reading-layout{display:block}.reading-tools{display:none}details>*{display:block!important}}'
    nav='<nav class="reading-tools" aria-label="Разделы"><div class="toolbar"><button id="expand">Раскрыть всё</button><button id="collapse">Свернуть всё</button></div><ol>'+''.join(f'<li><a href="#{id}"><span class="nav-number">{i+2:02d}</span>{esc(title)}</a></li>' for i,(id,title,_) in enumerate(sections))+'</ol></nav>'
    js=(ROOT/'scripts/week2-report.js').read_text()
    html=f'''<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Неделя 2. Сквозной сценарий в терапии</title><link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@400;600;700&amp;family=Instrument+Sans:wght@400;500;600&amp;family=JetBrains+Mono:wght@400;500&amp;display=swap" rel="stylesheet"><style>{css}</style></head><body><header><div class="eyebrow">ИТМО · AIMedicine · Этап 2</div><h1>Сквозной сценарий в терапии</h1><p class="subtitle">Неделя 2 · {report_date:%d.%m.%Y}</p><p>Я подключил Gemini и Gemma через Router, связал рекомендации с временной историей и проверкой назначений. После первого сравнения добавил расчёт сроков, независимую проверку, поиск по документу и управляемый сценарий действий врача. Сопоставил исходную и новую версии на восьми новых случаях. Ошибки и незавершённые пункты указал отдельно. Дальше нужны согласование документов, врачебная разметка и закрытое размещение.</p><div class="stat-grid"><div class="stat-tile"><strong>20</strong><span>вымышленных историй</span></div><div class="stat-tile"><strong>22</strong><span>момента проверки</span></div><div class="stat-tile"><strong>{total+revision["attempted"]}</strong><span>заданий двух опытов</span></div><div class="stat-tile"><strong>4</strong><span>правила пилота</span></div></div></header><main>{summary_html}<div class="reading-layout">{nav}<div class="reading-body">{''.join(s[2] for s in sections)}</div></div></main><footer>Собрал {report_date:%d.%m.%Y}. Данные и результаты встроены в HTML. Отчёт можно открыть без локального сервера. Исходники: scripts/build_week2_report.py; протокол: reports/therapy/manifest.json. На платформу отчёт пока не загружен.</footer><script id="evidence" type="application/json">{encoded}</script><script>{js}</script></body></html>'''
    (ROOT/'reports/week-2-report.html').write_text(html)
    inputs={'week':2,'title':'Сквозной сценарий в терапии','context':'Я ограничил проект терапией взрослых, доработал расчёт сроков, поиск и управляемый сценарий для пневмонии. Все случаи синтетические. Gemini и Gemma подключены через Router; результаты, ошибки и ограничения зафиксированы. Публикации и клинической валидации пока нет.','rows':rows,'sections':[s[1] for s in sections],'assets':[],'preferences':'Писать по-русски от первого лица мужского рода. Сохранить дизайн, цвета, последовательные номера и метки Факт/Интерпретация/Гипотеза исходного промпта. Все данные встроить в HTML. Ничего не выдавать за клиническую валидацию, согласование или публичную демонстрацию.'}
    template=(ROOT/'reports/generation/platform-template.txt').read_text()
    replacements={'(not provided)':inputs['context'],'(choose a precise title based on the context)':'Неделя 2. Сквозной сценарий в терапии','(no rows were provided: build the table skeleton and mark every empty cell with the badge "нужно уточнить")':json.dumps(rows,ensure_ascii=False,indent=2),'(no extra sections were requested: derive sensible sections from the summary rows)':'\n'.join(inputs['sections']),'(no assets were uploaded: use only the data given in this prompt)':'Все материалы и результаты встроены в local_materials; внешних файлов для загрузки нет.','(none)':inputs['preferences']}
    for placeholder,value in replacements.items():
        if template.count(placeholder)!=1: raise ValueError('Platform template changed')
        template=template.replace(placeholder,value,1)
    template+='\n<local_materials>\n'+json.dumps(evidence,ensure_ascii=False,indent=2)+'\n</local_materials>\n'
    (ROOT/'reports/generation/week-2-input.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n')
    (ROOT/'reports/generation/week-2-prompt.txt').write_text(template)
    print('Built week-2-report.html:',len(html.encode()),'bytes;',len(sections),'sections;',total+revision['attempted'],'jobs in two experiments')

if __name__=='__main__':main()
