"""Presentation rules from the unmodified platform prompt."""
from html import escape
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FACT = 'Факт'
INTERPRETATION = 'Интерпретация'
HYPOTHESIS = 'Гипотеза'


def badge(kind):
    return f'<span class="claim-kind">{kind}</span>'


def label_prose(body, name):
    """Label evidence and proposals by their authored context, never by colour."""
    default = FACT if name in ('02-research', '03-data', '07-models', '08-validation', '10-next-steps') else INTERPRETATION
    headings = {
        'Как я изучал процесс': FACT, 'Три роли и передача результата': INTERPRETATION,
        'Контроль ОМС: что именно проверяют': FACT, 'Почему задача сложна': INTERPRETATION,
        'Как проверить пользу': INTERPRETATION, 'Что следует из сравнения': INTERPRETATION,
        'Статистическая основа': FACT, 'Подготовленные примеры': FACT,
        'Как получить реалистичную симуляцию': INTERPRETATION, 'Условия приёмки данных': INTERPRETATION,
        'Проверка версии и полноты корпуса': INTERPRETATION,
        'Реализация и проект': FACT, 'Что произошло с Google': FACT,
        'Что перенесено из примера': FACT, 'Выбор модели и распределение работы': INTERPRETATION,
        'Документация API': FACT, 'Порядок перехода на Gemini': INTERPRETATION,
        'Что осталось': INTERPRETATION, 'Что показывают опубликованные результаты': FACT,
    }
    chunks = re.split(r'(<h3>.*?</h3>)', body, flags=re.S)
    kind = default
    title = re.search(r'<h2>(.*?)</h2>', body).group(1)
    result = []
    for chunk in chunks:
        match = re.fullmatch(r'<h3>(.*?)</h3>', chunk, re.S)
        if match:
            title = match[1]
            kind = headings.get(title, default)
            result.append(chunk)
            continue
        def mark_paragraph(m):
            text = m[1]
            label = HYPOTHESIS if '<strong>Гипотеза:</strong>' in text or 'Проверяемая исследовательская гипотеза' in text else kind
            if '<strong>Вывод для проекта.</strong>' in text or 'я бы проверял' in text:
                label = INTERPRETATION
            if text.startswith(('Содержательных запросов', 'В Subscription активен', 'Ключ я создал')):
                label = FACT
            if text.startswith('<strong>Гипотеза:</strong> '):
                text = text.removeprefix('<strong>Гипотеза:</strong> ')
                text = text[:1].upper() + text[1:]
            return '<p>'+badge(label)+' '+text+'</p>'
        chunk = re.sub(r'<p>(.*?)</p>', mark_paragraph, chunk, flags=re.S)
        chunk = chunk.replace('<table>', '<table><caption>'+badge(kind)+' '+title+'</caption>')
        chunk = re.sub(r'(<[ou]l>)', badge(kind)+r'\1', chunk)
        result.append(chunk)
    return ''.join(result)


LIMITATIONS = {
    'chapter-1': 'Интервью не проводил. Процесс и базовое время проверки нужно подтвердить в конкретной организации.',
    'chapter-2': 'Продукты изучены по открытым материалам. На одинаковых картах я их не испытывал; сопоставимой оценки точности нет.',
    'chapter-3': 'Полный корпус не собран. Версии на дату случая, региональные правила и локальные документы ещё нужно проверить.',
    'chapter-4': '12 семей не образуют репрезентативную выборку. Все 14 новых вариантов относятся к одной из этих семей; клинической разметки нет.',
    'chapter-5': 'Клинические и экспертные модули пока спроектированы. Работает техническая основа, а не весь описанный процесс.',
    'chapter-6': 'Функция ещё не реализована. Актуальность КР 654_2 версии 2024 на дату учебного случая не подтверждена.',
    'chapter-7': 'Сравнение охватило 12 коротких авторских историй без независимой клинической разметки. Клинические пороги и размер закрытой выборки нужно согласовать.',
    'chapter-8': 'Выбор GLM предварительный: один запуск на случай, 12 историй, разный контроль схемы у провайдеров. Клиническое качество и доступность Gemini не подтверждены.',
    'chapter-9': '69 локальных тестов и 36 новых ответов проверяют авторскую спецификацию. Улучшение точности GLM от фильтра времени не показано; полного C07 ещё нет.',
    'chapter-10': 'Подготовленные материалы не заменяют реализацию и независимую оценку. Окончательную оценку этапа даёт руководитель.',
    'examples': 'Заготовки вымышленные и содержат только часть документов. Клиническую достаточность, госпитализацию и кодирование должен проверить специалист.',
    'sources': 'Публикация или описание поставщика не подтверждают эффективность моего проекта. Нормативную версию нужно сопоставить с датой случая.',
    'checks': 'У каждого результата сохранена дата запуска. Первая проба относится к одной семье, новое сравнение к 12 авторским историям. Независимой клинической оценки нет.',
    'failed': 'Причины перечислены по имеющимся наблюдениям. Точная причина ограничений Google не установлена.',
    'next': 'Это мой план второй недели. Доступ к экспертам, бесплатная квота и результаты первых запусков могут повлиять на сроки.',
}
EXTRA_TAKEAWAYS = {
    'examples': 'Подготовленные заготовки позволяют обсуждать входные документы и ожидания; клинические выводы ещё нужно согласовать.',
    'sources': 'Собрал 28 источников с местами подтверждения и ограничениями; применимость нормативных версий проверяется отдельно.',
    'checks': 'Сохранённые журналы подтверждают технические проверки и подготовку данных, но не клиническое качество.',
    'failed': 'После первой пробы добавил экспериментальный отбор документов и сравнение моделей. Доступ к Google и клиническая оценка остаются нерешёнными задачами.',
    'next': 'На второй неделе планирую реализовать первый проход проверки и сравнить варианты на одном наборе.',
}


def asset_panel(path, title):
    return (f'<details class="asset-panel" data-asset="{path}"><summary>{title}</summary>'
            f'<p class="asset-state caption" role="status">Источник: <a href="{path}">{path}</a>. Данные доступны в сохранённой копии отчёта.</p>'
            '<div class="asset-view"></div></details>')


def decorate_report(html, inputs, evidence, cases, seeds):
    fonts = '<link href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:wght@400;600;700&amp;family=Instrument+Sans:wght@400;500;600;700&amp;family=JetBrains+Mono:wght@400;500&amp;display=swap" rel="stylesheet">'
    html = html.replace('<style>', fonts+'<style>', 1)
    html = html.replace('<header id="top">', '<header id="top"><p class="eyebrow">Исследовательская практика · Неделя 1</p>', 1)
    tiles = ''.join(f'<div class="stat-tile"><strong>{number}</strong><span>{label}</span></div>' for number,label in [
        ('28','источников'),('12','подходов и продуктов'),('12','исходных семей'),(str(evidence['comparison_tests']['tests']),'локальных тестов')])
    html = html.replace('</header>', f'<div class="stat-grid" aria-label="Итоги подготовки">{tiles}</div></header>', 1)
    html = html.replace('<p class="takeaway"><strong>Вывод:</strong>', '<p class="takeaway">'+badge(INTERPRETATION)+' <strong>Вывод:</strong>')
    html = html.replace('<section id="summary"><h2>', '<section class="card" id="summary"><span class="section-tag">01 · Итоги недели</span><h2>')
    html = html.replace('<p><strong>Решение:</strong>', '<p class="takeaway">'+badge(INTERPRETATION)+' <strong>Решение:</strong>')
    # Keep the summary cells and all supplied numbers unchanged.
    html = html.replace('<div class="summary-filters"', '<p class="claim-note">'+badge(FACT)+' Выполненные действия и сохранённые результаты; выводы в таблице отражают мою интерпретацию.</p><div class="summary-filters"', 1)
    order = [f'chapter-{i}' for i in range(1,11)] + ['examples','sources','checks','failed','next']
    for number, sid in enumerate(order, 2):
        pattern = rf'(<section class="chapter" id="{sid}"><details class="chapter-body" open><summary>)(.*?)(</summary>)(.*?)(</details></section>)'
        def decorate_section(m):
            content = m[4]
            if sid in EXTRA_TAKEAWAYS:
                content = '<p class="takeaway">'+badge(INTERPRETATION)+' <strong>Вывод:</strong> '+EXTRA_TAKEAWAYS[sid]+'</p>'+content
                # Labels apply to authored factual paragraphs, not the technical JSON block.
                category = INTERPRETATION if sid == 'next' else FACT
                content = re.sub(r'<p>(.*?)</p>', lambda p:'<p>'+badge(INTERPRETATION if '<strong>Вопрос эксперту:</strong>' in p[1] else category)+' '+p[1]+'</p>', content, flags=re.S)
            missing = '<span class="missing">нужно уточнить</span> ' if sid not in ('chapter-9','checks') else ''
            limitation = '<aside class="limitations"><h3>Ограничения</h3><p>'+badge(FACT)+' '+missing+LIMITATIONS[sid]+'</p></aside>'
            return m[1]+f'<span class="section-tag">{number:02d} · Раздел</span>'+m[2]+m[3]+content+limitation+m[5]
        html, count = re.subn(pattern, decorate_section, html, count=1, flags=re.S)
        if count != 1:
            raise ValueError(f'Section not found: {sid}')
        html = html.replace(f'<a href="#{sid}">', f'<a href="#{sid}"><span class="nav-number">{number:02d}</span> ', 1)
    html = html.replace('<ol><li>', '<ol><li><a href="#summary"><span class="nav-number">01</span> Итоги недели</a></li><li>', 1)
    html = html.replace('<div class="toolbar"', '<div class="reading-layout"><div class="reading-tools"><div class="toolbar"', 1)
    html = html.replace('</nav>', '</nav></div><div class="reading-body">', 1)
    html = html.replace('</main>', '</div></div></main>', 1)
    # Give every table a useful caption, including tables created from source data.
    nearest_heading = 'Материалы отчёта'
    def captions(m):
        nonlocal nearest_heading
        if m[0].startswith('<h'):
            nearest_heading = re.sub('<[^>]+>', '', m[0])
            return m[0]
        opening, rest = m[1], m[2]
        if rest.lstrip().startswith('<caption>'):
            return m[0]
        return opening+'<caption>'+escape(nearest_heading)+'</caption>'+rest+'</table>'
    html = re.sub(r'<h[234]>.*?</h[234]>|(<table\b[^>]*>)(.*?)</table>', captions, html, flags=re.S)
    html = html.replace('<pre>', '<pre><code class="language-json">').replace('</pre>', '</code></pre>')
    # Source panels make each of the four listed JSON files useful in its own section.
    panels = {
        'examples': asset_panel('assets/review-examples.json', 'Таблица заготовок из исходного файла'),
        'checks': asset_panel('assets/research-evidence.json', 'Технические результаты из исходного файла'),
    }
    for sid, panel in panels.items():
        pattern = rf'(<section class="chapter" id="{sid}">.*?</p>)'
        html = re.sub(pattern, lambda m:m[0]+panel, html, count=1, flags=re.S)
    html = html.replace('<div class="case-demo"', asset_panel('assets/feature-walkthrough.json', 'Ожидаемые состояния из исходного файла')+'<div class="case-demo"', 1)
    html = html.replace('<h4>Покрытие ситуаций первой функции</h4>', '<h4>Покрытие ситуаций первой функции</h4>'+asset_panel('assets/feature-packet.json', 'Критерии и ожидания из исходного файла'), 1)
    if 'data-asset="assets/feature-packet.json"' not in html:
        raise ValueError('Missing feature packet panel')
    iceberg = ('<figure class="iceberg"><figcaption>Результат и работа за ним</figcaption>'
               '<div class="iceberg-visible">'+badge(FACT)+'<h4>В отчёте</h4><p>Обзор 12 подходов, 28 источников, спецификация первой функции, 69 локальных тестов и сравнение GLM с Mistral на 12 новых историях.</p></div>'
               '<div class="waterline">Подготовка и неудачные попытки</div>'
               '<div class="iceberg-hidden">'+badge(FACT)+'<ul><li>Расширил первоначальные 8 инженерных примеров до исследования процессов и набора из 12 семей.</li>'
               '<li>Отделил 14 дополнительных вариантов одной семьи от независимой выборки.</li>'
               '<li>Убрал неподтверждённые клинические пороги из условий приёмки.</li>'
               '<li>При чтении ответов GLM нашёл сведения из будущего документа, которые пропустили автоматические проверки.</li>'
               '<li>Проверил доступ к Google, в том числе с VPN; создать ключ не удалось.</li></ul></div></figure>')
    html = re.sub(r'(<section class="chapter" id="failed">.*?)(<aside class="limitations">)', lambda m:m[1]+iceberg+m[2], html, count=1, flags=re.S)
    html = re.sub(r'<a href="([^"]+\.pdf(?:\?[^"]*)?)">', r'<a href="\1" target="_blank" rel="noopener">', html, flags=re.I)
    snapshots = {
        'assets/research-evidence.json': evidence,
        'assets/review-examples.json': {'purpose':'synthetic examples for expert review; not clinical ground truth','cases':cases,'questions':{k:v['expert_question'] for k,v in seeds.items()}},
        'assets/feature-walkthrough.json': json.loads((ROOT/'reports/assets/feature-walkthrough.json').read_text()),
        'assets/feature-packet.json': json.loads((ROOT/'reports/assets/feature-packet.json').read_text()),
    }
    data = json.dumps(snapshots, ensure_ascii=False).replace('<', '\\u003c')
    html = html.replace('<script>', '<script id="asset-snapshots" type="application/json">'+data+'</script><script>', 1)
    return html
