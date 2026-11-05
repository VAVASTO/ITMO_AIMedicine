(() => {
  'use strict';
  const data=JSON.parse(document.getElementById('evidence').textContent);
  const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const names={met:'Подтверждено',attention:'Нужен разбор',pending:'Срок ещё идёт',unknown:'Недостаточно данных',not_applicable:'Не применяется'};
  const actions={measure_spo2:'Уточнить измерение SpO2',review_antibiotic_order:'Проверить назначение антибиотика',clarify_treatment_start:'Уточнить начало терапии',schedule_reassessment:'Запланировать оценку ответа',assess_response:'Оценить ответ на лечение',review_treatment:'Пересмотреть тактику с врачом',clarify_record:'Уточнить запись',specialist_review:'Разобрать исключение с врачом'};
  const kinds={diagnosis:'Диагноз',spo2:'SpO2',antibiotic_order:'Назначение',antibiotic_start:'Начало терапии',reassessment:'Оценка ответа',treatment_review:'Пересмотр тактики',exception:'Исключение',observation:'Наблюдение'};
  const values={confirmed_cap:'Подтверждена ВП',suspected_cap:'Подозрение на ВП',improving:'Улучшение',worsening:'Ухудшение',unchanged:'Без изменений',documented:'Подтверждено записью','requires review':'Требуется разбор исключения'};
  const format=t=>new Date(t).toLocaleString('ru-RU',{timeZone:'Europe/Moscow',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
  const tbody=document.querySelector('#summary-table tbody');
  const original=[...tbody.rows]; let selectedStatus='all';
  function filterSort(){
    const order=document.getElementById('summary-sort').value;
    const indices=data.rows.map((_,i)=>i);
    if(order!=='original') indices.sort((a,b)=>data.rows[a][order].localeCompare(data.rows[b][order],'ru'));
    indices.forEach(i=>{const row=original[i];row.hidden=selectedStatus!=='all'&&data.rows[i].status!==selectedStatus;tbody.append(row);});
  }
  document.querySelectorAll('#summary-filter button').forEach(button=>button.onclick=()=>{selectedStatus=button.dataset.status;document.querySelectorAll('#summary-filter button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));filterSort();});
  document.getElementById('summary-sort').onchange=filterSort;
  document.getElementById('expand').onclick=()=>document.querySelectorAll('details').forEach(d=>d.open=true);
  document.getElementById('collapse').onclick=()=>document.querySelectorAll('details').forEach(d=>d.open=false);
  const details=[...document.querySelectorAll('details')];let beforePrint=[];
  window.addEventListener('beforeprint',()=>{beforePrint=details.map(d=>d.open);details.forEach(d=>d.open=true);});
  window.addEventListener('afterprint',()=>details.forEach((d,i)=>d.open=beforePrint[i]));
  const links=[...document.querySelectorAll('nav a')];
  if('IntersectionObserver' in window){
    const observer=new IntersectionObserver(entries=>{for(const entry of entries)if(entry.isIntersecting){links.forEach(a=>a.removeAttribute('aria-current'));links.find(a=>a.hash==='#'+entry.target.id)?.setAttribute('aria-current','location');}},{rootMargin:'-5% 0px -65% 0px'});
    document.querySelectorAll('section.chapter').forEach(s=>observer.observe(s));
  }
  document.querySelectorAll('.flow-step').forEach(step=>{
    const show=()=>{step.closest('figure').querySelector('.diagram-explanation').textContent=step.dataset.explanation;};
    step.addEventListener('mouseenter',show);step.addEventListener('focus',show);
  });
  document.querySelectorAll('.copy-code').forEach(button=>button.onclick=async()=>{try{await navigator.clipboard.writeText(button.previousElementSibling.textContent);button.textContent='Скопировано';}catch{button.textContent='Копирование недоступно; выделите текст вручную';}});
  const hidden=new Set(), colors=['#E2A12B','#56544e'];
  const modelNames=Object.keys(data.summary.models);
  function chart(){
    const svg=document.getElementById('quality-chart');let parts=[];
    for(let tick=0;tick<=100;tick+=25){const x=230+tick*3.5;parts.push(`<line x1="${x}" y1="20" x2="${x}" y2="245" stroke="#E4E0D6"/><text x="${x}" y="270" text-anchor="middle" font-size="13">${tick}</text>`);}
    modelNames.forEach((name,i)=>{
      if(hidden.has(name))return;
      const m=data.summary.models[name];
      [['Статусы',m.audit_correct_checks,m.audit_total_checks],['Действия',m.plan_exact_snapshots,m.plan_snapshots]].forEach(([label,n,d],j)=>{
        const y=35+i*105+j*42,percent=d?100*n/d:0,tip=`${name}, ${label}: ${n}/${d}, ${percent.toFixed(1)}%`;
        parts.push(`<text x="12" y="${y+14}" font-size="12">${escape(name)} · ${label}</text><g tabindex="0" aria-label="${escape(tip)}"><title>${escape(tip)}</title><rect x="230" y="${y}" width="${percent*3.5}" height="22" fill="${colors[i]}"/><text x="${240+percent*3.5}" y="${y+16}" font-size="12">${n}/${d}</text></g>`);
      });
    });
    parts.push('<text x="410" y="300" text-anchor="middle" font-size="13">Совпадение, %</text>');svg.innerHTML=parts.join('');
  }
  modelNames.forEach(name=>{const b=document.createElement('button');b.className='chart-legend';b.textContent=name;b.setAttribute('aria-pressed','true');b.onclick=()=>{hidden.has(name)?hidden.delete(name):hidden.add(name);b.setAttribute('aria-pressed',String(!hidden.has(name)));chart();};document.getElementById('legend').append(b);});
  let chartBuilt=false;
  document.getElementById('results').querySelector('details').addEventListener('toggle',e=>{if(e.target.open&&!chartBuilt){chart();chartBuilt=true;}});
  chart();chartBuilt=true;
  const caseSelect=document.getElementById('demo-case'),pointSelect=document.getElementById('demo-point'),modelSelect=document.getElementById('demo-model');
  function option(value,label){const o=document.createElement('option');o.value=value;o.textContent=label;return o;}
  [...new Map(data.replay.map(r=>[r.case_id,r.title]))].forEach(([id,title])=>caseSelect.append(option(id,id+' · '+title)));
  modelNames.forEach(name=>modelSelect.append(option(name,name)));
  function updatePoints(){pointSelect.replaceChildren();data.replay.filter(r=>r.case_id===caseSelect.value).forEach(r=>pointSelect.append(option(r.checkpoint,format(r.review_at)+' · '+(r.condition||'v1'))));render();}
  function render(){
    const row=data.replay.find(r=>r.case_id===caseSelect.value&&r.checkpoint===Number(pointSelect.value));
    if(!row)return;
    const output=row.models[modelSelect.value];
    const checkRows=(output.audit?.checks||[]).map(c=>{const target=row.formal.checks.find(f=>f.rule_id===c.rule_id);return `<tr><td>${escape(c.rule_id)}</td><td>${escape(names[c.status])}</td><td>${escape(names[target.status])}</td><td>${escape(c.explanation)}</td></tr>`;}).join('');
    const timeline=row.state.events.map(e=>`<li><strong>${format(e.occurred_at)} · ${escape(kinds[e.kind])}</strong>: ${escape(values[e.value]||e.value)} <small>(${escape(e.id)})</small></li>`).join('');
    const recommendations=output.recommend?.recommendations?.map(r=>`<li><strong>${escape(actions[r.action])}</strong> (${escape(r.rule_id)}). ${escape(r.explanation)}</li>`).join('');
    document.getElementById('demo-output').innerHTML=`<h3>${escape(row.case_id)} · ${format(row.review_at)} · ${escape(row.condition||'v1')}</h3><p><span class="claim-kind">Факт</span>Сохранённые результаты эксперимента. Будущие события отсутствуют во входе.</p><h4>Доступные сведения</h4><ol>${timeline}</ol><h4>Рекомендации модели</h4>${output.recommend?recommendations?'<ul>'+recommendations+'</ul>':'<p>Дополнительные действия не предложены.</p>':'<p>Успешного ответа для этого шага нет.</p>'}<h4>Проверка помощи</h4>${output.audit?`<div class="table-wrap"><table><caption>Ответ модели и формальные ожидания</caption><thead><tr><th>Правило</th><th>Модель</th><th>Расчёт</th><th>Объяснение модели</th></tr></thead><tbody>${checkRows}</tbody></table></div>`:'<p>Успешного ответа для этого шага нет.</p>'}`;
  }
  caseSelect.onchange=updatePoints;pointSelect.onchange=render;modelSelect.onchange=render;updatePoints();
})();
