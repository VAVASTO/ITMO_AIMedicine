"""Standalone follow-up report; preserves the submitted week-two report."""
from datetime import datetime
from html import escape as esc
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from itmo_aimedicine.config import ROOT
from itmo_aimedicine.therapy_expansion import registry,cases,snapshot,check
from build_report import table

read=lambda path:json.loads((ROOT/path).read_text())


def main():
    reg=registry();stats=read('research/therapy-expansion/rationale.json')
    synthea=read('research/therapy-expansion/synthea-manifest.json')
    models=read('reports/therapy-expansion/summary.json');parsing=read('research/therapy-expansion/parsing.json')
    repeat_path=ROOT/'reports/therapy-expansion-gemma-compatible/summary.json'
    repeat=read(str(repeat_path.relative_to(ROOT))) if repeat_path.exists() else None
    repeat_group=repeat['groups'][0] if repeat else None
    main_jobs=models['attempted']+(repeat['attempted'] if repeat else 0)
    search=read('research/therapy-expansion/search-check.json');package=read('research/therapy-expansion/static-package.json')
    tests=ET.parse(ROOT/'reports/checks/expansion-tests.xml').getroot()
    suites=list(tests) if tests.tag=='testsuites' else [tests]
    total=sum(int(s.get('tests',0)) for s in suites);failed=sum(int(s.get('failures',0))+int(s.get('errors',0)) for s in suites)
    date=datetime.now(ZoneInfo('Europe/Moscow')).strftime('%d.%m.%Y')
    rows=[
      dict(approach='Пять заболеваний',action='Добавил ВП, ХОБЛ, АГ, ХСН и СД2; описал основания выбора',result='5 рабочих профилей, 15 авторских историй',conclusion='Кандидатный набор; доля покрытия терапии пока неизвестна',status='partial'),
      dict(approach='До десяти классов проверки',action='Разделил проверки по категориям и написал контракты',result='10 категорий, 17 проверок',conclusion='Проверки работают; клинические критерии ещё не согласованы',status='worked'),
      dict(approach='Другие и более новые документы',action='Добавил КР четырёх направлений и алгоритмы по диабету 2025 года',result='6 документов, '+str(parsing['passages'])+' поисковых фрагментов',conclusion='Редакции закреплены; полнота проверки актуальности в рубрикаторе не подтверждена',status='partial'),
      dict(approach='Synthea',action='Запустил генератор и написал импорт CSV',result='130 пациентов, 10 примеров в приложении',conclusion='Формат протестирован; российские частоты и отделения не восстановлены',status='worked'),
      dict(approach='Проверка моделей',action='Провёл ограниченный опыт на пяти срезах',result='20 заданий, 0 GLM; Gemini 85/85 статусов, 1/5 наборов действий',conclusion='Gemma: 10 ошибок BAD_REQUEST. Сравнение качества двух моделей не завершено',status='partial'),
      dict(approach='Демо',action='Запустил локальную версию и закрытый бесплатный Static Space',result=f"{package['views']} подготовленных состояний; без ключей и новых запросов",conclusion='Демо работает. Доступ преподавателю ещё не предоставлен; видеозапись пока не подготовлена',status='partial'),
      dict(approach='Проверки реализации',action='Проверил границы сроков, доступность записей, импорт и API',result=f'{total} тестов, {failed} ошибок',conclusion='Инженерная проверка не заменяет врачебную разметку',status='worked'),
    ]
    if repeat_group:
        g=repeat_group
        rows[4].update(action='Провёл исходную серию и отдельный повтор Gemma после исправления схемы',
          result=f"Gemini: 85/85 статусов, 1/5 полных наборов действий; Gemma: {g['correct_checks']}/{g['scored_checks']} статусов, {g['exact_plans']}/{g['valid_plans']} полных наборов действий",
          conclusion=f"В повторе {g['valid']}/{g['attempted']} ответов прошли проверку. Исходные ошибки сохранены; настройки серий различаются.")
    sections=[]
    def section(id,title,kind,takeaway,content,limit):
        number=len(sections)+2
        sections.append((id,title,f'<section class="chapter" id="{id}"><details class="chapter-body" open><summary><span class="section-tag">{number:02d} / ДОРАБОТКА</span><h2>{esc(title)}</h2></summary><p class="takeaway"><span class="claim-kind">{kind}</span>{esc(takeaway)}</p>{content}<div class="limitations"><h3>Ограничения</h3><p>{esc(limit)}</p></div></details></section>'))
    links=lambda url,text:f'<a href="{esc(url,quote=True)}" target="_blank" rel="noopener">{esc(text)}</a>'
    section('profiles','Почему выбрал эти направления','Интерпретация','Расширил пилот по разным сценариям терапевтического наблюдения; не объявляю выбранные болезни самыми частыми.',
      table(['Профиль','Основание и показатель','Что означает выборка','Гипотеза'],[[reg['profiles'][r['profile']]['name'],r['decision']+' '+r['number'],r['denominator'],r['hypothesis']] for r in stats['profiles']])+
      '<ul>'+''.join('<li>'+links(r['source'],r['profile']+': '+r['study'])+'. '+esc(r['limit'])+'</li>' for r in stats['profiles'])+'</ul>'+
      '<p>Все пять профилей имеют одинаковое число авторских сценариев. Это проверка покрытия функций. Проценты из разных исследований не складываю и не превращаю в вероятности генератора. Грипп/COVID и болезни пищеварения остаются кандидатами; отсутствие в этой версии не означает меньшую распространённость.</p>',
      stats['rosstat_note']+' Нужны данные о диагнозах выписанных взрослых именно из терапевтических отделений, с регионом, годом и сопутствующими состояниями.')
    section('documents','Документы и сравнение редакций','Факт','Собрал корпус из пяти клинических рекомендаций и отдельного документа 2025 года.',
      table(['Документ','Год','Страницы PDF','Использование'],[[s['title'],s['year'],', '.join(map(str,s['pdf_pages'])),s['summary']] for s in reg['sources'] if s['url']])+
      '<ul>'+''.join('<li>'+links(s['url'],s['id'])+' · SHA-256 <code>'+esc(s['sha256'])+'</code></li>' for s in reg['sources'] if s['url'])+'</ul>'+
      '<p>Визуально проверил титульную страницу КР СД2 2022 года, минимум обследования при госпитализации с ХОБЛ и таблицу наблюдения в алгоритмах 2025 года. В последней осмотр ног при каждом посещении и ежегодная оценка чувствительности стоп разделены. Этот нюанс вынес на согласование, вместо автоматической замены одного правила другим.</p>'+
      f'<p>Локальный индекс содержит {sum(s["pdf_pages"] for s in parsing["sources"])} страниц PDF и {parsing["passages"]} фрагментов. В пяти из шести авторских поисковых запросов нужная страница вошла в первые пять результатов. Запрос по калию и креатинину при АГ не вывел нужную страницу в первую пятёрку. Поиск не отправляет найденный текст в модель автоматически.</p>',
      'Рубрикатор не загрузил список, поэтому не утверждаю, что собрал последние применимые редакции. Приказ 203н 2025 года найден как кандидат для дальнейшего разбора; правовые критерии и штрафы не автоматизированы. Визуально проверены выбранные страницы, не весь корпус.')
    section('rules','Десять категорий и 17 проверок','Факт','Расширил проверку записей, сохранил различие между назначением, введением, ответом на лечение и выпиской.',
      table(['Категория','Реализованные проверки'],[[c['name'],'; '.join(r['id']+' '+r['title'] for r in reg['rules'] if r['category']==c['id'])] for c in reg['categories']])+
      '<p>Проверяю только сведения, которые возникли и стали доступны к выбранному моменту. Пропущенный результат даёт «недостаточно данных». Позднее внесение аллергоанамнеза не исправляет его отсутствие при назначении. Пустой список аллергий и запись «известных аллергий нет» различаются.</p>'+
      '<p>Срок госпитализации не равен автоматически длительности антибиотикотерапии. В полном авторском примере поступление произошло в час 0, назначение в час 2, первое введение в час 3, завершение курса в час 96, выписка в час 120. Получаются 120 часов госпитализации и 93 часа между началом и окончанием курса. Это временные метки вымышленного примера, а не рекомендуемая длительность лечения.</p>',
      'Числовые результаты, правильность доз, взаимодействия и перекрёстные аллергии не оцениваются. Выбранные исследования не составляют полный обязательный перечень. Для АГ и ЭхоКГ окна давности заданы автором; 90 и 365 дней для календарных сроков СД2 тоже требуют проверки.')
    section('synthea','Что получилось с Synthea','Факт','Запустил официальный генератор и проверил импорт его данных в прототип.',
      '<p>'+links('https://github.com/synthetichealth/synthea','Synthea, официальный репозиторий')+': сборка от 21.10.2026, seed 20261108, дата моделирования 08.11.2026, 100 живых пациентов 35–85 лет, Massachusetts по умолчанию. Генератор дополнительно экспортировал 30 умерших в ходе моделирования. Использовал Java 17.</p>'+
      table(['Показатель','Результат'],[['Экспортировано пациентов',synthea['patients_exported']],['Живых / умерших в модели',f"{synthea['alive_exported']} / {synthea['deceased_exported']}"],['Обращений / inpatient',f"{sum(synthea['encounter_classes'].values())} / {synthea['encounter_classes']['inpatient']}"],['Примеров в приложении',synthea['imported_cases']]])+
      table(['Диагноз когда-либо в синтетической истории','Пациентов из 130'],[[reg['profiles'][p]['name'],n] for p,n in synthea['patients_ever_with_profile'].items()])+
      '<p>Профили пересекаются. Это исторические диагнозы в симуляторе, не распространённость в российской терапии. В интерфейс перенёс по два примера на направление. Имена, адреса и полная сырая выгрузка в пакет не входят.</p>'+
      '<p>Не выдумывал время введения препарата, отрицательный аллергоанамнез или российское отделение. Случаи Synthea по умолчанию находятся вне области правил. Для учебного просмотра можно явно предположить терапевтическое отделение. В CSV нет времени внесения записи; при импорте оно приравнено времени события и это допущение сохранено.</p>',
      'Российская калибровка, проверка тяжести и клиническая реалистичность не выполнены. Два примера на профиль выбраны для теста формата. Для воспроизведения нужны закреплённый JAR и конфигурация; изменяемого тега master-branch-latest недостаточно.')
    model_groups=[(g,'Исходная, 8192 токена') for g in models['groups']]
    if repeat_group:model_groups.append((repeat_group,'Повтор, 4096 токенов, упрощена схема сервиса'))
    repeat_text=''
    if repeat_group:
        g=repeat_group
        repeat_text=(
          '<p>Короткий тест связи с Gemma прошёл. Полный запрос с прежней схемой был отклонён и при лимите 4096; короткий технический текст с той же схемой тоже дал BAD_REQUEST. Затем удалил только minItems/maxItems из схемы, передаваемой сервису: полный исходный случай прошёл. Это локализует проблему в обработке ограничений схемы на доступном маршруте; конкретный внутренний компонент Router мне неизвестен.</p>'+
          '<p>Локальная проверка осталась прежней: ровно 17 уникальных правил в заданном порядке, допустимые статусы и ссылки на доступные события и источники. Неполные ответы не принимаются. Поля и значения ответа не исправляются.</p>'+
          '<p>Сервис вернул все 10 ответов повторной серии. Один ответ проверки СД2 сослался на документ DM22020, которого нет в разрешённом наборе. Этот ответ исключён целиком; 65/68 относится к четырём принятым ответам по 17 правил, а не ко всем пяти случаям. Во всех трёх ошибках статуса Gemma посчитала недостаточными записи наблюдений Q04. Во всех пяти планах были лишние действия. Случаи СД2 и ХОБЛ с полной записью получили лишнее предложение уточнить Q15.</p>'+
          f"<p>В отдельном повторе Gemma: {g['valid']}/{g['attempted']} ответов прошли проверку, статусы {g['correct_checks']}/{g['scored_checks']}, полные наборы действий {g['exact_plans']}/{g['valid_plans']}. Успешный диагностический ответ включён как первый ответ серии, второй раз его не запрашивал. Истории, инструкции и эталон взяты из исходного опыта без изменений.</p>"+
          '<p>Основные серии содержат 20 исходных и 10 повторных заданий. Отдельно выполнил три диагностических запроса: успешный тест связи и два отказа со старой схемой. GLM и Mistral не использовал. Разные лимиты ответа, схема сервиса и время запуска не позволяют считать это сравнением моделей в полностью одинаковых условиях.</p>'+
          '<p>Наблюдение согласуется с '+links('https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/capabilities/control-generated-output#considerations','документацией Google о сложности схемы')+': сочетание ограничений массивов и перечислений может приводить к InvalidArgument. Это объяснение механизма, а не подтверждение внутреннего устройства учебного Router.</p>')
    section('models','Модели: результат и ошибки','Факт',
      'Gemma вернула ответы после упрощения схемы сервиса. Исходная серия и повтор оценены отдельно.' if repeat else 'Gemini правильно определила статусы, но ошибалась в действиях. Gemma не вернула ответов для оценки.',
      table(['Модель / серия','Задания / прошли проверку','Статусы','Полный набор действий','Медиана успешного ответа'],[[g['model']+' · '+label,f"{g['attempted']} / {g['valid']}",f"{g['correct_checks']} / {g['scored_checks']}" if g['scored_checks'] else 'Не оценено',f"{g['exact_plans']} / {g['valid_plans']}" if g['valid_plans'] else 'Не оценено',str(round(g['latency_median_ms']/1000,2))+' с' if g['latency_median_ms'] else 'Нет успешных ответов'] for g,label in model_groups])+
      '<p>Использовал пять заранее зафиксированных срезов и две независимые роли. Вход одинаков для обеих моделей: доступные события, контракты и рассчитанные интервалы. Разметка и ответ другой роли не передаются. Исходная серия: 20 заданий, по 10 на модель, без автоматических повторов и подмены. К GLM и Mistral не обращался.</p>'+
      '<p>У Gemini все 85 статусов совпали с авторской разметкой. Полностью совпал только один из пяти наборов действий: встречались пропуски проверки плана и лишние действия по неприменимым правилам. В интерфейсе эти расхождения выделены отдельно от проверки формата.</p>'+
      '<p>В исходной серии все задания Gemma завершились BAD_REQUEST: Router сообщил о недопустимом аргументе, но не назвал его. Эти ошибки сохранены и не оценивают качество медицинских ответов.</p>'+repeat_text,
      'Это небольшой инженерный опыт на авторских случаях, по одному запуску каждой роли. Врачебного эталона, оценки устойчивости и статистической значимости нет. Правильный статус не гарантирует правильного действия.')
    demo=read('research/therapy-expansion/deployment.json') if (ROOT/'research/therapy-expansion/deployment.json').exists() else {'status':'prepared','url':None}
    section('demo','Приложение и бесплатное размещение','Факт','Полная версия работает локально; для бесплатного хостинга собрал отдельный показ подготовленных результатов.',
      f'<p>В бесплатном пакете {package["cases"]} историй и {package["views"]} подготовленных состояний: выбор заболевания, времени, учебного допущения для Synthea и одной дополнительной записи. Сохранённые ответы моделей можно раскрыть и сопоставить с проверкой. Новые запросы не отправляются.</p>'+
      '<p>Статический пакет не обрабатывает произвольную историю. Полная локальная версия выполняет проверки заново, позволяет добавить несколько записей и искать по полным текстам. Предыдущий пилот ВП сохранён в отдельной вкладке.</p>'+
      '<p>Для бесплатного размещения выбрал закрытый Static Space на Hugging Face. Ключей, полных PDF и сырых выгрузок в нём нет. Вход в аккаунт необходим; без авторизации сервер возвращает 401.</p>'+
      ('<p>Адрес: '+links(demo['url'],demo['url'])+'. Демо запущено; доступ закрытый. Доступ преподавателю предоставлю отдельно. Видеозапись пока не подготовлена.</p>' if demo.get('url') else '<p>Внешний адрес пока не получен: пакет готов, ожидается вход в аккаунт Hugging Face.</p>'),
      'Это раннее демонстрационное приложение. Публичного размещения и доступа экспертов пока нет. Оплату и платные ресурсы не подключал.')
    section('checks','Проверка реализации','Факт',f'Автоматические проверки: {total} тестов, {failed} ошибок.',
      '<p>Проверил границы 4 часов и 48–72 часов, запоздалую доступность данных, разные часовые пояса, давность HbA1c, локальность исключений, несовпадение лекарства при введении, пропущенную связь с планом и выход за область взрослой терапии.</p>'+
      '<p>Через браузер проверил смену профиля и набора данных, добавление разбора тактики и исходное исключение Synthea из клинических правил. Сборка интерфейса прошла. Документы и исходные опыты предыдущего этапа не заменял.</p>',
      'Тесты проверяют программный контракт. Они не подтверждают достаточность обследования и безопасность лечения реального пациента.')
    section('next','Следующие шаги','Гипотеза','Следующий этап должен дать независимую оценку и данные для калибровки.',
      table(['Шаг','Критерий готовности'],[['Согласовать профили и документы','Врач подтвердил границы сценариев, редакции и исключения'],['Уточнить 17 правил','Для каждого правила записаны применимость, срок, исключения и источник; авторские проверки отделены'],['Разметить закрытую выборку','Врач размечает случаи без ответов моделей и авторского эталона; разногласия сохраняются'],['Выровнять условия сравнения','Одинаковые схема сервиса и лимит ответа для обеих моделей; отдельная серия на новых случаях'],['Калибровать генератор','Есть совместное распределение признаков взрослого терапевтического стационара, а не смесь несопоставимых процентов'],['Показать демо','Закрытый доступ или запись экрана; замечания эксперта сохранены']]),
      'Нет оснований задавать вероятности эффекта лекарств, рассчитывать штрафы или выдавать демонстрацию за клиническую систему.')
    summary='<section class="chapter"><span class="section-tag">01 / СВОДКА</span><h2>Что сделал после обратной связи</h2>'+table(['Замечание','Что сделал','Результат','Вывод'],[[r['approach'],r['action'],r['result'],r['conclusion']] for r in rows])+'</section>'
    nav='<nav class="reading-tools"><div class="toolbar"><button id="expand">Раскрыть всё</button><button id="collapse">Свернуть всё</button></div><ol>'+''.join(f'<li><a href="#{id}"><span class="nav-number">{i+2:02d}</span>{esc(title)}</a></li>' for i,(id,title,_) in enumerate(sections))+'</ol></nav>'
    css=(ROOT/'scripts/report.css').read_text()+'\nbody{overflow-wrap:anywhere}code{font-size:11px}button{cursor:pointer}@media print{.reading-tools{display:none}.reading-layout{display:block}details>*{display:block!important}}'
    js="document.getElementById('expand').onclick=()=>document.querySelectorAll('details').forEach(x=>x.open=true);document.getElementById('collapse').onclick=()=>document.querySelectorAll('details').forEach(x=>x.open=false);"
    html=f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Расширение терапевтического пилота</title><style>{css}</style></head><body><header><div class="eyebrow">ИТМО · AIMedicine · Доработка после обратной связи</div><h1>Пять направлений терапии</h1><p class="subtitle">{date}</p><p>Я расширил прототип после замечаний преподавателя: добавил заболевания и проверки, запустил Synthea, собрал дополнительные документы и подготовил демонстрацию. Ниже привёл выполненные проверки, реальные результаты моделей и то, что ещё требует согласования.</p><div class="stat-grid"><div class="stat-tile"><strong>5</strong><span>направлений</span></div><div class="stat-tile"><strong>10 / 17</strong><span>категорий / проверок</span></div><div class="stat-tile"><strong>130</strong><span>пациентов Synthea</span></div><div class="stat-tile"><strong>{main_jobs}</strong><span>заданий в основных сериях</span></div></div></header><main>{summary}<div class="reading-layout">{nav}<div class="reading-body">'+''.join(s[2] for s in sections)+f'</div></div></main><footer>AIMedicine · {date} · Расширение пилота</footer><script>{js}</script></body></html>'
    (ROOT/'reports/therapy-expansion-report.html').write_text(html)
    inputs={'title':'Расширение терапевтического пилота','context':'После обратной связи расширил пилот до пяти направлений, запустил Synthea, добавил 17 проверок и исследовал шесть документов. Результаты и ограничения приведены в local_materials.','rows':rows,'sections':[s[1] for s in sections],'preferences':'Первое лицо мужского рода. Сохранить исходный дизайн, последовательные номера и метки Факт/Интерпретация/Гипотеза. Не выдавать авторскую разметку за клинический эталон.'}
    generation=ROOT/'reports/generation';generation.mkdir(exist_ok=True)
    (generation/'therapy-expansion-input.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n')
    template=(generation/'platform-template.txt').read_text()
    substitutions={'(not provided)':inputs['context'],'(choose a precise title based on the context)':inputs['title'],'(no rows were provided: build the table skeleton and mark every empty cell with the badge "нужно уточнить")':json.dumps(rows,ensure_ascii=False,indent=2),'(no extra sections were requested: derive sensible sections from the summary rows)':'\n'.join(inputs['sections']),'(no assets were uploaded: use only the data given in this prompt)':'Материалы включены ниже.','(none)':inputs['preferences']}
    for a,b in substitutions.items():template=template.replace(a,b)
    template+='\n\n<local_materials>\n'+json.dumps({'inputs':inputs,'rationale':stats,'synthea':synthea,'models':models,'gemma_repeat':repeat,'parsing':parsing,'search':search,'tests':{'total':total,'failed':failed}},ensure_ascii=False,indent=2)+'\n</local_materials>\n'
    (generation/'therapy-expansion-prompt.txt').write_text(template)
    print('Built standalone expansion report:',len(html.encode()),'bytes')


if __name__=='__main__':main()
