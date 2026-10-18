"""Build a standalone HTML report from the reviewed source documents."""
from html import escape
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import markdown

ROOT = Path(__file__).resolve().parents[1]


def test_summary(path):
    suite = ET.parse(path).getroot()
    if suite.tag == "testsuites":
        suites = list(suite)
    else:
        suites = [suite]
    return {key: sum(int(s.attrib.get(key, 0)) for s in suites)
            for key in ("tests", "failures", "errors", "skipped")}


def main():
    checks = test_summary(ROOT / "reports/checks/pytest.xml")
    reference = test_summary(ROOT / "reports/checks/reference-mistral.xml")
    if any(s["failures"] or s["errors"] for s in (checks, reference)):
        raise ValueError("Fix failing checks before generating the report")
    smoke = json.loads((ROOT / "reports/checks/mock-smoke.json").read_text())
    if smoke.get("mode") != "mock" or smoke.get("attempts") != 0:
        raise ValueError("Expected an explicitly offline smoke result")
    live = json.loads((ROOT / "reports/checks/mistral-live.json").read_text())
    if live.get("mode") != "live" or live.get("success") is not True:
        raise ValueError("Expected a successful recorded Mistral connectivity check")
    chapters, nav = [], []
    for number, source in enumerate(sorted((ROOT / "docs").glob('*.md')), 1):
        text = source.read_text(encoding="utf-8")
        title = text.splitlines()[0].removeprefix('# ')
        chapter_id = f"chapter-{number}"
        body = markdown.markdown(text, extensions=["tables", "fenced_code"])
        body = re.sub(r'<(/?)h([1-5])>', lambda m: f'<{m[1]}h{int(m[2])+1}>', body)
        body = body.replace('<table>', '<div class="table-wrap"><table>').replace('</table>', '</table></div>')
        chapters.append(f'<section id="{chapter_id}" class="chapter"><span class="chapter-number">{number:02d}</span>{body}</section>')
        nav.append(f'<a href="#{chapter_id}">{number:02d} · {escape(title)}</a>')
    rows = [
        ("Определили первую задачу", "Полнота записи при внебольничной пневмонии у взрослых", "Объём ограничен; нужен врач-эксперт", "Подготовлено"),
        ("Изучили аналоги", "Сравнение шести решений со ссылками", "Нужны источники и отдельная проверка фактов", "Подготовлено"),
        ("Спроектировали систему и RAG", "Модули, данные, хранение и порядок поиска", "Реализация клинического процесса впереди", "Спроектировано"),
        ("Подготовили данные", "Восемь синтетических примеров и схема", "Это инженерная семья случаев без экспертной разметки", "Частично"),
        ("Подключили окружение", f"Python + Vue; {checks['tests']} локальных тестов", "Mistral-клиент проверен на имитации HTTP", "Проверено локально"),
        ("Подключили Mistral", f"{live['model']}; {live['usage']['total_tokens']} токена; {live['attempts']} запрос", "Технический JSON принят; Free активен, платный перерасход выключен", "Соединение проверено"),
        ("Проверили отборочный проект", f"{reference['tests']} теста Mistral-клиента, коммит e2f4877", "Полный набор и реальные запросы не повторялись", "Выбранный модуль"),
        ("Попробовали Google AI Studio", "Ключ не создан; повторная попытка автора проекта с телефона через VPN США также не удалась", "Причина ограничения не установлена; продолжаем на Mistral", "Подключение не завершено"),
        ("Описали первую функцию и оценку", "Входы, выходы, ошибки, критерии, план сравнения", "Клиническое качество ещё не измерено", "Подготовлено"),
    ]
    table_rows = ''.join('<tr>'+''.join(f'<td>{escape(cell)}</td>' for cell in row)+'</tr>' for row in rows)
    cases = json.loads((ROOT / "data/cases.json").read_text())
    examples = ''.join(f'<details><summary>{escape(case["id"])}</summary><pre>{escape(json.dumps(case,ensure_ascii=False,indent=2))}</pre></details>' for case in cases)
    evidence = escape(json.dumps({"new_project":checks,"reference_project":reference,"mock_smoke":smoke,"mistral_live":live},ensure_ascii=False,indent=2))
    css = '''
    :root{color:#203d38;background:#f4f5f1;font-family:system-ui,-apple-system,sans-serif;font-size:16px;line-height:1.65}*{box-sizing:border-box}body{margin:0}a{color:#146a58;text-underline-offset:3px;overflow-wrap:anywhere}header{background:#123f36;color:white;padding:52px max(24px,calc((100vw - 1120px)/2)) 44px}.eyebrow{font-size:12px;letter-spacing:2px;opacity:.7}h1{font-size:clamp(32px,5vw,54px);line-height:1.1;max-width:820px;letter-spacing:-1.5px;margin:25px 0 20px}header p{max-width:750px;color:#d8e8e0}header a{color:#d8e8e0}.meta{font-size:13px}.container{max-width:1170px;margin:auto;padding:34px 25px}h2{font-size:28px;line-height:1.25;margin:12px 0 24px;letter-spacing:-.5px}h3{font-size:20px;margin:30px 0 14px}p{margin:12px 0 18px}section{scroll-margin-top:24px}.chapter{padding:40px 0;border-top:1px solid #cddbd2}.chapter-number{font-size:12px;letter-spacing:2px;color:#598271}nav{display:grid;grid-template-columns:1fr 1fr;gap:9px 25px;background:#e8eee6;border-radius:12px;padding:24px;margin:28px 0}nav a{text-decoration:none;font-size:14px}.table-wrap{overflow-x:auto;margin:20px 0 26px}table{width:100%;border-collapse:collapse;font-size:14px;text-align:left}th{background:#dfebe3;padding:14px;vertical-align:top}td{padding:14px;vertical-align:top;border-bottom:1px solid #d6dfd7;min-width:150px}tbody tr:nth-child(even){background:#eef2eb}code{font-size:.9em;background:#e5ede7;padding:2px 4px;border-radius:3px;overflow-wrap:anywhere}pre{background:#e7eee8;padding:20px;white-space:pre-wrap;overflow-wrap:anywhere;border-radius:10px;font-size:13px;line-height:1.6}pre code{padding:0;background:none}li{margin:6px 0}.note{border-left:4px solid #b58b34;background:#fff6dc;padding:17px 20px;margin:20px 0 28px}.flow{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:25px 0}.flow div{border:1px solid #c3d8cc;background:white;border-radius:10px;padding:18px}.flow small{display:block;color:#5c786c;margin-bottom:7px}details{border:1px solid #d4dfd5;border-radius:10px;padding:12px 18px;margin:10px 0}summary{cursor:pointer;font-weight:600}footer{border-top:1px solid #cddbd2;padding:24px 0 40px;font-size:13px;color:#597568}@media(max-width:700px){.container{padding:22px 18px}header{padding:36px 20px}nav,.flow{grid-template-columns:1fr}h2{font-size:25px}td{min-width:200px}}@media print{header{background:white;color:#163e32;padding:0}header p,header a{color:#163e32}.container{max-width:none;padding:0}body{background:white;font-size:11pt}nav{display:none}h1{font-size:28pt}.table-wrap{overflow:visible}td{min-width:0;padding:7px}th{padding:7px}.chapter{break-before:page}tr,pre{break-inside:avoid}}
    '''
    html = f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ITMO AIMedicine · Отчёт первого этапа</title><style>{css}</style></head>
<body><header><div class="eyebrow">ИТМО · PERFORMANCE ENGINEERING · ЭТАП 01</div><h1>Проверка медицинской документации</h1><p>Исследование, архитектура и подготовка окружения. Начинаем с Mistral; проверку Gemini и Gemma переносим до решения проблемы доступа.</p><div class="meta">18 октября 2026 · Учебный проект · <a href="https://github.com/VAVASTO/ITMO_AIMedicine">ITMO_AIMedicine</a></div></header>
<main class="container"><h2>Что сделано на первом этапе</h2><div class="table-wrap"><table><thead><tr><th>Что делали</th><th>Результат</th><th>Вывод</th><th>Статус</th></tr></thead><tbody>{table_rows}</tbody></table></div>
<div class="note"><strong>Границы результата.</strong> Доступ к Mistral подтверждён одним техническим запросом без медицинских данных. Клиническая функция описана, но ещё не реализована; качество медицинских ответов не оценивалось. Gemini и Gemma пока не подключены.</div>
<nav aria-label="Содержание">{''.join(nav)}<a href="#appendix">09 · Примеры и подтверждения</a></nav>
<div class="flow" aria-label="План клинической проверки"><div><small>01 · ВХОД</small>Запись и время доступности фактов</div><div><small>02 · ОСНОВАНИЯ</small>Поиск по зафиксированной версии документа</div><div><small>03 · РЕЗУЛЬТАТ</small>Замечания со ссылками и решение врача</div></div>
{''.join(chapters)}
<section class="chapter" id="appendix"><span class="chapter-number">09</span><h2>Примеры и подтверждения</h2><p>Встроенные данные позволяют читать отчёт без доступа к репозиторию. Раскройте пример, чтобы увидеть вход будущей функции. Ожидаемые метки хранятся отдельно и модели не передаются.</p>{examples}<h3>Машинный итог проверок</h3><pre>{evidence}</pre><p>Все внешние источники приведены рядом с соответствующими утверждениями. Исторические результаты отборочного проекта не включены в число новых проверок модели.</p></section>
<footer>Отчёт подготовлен для первого этапа практики. Выполненные проверки, планы и нерешённые вопросы указаны отдельно. Документ не содержит реальных медицинских карт и ключей API.</footer></main></body></html>'''
    output = ROOT / "reports/stage1.html"
    output.write_text(html, encoding="utf-8")
    print(f"Built {output.relative_to(ROOT)} ({len(html.encode())} bytes)")


if __name__ == "__main__":
    main()
