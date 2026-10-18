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
        chapters.append(f'<section id="{chapter_id}" class="chapter">{body}</section>')
        nav.append(f'<li><a href="#{chapter_id}">{escape(title)}</a></li>')
    rows = [
        ("Выбрал первую задачу", "Полнота записи при внебольничной пневмонии у взрослых", "Объём ограничен; нужен врач-эксперт", "Подготовлено"),
        ("Изучил аналоги", "Сравнение шести решений со ссылками", "Нужны источники и отдельная проверка фактов", "Подготовлено"),
        ("Спроектировал систему и RAG", "Модули, данные, хранение и порядок поиска", "Клинический процесс ещё предстоит реализовать", "Спроектировано"),
        ("Подготовил данные", "Восемь синтетических примеров и схема", "Варианты одной базовой истории, без экспертной разметки", "Частично"),
        ("Настроил окружение", f"Python + Vue; {checks['tests']} локальных тестов", "Mistral-клиент проверен на имитации HTTP", "Проверено локально"),
        ("Подключил Mistral", f"{live['model']}; {live['usage']['total_tokens']} токена; {live['attempts']} запрос", "Технический JSON принят; Free активен, платный перерасход выключен", "Соединение проверено"),
        ("Проверил отборочный проект", f"{reference['tests']} теста Mistral-клиента, коммит e2f4877", "Полный набор и реальные запросы не повторялись", "Выбранный модуль"),
        ("Попробовал Google AI Studio", "Ключ не создан, в том числе с телефона через VPN США", "Причину ограничения пока не установил; продолжаю на Mistral", "Подключение не завершено"),
        ("Описал первую функцию и оценку", "Входы, выходы, ошибки, критерии, план сравнения", "Клиническое качество ещё не измерено", "Подготовлено"),
    ]
    table_rows = ''.join('<tr>'+''.join(f'<td>{escape(cell)}</td>' for cell in row)+'</tr>' for row in rows)
    cases = json.loads((ROOT / "data/cases.json").read_text())
    examples = ''.join(f'<details><summary>{escape(case["id"])}</summary><pre>{escape(json.dumps(case,ensure_ascii=False,indent=2))}</pre></details>' for case in cases)
    evidence = escape(json.dumps({"new_project":checks,"reference_project":reference,"mock_smoke":smoke,"mistral_live":live},ensure_ascii=False,indent=2))
    css = """
    * { box-sizing: border-box; }
    html { color: #222; background: #fff; font: 16px/1.6 Arial, sans-serif; }
    body { max-width: 1080px; margin: 0 auto; padding: 40px 32px 64px; }
    header { margin-bottom: 32px; padding-bottom: 20px; border-bottom: 1px solid #bbb; }
    h1 { margin: 0 0 12px; font-size: 28px; line-height: 1.3; }
    h2 { margin: 0 0 20px; font-size: 23px; line-height: 1.35; }
    h3 { margin: 28px 0 12px; font-size: 18px; line-height: 1.4; }
    p { margin: 12px 0 16px; }
    a { color: inherit; text-underline-offset: 3px; overflow-wrap: anywhere; }
    a:hover { text-decoration-thickness: 2px; }
    a:focus-visible, summary:focus-visible { outline: 2px solid #333; outline-offset: 3px; }
    .meta { color: #555; font-size: 14px; }
    .subtitle { margin: 0 0 12px; font-size: 18px; }
    nav { margin: 36px 0; }
    nav ol { padding-left: 24px; }
    nav li { margin: 4px 0; }
    .chapter { padding: 32px 0; border-top: 1px solid #ccc; scroll-margin-top: 24px; }
    .table-wrap { overflow-x: auto; margin: 20px 0 24px; }
    table { width: 100%; border-collapse: collapse; text-align: left; font-size: 14px; }
    th, td { padding: 10px 12px; vertical-align: top; border: 1px solid #ccc; }
    th { background: #f2f2f2; font-weight: 600; }
    code { font-size: .9em; overflow-wrap: anywhere; }
    pre { padding: 16px; border: 1px solid #ddd; background: #f7f7f7;
          white-space: pre-wrap; overflow-wrap: anywhere; font-size: 13px; line-height: 1.6; }
    pre code { font-size: inherit; }
    li { margin: 6px 0; }
    details { margin: 12px 0; }
    summary { cursor: pointer; padding: 8px 0; }
    @media (max-width: 700px) {
        body { padding: 24px 18px 40px; }
        h1 { font-size: 25px; }
        h2 { font-size: 21px; }
        th, td { min-width: 160px; }
    }
    @media print {
        html { font-size: 11pt; }
        body { max-width: none; padding: 0; }
        nav { display: none; }
        h1 { font-size: 22pt; }
        h2 { break-after: avoid; }
        .chapter { padding: 20px 0; }
        .table-wrap { overflow: visible; }
        th, td { min-width: 0; padding: 6px; }
        tr, pre { break-inside: avoid; }
    }
    """
    html = f'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Отчёт за первую неделю</title>
<style>{css}</style>
</head>
<body>
<header>
<h1>Отчёт за первую неделю</h1>
<p class="subtitle">Проект «Проверка медицинской документации»</p>
<p class="meta">18 октября 2026 года<br>
Репозиторий: <a href="https://github.com/VAVASTO/ITMO_AIMedicine">VAVASTO/ITMO_AIMedicine</a></p>
</header>
<main>
<h2>Что сделано</h2>
<div class="table-wrap"><table>
<thead><tr><th>Задача</th><th>Результат</th><th>Вывод</th><th>Статус</th></tr></thead>
<tbody>{table_rows}</tbody>
</table></div>
<nav aria-label="Содержание">
<h2>Содержание</h2>
<ol>{''.join(nav)}<li><a href="#appendix">Примеры и результаты тестов</a></li></ol>
</nav>
{''.join(chapters)}
<section class="chapter" id="appendix">
<h2>Примеры и результаты тестов</h2>
<p>Восемь синтетических записей для проверки будущей функции. Ожидаемые метки хранятся отдельно и модели не передаются.</p>
{examples}
<details><summary>Результаты тестов в JSON</summary><pre>{evidence}</pre></details>
</section>
</main>
</body>
</html>'''
    output = ROOT / "reports/Отчёт_за_первую_неделю.html"
    output.write_text(html, encoding="utf-8")
    print(f"Built {output.relative_to(ROOT)} ({len(html.encode())} bytes)")


if __name__ == "__main__":
    main()
