const group = document.getElementById('group-filter');
group.addEventListener('change', () => {
  let count = 0;
  for (const row of document.querySelectorAll('#competitor-table tbody tr')) {
    row.hidden = group.value !== 'all' && row.dataset.group !== group.value;
    if (!row.hidden) count++;
  }
  document.getElementById('filter-count').textContent = 'Показано: ' + count;
});

const summaryTable = document.getElementById('summary-table');
const summaryRows = [...summaryTable.tBodies[0].rows];
for (const button of document.querySelectorAll('[data-status-filter]')) {
  button.addEventListener('click', () => {
    for (const other of document.querySelectorAll('[data-status-filter]')) {
      other.setAttribute('aria-pressed', String(other === button));
    }
    for (const row of summaryRows) {
      row.hidden = button.dataset.statusFilter !== 'all' && row.dataset.status !== button.dataset.statusFilter;
    }
    document.getElementById('summary-count').textContent =
      `Показано: ${summaryRows.filter(row => !row.hidden).length} из ${summaryRows.length}`;
  });
}
for (const button of summaryTable.querySelectorAll('[data-sort]')) {
  button.addEventListener('click', () => {
    const th = button.closest('th');
    const direction = th.getAttribute('aria-sort') === 'ascending' ? 'descending' : 'ascending';
    for (const header of summaryTable.querySelectorAll('th')) header.setAttribute('aria-sort', 'none');
    th.setAttribute('aria-sort', direction);
    const column = Number(button.dataset.sort);
    const rows = [...summaryTable.tBodies[0].rows];
    const rank = {worked:0, partial:1, failed:2};
    rows.sort((a,b) => {
      const result = column === 4 ? rank[a.dataset.status] - rank[b.dataset.status] :
        a.cells[column].textContent.localeCompare(b.cells[column].textContent,'ru',{numeric:true});
      return direction === 'ascending' ? result : -result;
    });
    summaryTable.tBodies[0].append(...rows);
  });
}

document.getElementById('expand-all').addEventListener('click', () => {
  document.querySelectorAll('details').forEach(detail => { detail.open = true; });
});
document.getElementById('collapse-all').addEventListener('click', () => {
  document.querySelectorAll('details').forEach(detail => { detail.open = false; });
});
function revealTarget(hash) {
  let id;
  try { id = decodeURIComponent(hash.slice(1)); } catch { return; }
  const target = document.getElementById(id);
  if (!target) return;
  const child = target.querySelector(':scope > details');
  if (child) child.open = true;
  let current = target;
  while (current) {
    if (current.tagName === 'DETAILS') current.open = true;
    current = current.parentElement;
  }
  target.scrollIntoView({block:'start'});
}
document.querySelectorAll('a[href^="#"]').forEach(link => link.addEventListener('click', () => {
  revealTarget(link.getAttribute('href'));
}));
window.addEventListener('hashchange', () => revealTarget(location.hash));
if (location.hash) revealTarget(location.hash);

document.getElementById('case-state').addEventListener('change', event => {
  for (const panel of document.querySelectorAll('[data-case-state]')) {
    panel.hidden = panel.dataset.caseState !== event.target.value;
  }
});

const dialog = document.getElementById('diagram-dialog');
let zoomTrigger = null;
document.querySelectorAll('.diagram svg').forEach(svg => {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'zoom-button';
  button.textContent = 'Увеличить схему';
  button.setAttribute('aria-label', 'Увеличить: ' + (svg.getAttribute('aria-label') || 'схема'));
  button.addEventListener('click', () => {
    zoomTrigger = button;
    document.getElementById('zoom-title').textContent = svg.getAttribute('aria-label') || 'Схема';
    document.getElementById('zoom-content').replaceChildren(svg.cloneNode(true));
    dialog.showModal();
  });
  svg.closest('.diagram').after(button);
});
document.getElementById('close-diagram').addEventListener('click', () => dialog.close());
dialog.addEventListener('close', () => { if (zoomTrigger) zoomTrigger.focus(); });

let printState = null;
window.addEventListener('beforeprint', () => {
  if (printState) return;
  printState = [...document.querySelectorAll('details')].map(detail => [detail, detail.open]);
  for (const [detail] of printState) detail.open = true;
});
window.addEventListener('afterprint', () => {
  if (printState) for (const [detail, open] of printState) detail.open = open;
  printState = null;
});
document.getElementById('print-report').addEventListener('click', () => {
  try { window.print(); } catch {
    document.getElementById('print-help').textContent = 'Скачайте HTML и откройте отдельно для печати.';
  }
});

// The same renderers accept fetched assets and embedded snapshots for offline use.
function dataTable(headers, rows, caption) {
  const wrap = document.createElement('div');
  wrap.className = 'table-wrap';
  const table = document.createElement('table');
  const title = document.createElement('caption');
  title.textContent = caption;
  table.append(title);
  const head = table.createTHead().insertRow();
  for (const label of headers) {
    const th = document.createElement('th'); th.scope = 'col'; th.textContent = label; head.append(th);
  }
  const body = table.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    for (const value of row) tr.insertCell().textContent = value ?? 'нужно уточнить';
  }
  wrap.append(table);
  return wrap;
}
function renderAsset(path, data, panel) {
  let headers, rows, caption;
  if (path.endsWith('research-evidence.json')) {
    headers = ['Проверка', 'Дата', 'Тесты', 'Ошибки', 'Падения'];
    const checks = [['Исходный проект','18.10.2026',data.original_tests_2026_10_18],
      ['Клиент отборочного проекта','18.10.2026',data.reference_tests_2026_10_18],
      ['Предыдущая доработка','25.10.2026',data.revision_tests],
      ['После усиления отчёта','25.10.2026',data.strengthening_tests],
      ['После подключения GLM','25.10.2026',data.glm_tests],
      ['После сравнительного эксперимента','25.10.2026',data.comparison_tests]];
    rows = checks.map(([label,date,r]) => [label,date,r.tests,r.errors,r.failures]);
    caption = 'Факт · сохранённые технические проверки';
    const bars = [...document.querySelectorAll('#strata-chart .chart-bar')];
    data.sampling_plan.strata.forEach((stratum, index) => {
      const bar = bars[index];
      if (!bar) return;
      const value = stratum.discharged_thousand_2024;
      const width = value / 5000 * 510;
      const description = `${stratum.label}: ${value.toLocaleString('ru-RU')} тыс. человек`;
      bar.setAttribute('aria-label', description);
      bar.querySelector('title').textContent = description;
      bar.querySelector('rect').setAttribute('width', String(width));
      const text = bar.querySelector('.chart-value');
      text.setAttribute('x', String(295 + width)); text.textContent = value.toLocaleString('ru-RU');
    });
  } else if (path.endsWith('review-examples.json')) {
    headers = ['Заготовка', 'Возраст', 'Диагноз в примере', 'Вопрос эксперту'];
    rows = data.cases.map(c => [c.id,c.age,c.diagnosis.text,data.questions[c.id]]);
    caption = 'Факт · 12 подготовленных вымышленных заготовок; клинической разметки нет';
  } else if (path.endsWith('feature-walkthrough.json')) {
    headers = ['Момент проверки', 'Доступные документы', 'Ожидаемое действие'];
    rows = data.states.map(s => [s.review_at,s.available_documents.join(', '),s.message]);
    caption = 'Интерпретация · два заранее описанных состояния, не ответы модели';
  } else {
    headers = ['Вариант', 'Критерий', 'Ситуация', 'Ожидаемое действие'];
    rows = data.expectations.map(e => [e.case_id,e.criterion_id,e.scenario,e.reason]);
    caption = 'Интерпретация · 14 вариантов одной семьи, авторские ожидания';
  }
  panel.querySelector('.asset-view').replaceChildren(dataTable(headers,rows,caption));
}
async function loadAssets() {
  let snapshots;
  try { snapshots = JSON.parse(document.getElementById('asset-snapshots').textContent); }
  catch { return; }
  await Promise.all([...document.querySelectorAll('[data-asset]')].map(async panel => {
    const path = panel.dataset.asset;
    const state = panel.querySelector('.asset-state');
    try { renderAsset(path,snapshots[path],panel); }
    catch { state.textContent = 'Не удалось прочитать сохранённую копию. Основные материалы приведены в отчёте.'; }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const response = await fetch(path,{signal:controller.signal,credentials:'omit'});
      if (!response.ok) throw new Error('Asset unavailable');
      const data = await response.json();
      // Report facts and fixed tables must never silently drift from this revision.
      if (JSON.stringify(data) !== JSON.stringify(snapshots[path])) {
        state.textContent = `Файл ${path} изменился после сборки. Показана сохранённая версия отчёта; для обновления нужна повторная сборка.`;
        panel.dataset.load = 'changed'; return;
      }
      renderAsset(path,data,panel);
      state.textContent = `Источник: ${path}. Файл загружен; данные совпадают с сохранённой версией отчёта.`;
      panel.dataset.load = 'fetched';
    } catch {
      state.textContent = `Не удалось загрузить ${path}. Показана сохранённая копия. При открытии HTML с диска браузер может блокировать загрузку соседних файлов.`;
      panel.dataset.load = 'fallback';
    } finally { clearTimeout(timeout); }
  }));
}
loadAssets();

const chart = document.getElementById('strata-chart');
chart.querySelector('.chart-legend').addEventListener('click', event => {
  const button = event.currentTarget;
  const show = button.getAttribute('aria-pressed') !== 'true';
  button.setAttribute('aria-pressed', String(show));
  chart.querySelector('[data-series]').hidden = !show;
  chart.querySelector('.chart-note').textContent = show ? 'Показаны все 6 классов.' : 'Ряд скрыт. Нажмите на легенду, чтобы вернуть значения.';
});
for (const bar of chart.querySelectorAll('.chart-bar')) {
  const explain = () => { chart.querySelector('.chart-note').textContent = bar.getAttribute('aria-label'); };
  bar.addEventListener('pointerenter',explain); bar.addEventListener('focus',explain);
}
for (const step of document.querySelectorAll('.flow-step')) {
  const explain = () => { step.closest('figure').querySelector('.diagram-explanation').textContent = step.dataset.explanation; };
  step.addEventListener('pointerenter',explain); step.addEventListener('focus',explain);
}

// No storage or parent-frame access: navigation works inside a sandbox.
const navigation = [...document.querySelectorAll('#contents a')];
const navigationTargets = navigation.map(link => document.getElementById(link.hash.slice(1))).filter(Boolean);
let scrollPending = false;
function updateNavigation() {
  scrollPending = false;
  const top = window.innerWidth <= 900 ? 200 : 80;
  let current = navigationTargets[0];
  for (const target of navigationTargets) if (target.getBoundingClientRect().top <= top) current = target;
  for (const link of navigation) {
    if (link.hash === '#' + current.id) link.setAttribute('aria-current','location');
    else link.removeAttribute('aria-current');
  }
}
window.addEventListener('scroll',() => {
  if (!scrollPending) { scrollPending = true; requestAnimationFrame(updateNavigation); }
},{passive:true});
updateNavigation();

// Small JSON tokenizer; textContent keeps source strings from becoming markup.
for (const pre of document.querySelectorAll('pre')) {
  const code = pre.querySelector('code');
  const raw = code.textContent;
  const parts = raw.split(/("(?:\\.|[^"\\])*"\s*:|"(?:\\.|[^"\\])*"|\b(?:true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g);
  code.replaceChildren();
  for (const part of parts) {
    const span = document.createElement('span'); span.textContent = part;
    span.className = /^".*:\s*$/.test(part) ? 'token-key' : /^"/.test(part) ? 'token-string' : /^(true|false|null)$/.test(part) ? 'token-literal' : /^-?\d/.test(part) ? 'token-number' : '';
    code.append(span);
  }
  const button = document.createElement('button'); button.type = 'button'; button.className = 'copy-button'; button.textContent = 'Копировать код';
  const status = document.createElement('p'); status.className = 'copy-status'; status.setAttribute('role','status');
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(raw);
      status.textContent = 'Код скопирован.';
    } catch {
      try {
        const range = document.createRange(); range.selectNodeContents(code);
        const selection = window.getSelection(); selection.removeAllRanges(); selection.addRange(range);
        status.textContent = 'Копирование недоступно в этом окне. Код выделен; скопируйте его сочетанием Ctrl+C или ⌘C.';
      } catch { status.textContent = 'Копирование недоступно в этом окне. Откройте HTML отдельно или выделите код вручную.'; }
    }
  });
  pre.prepend(button); pre.after(status);
}
