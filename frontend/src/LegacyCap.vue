<script setup>
import { ref, computed, onMounted } from 'vue'
import ScenarioLab from './ScenarioLab.vue'
import KnowledgeSearch from './KnowledgeSearch.vue'
const catalog = ref(null), caseId = ref('V01'), checkpoint = ref(0), mode = ref('formal')
const condition = ref('v2')
const model = ref('gemma-4-31b-it'), result = ref(null), busy = ref(false), error = ref('')
const selected = computed(() => catalog.value?.cases.find(c => c.id === caseId.value))
const time = computed(() => selected.value?.review_times[checkpoint.value])
const disagreement = computed(() => Boolean(result.value?.consistency && (result.value.consistency.audit_disagreements.length || result.value.consistency.plan_disagreements.length)))
const visible = computed(() => selected.value?.events.filter(e => new Date(e.occurred_at) <= new Date(time.value) && new Date(e.available_at) <= new Date(time.value)) || [])
const statusNames = { met:'Подтверждено', attention:'Нужен разбор', pending:'Срок ещё идёт', unknown:'Недостаточно данных', not_applicable:'Не применяется' }
const kindNames = { diagnosis:'Диагноз', spo2:'SpO2', antibiotic_order:'Назначение', antibiotic_start:'Начало лечения', reassessment:'Оценка ответа', treatment_review:'Пересмотр тактики', exception:'Исключение', observation:'Наблюдение' }
const valueNames = {confirmed_cap:'Подтверждена внебольничная пневмония',suspected_cap:'Подозрение на пневмонию',improving:'Улучшение',unchanged:'Без изменений',worsening:'Ухудшение',documented:'Подтверждено записью','requires review':'Требуется разбор исключения'}
const actions = {measure_spo2:'Уточнить измерение SpO2',review_antibiotic_order:'Проверить назначение антибиотика',clarify_treatment_start:'Уточнить начало терапии',schedule_reassessment:'Запланировать оценку ответа',assess_response:'Оценить ответ на лечение',review_treatment:'Пересмотреть тактику с врачом',clarify_record:'Уточнить запись',specialist_review:'Разобрать исключение с врачом'}
const formatTime = value => new Date(value).toLocaleString('ru-RU', {timeZone:'Europe/Moscow',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})
const source = id => catalog.value?.cards.find(c => c.id === id)
async function request(path, options) {
  const response = await fetch(path, options)
  if (!response.ok) {
    let message = `Ошибка ${response.status}`
    try { message = (await response.json()).detail || message } catch {}
    throw new Error(typeof message === 'string' ? message : 'Проверьте выбранные параметры.')
  }
  return response.json()
}
onMounted(async () => {
  try { catalog.value = await request('/api/therapy/catalog'); await run() }
  catch(e) { error.value = e.message }
})
function changedCase() { condition.value=caseId.value.startsWith('V')?'v2':'v1'; checkpoint.value = 0; result.value = null; error.value = '' }
function changed() { result.value = null; error.value = '' }
async function run() {
  busy.value = true; error.value = ''; result.value = null
  try {
    result.value = await request('/api/therapy/evaluate', {method:'POST', headers:{'Content-Type':'application/json'},
      body:JSON.stringify({case_id:caseId.value,review_at:time.value,mode:mode.value,model:model.value,condition:condition.value})})
  } catch(e) { error.value = e.message }
  finally { busy.value = false }
}
</script>

<template>
  <main>
    <header><a class="brand" href="/">AIMedicine</a><span>ИТМО · Терапия · Прототип</span></header>
    <h1>От наблюдения<br>к проверке назначений</h1>
    <p class="lead">Одна история болезни во времени: сведения о пациенте, назначения врача, ответ на лечение и основания для повторной оценки.</p>
    <p class="scope">20 синтетических историй · 4 проверки при пневмонии · Взрослые в терапевтическом стационаре. Клиническая проверка правил ещё не проведена.</p>
    <section class="controls" aria-label="Настройки проверки" v-if="catalog">
      <label>История<select v-model="caseId" @change="changedCase" :disabled="busy"><option v-for="c in catalog.cases" :key="c.id" :value="c.id">{{c.id}} · {{c.title}}</option></select></label>
      <label>Момент проверки, МСК<select v-model="checkpoint" @change="changed" :disabled="busy"><option v-for="(t,i) in selected.review_times" :value="i" :key="t">{{formatTime(t)}}</option></select></label>
      <label>Режим<select v-model="mode" @change="changed" :disabled="busy"><option value="formal">Локальные формальные правила</option><option value="recorded">Сохранённые ответы моделей</option><option value="live" v-if="catalog.live_enabled">Новый запрос через Router</option></select></label>
      <label v-if="mode !== 'formal'">Модель<select v-model="model" @change="changed" :disabled="busy"><option v-for="m in catalog.models" :value="m" :key="m">{{m}}</option></select></label>
      <label v-if="mode !== 'formal'">Версия проверки<select v-model="condition" @change="changed" :disabled="busy"><option value="v1">Исходная версия</option><option value="v2" v-if="caseId.startsWith('V') || mode==='live'">С расчётом сроков и независимой проверкой</option></select></label>
      <p class="mode-note">{{mode==='formal' ? 'Работает без API. Результат рассчитан по четырём формализованным правилам.' : mode==='recorded' ? 'Показ реальных ответов из сохранённого эксперимента. Новые запросы не отправляются.' : 'Будут отправлены 2 запроса: рекомендации и отдельная проверка. Ожидание может занять несколько минут.'}}</p>
      <button @click="run" :disabled="busy">{{busy ? 'Выполняется…' : mode==='live' ? 'Запустить 2 запроса' : 'Проверить выбранный момент'}}</button>
    </section>
    <p role="alert" class="error" v-if="error">{{error}}</p>
    <p role="status" v-if="busy">{{mode==='live' ? 'Router обрабатывает задания. Повторная отправка отключена.' : 'Загружаю результат…'}}</p>
    <aside class="error" v-if="disagreement">
      <strong>Ответ модели расходится с формальными правилами</strong>
      <p>Проверка: {{result.consistency.audit_disagreements.join(', ') || 'расхождений нет'}}. Действия: {{result.consistency.plan_disagreements.join(', ') || 'расхождений нет'}}. Ответ сохранён как результат эксперимента и требует разбора. Сравнение доступно под списком проверок.</p>
    </aside>
    <div class="workspace" v-if="selected">
      <section aria-labelledby="timeline"><h2 id="timeline">Сведения на {{formatTime(time)}}</h2>
        <p class="muted">Возраст: {{selected.age}} · Время события и появления записи учитываются отдельно.</p>
        <ol class="timeline"><li v-for="e in visible" :key="e.id"><small>{{formatTime(e.occurred_at)}} · {{e.id}}</small><strong>{{kindNames[e.kind]}}</strong><p>{{valueNames[e.value] || e.value}}{{e.kind==='spo2' ? ' %' : ''}}</p><small v-if="e.available_at!==e.occurred_at">Запись доступна с {{formatTime(e.available_at)}}</small></li></ol>
        <p v-if="!visible.length">К выбранному моменту сведений нет.</p>
      </section>
      <section aria-labelledby="findings"><h2 id="findings">Проверка записанной помощи</h2>
        <p v-if="!result" class="muted">Нажмите «Проверить выбранный момент».</p>
        <div v-if="result">
          <p class="muted">{{result.mode==='formal' ? 'Расчёт программы по исследовательским правилам.' : 'Ответ модели. Ниже можно сопоставить его с расчётом программы.'}}</p>
          <article v-for="c in (result.audit?.result.checks || result.formal_reference.checks)" :key="c.rule_id" class="finding">
            <div class="finding-head"><strong>{{source(c.source_id)?.title || c.rule_id}}</strong><span class="badge" :class="c.status">{{statusNames[c.status]}}</span></div><p>{{c.explanation}}</p>
            <small>{{c.rule_id}} · <a :href="source(c.source_id)?.url" target="_blank" rel="noopener">КР 2024, стр. {{source(c.source_id)?.page}}</a> · События: {{c.evidence_ids.join(', ') || 'запись отсутствует'}}</small>
          </article>
          <details v-if="result.temporal_facts"><summary>Сроки, рассчитанные программой</summary><p>От диагноза до назначения: {{result.temporal_facts.order_since_diagnosis_seconds == null ? 'нет данных' : result.temporal_facts.order_since_diagnosis_seconds/3600+' ч'}}. От начала лечения до проверки: {{result.temporal_facts.review_since_start_seconds == null ? 'нет данных' : result.temporal_facts.review_since_start_seconds/3600+' ч'}}.</p></details>
          <details v-if="result.audit"><summary>Сопоставить с формальными правилами</summary><p v-for="c in result.formal_reference.checks" :key="c.rule_id">{{c.rule_id}}: {{statusNames[c.status]}}. {{c.explanation}}</p></details>
        </div>
      </section>
    </div>
    <section v-if="result?.formal_actions"><h2>Действия по формальным правилам</h2><p class="muted">Расчёт программы для сравнения с моделью. Правила ещё требуют клинического согласования.</p><p v-if="!result.formal_actions.length">В пределах четырёх проверок дополнительных действий нет.</p><ul><li v-for="r in result.formal_actions" :key="r.rule_id">{{r.rule_id}} · {{actions[r.action]}} · <a :href="source(r.source_id)?.url" target="_blank" rel="noopener">Основание</a></li></ul></section>
    <section v-if="result?.plan"><h2>{{disagreement ? 'Черновик модели с расхождениями' : 'Предложения модели для обсуждения с врачом'}}</h2><p v-if="disagreement" class="error">Этот черновик не прошёл сверку с формальными правилами. Ожидаемые действия приведены выше; исходный ответ сохранён для разбора.</p><p v-if="!result.plan.result.recommendations.length">Модель не предложила дополнительных действий в пределах четырёх проверок.</p><article class="finding" v-for="r in result.plan.result.recommendations" :key="r.rule_id"><strong>{{actions[r.action]}}</strong><p>{{r.explanation}}</p><small>{{r.rule_id}} · <a :href="source(r.source_id)?.url" target="_blank" rel="noopener">Источник, стр. {{source(r.source_id)?.page}}</a></small></article><p class="muted">{{result.plan.model}} · {{result.mode==='recorded' ? 'Сохранённый запуск' : 'Новый запуск'}} · Два шага: {{((result.plan.latency_ms+result.audit.latency_ms)/1000).toFixed(1)}} с · Новые назначения в карту не записываются.</p></section>
    <ScenarioLab />
    <KnowledgeSearch />
    <section v-if="catalog"><h2>На чём основаны проверки</h2><p>Разобран документ «Внебольничная пневмония у взрослых», 2024, 73 страницы. Для пилота вручную проверены положения на страницах 13, 24 и 28. В рубрикаторе 04.11.2026 проверен статус «Применяется» для 654_2. Правила прототипа ещё нужно согласовать.</p><details><summary>Границы прототипа</summary><p>Проверяются наличие SpO2, срок назначения антибиотика, оценка ответа через 48–72 часа и запись пересмотра при явном ухудшении. Подбор препарата, дозировки, постановка диагноза и расчёт санкций не реализованы. Отсутствующая запись даёт статус «Недостаточно данных».</p></details></section>
    <footer>Учебный проект · Все истории вымышлены · Версия {{catalog?.version}}</footer>
  </main>
</template>

<style>
:root{font-family:system-ui,-apple-system,sans-serif;color:#24262a;background:#f5f5f3;font-synthesis:none}*{box-sizing:border-box}body{margin:0}main{max-width:1200px;margin:auto;padding:30px 28px 50px}header{display:flex;justify-content:space-between;gap:16px;font-size:13px;color:#60636a}.brand{font-weight:750;color:#24262a;text-decoration:none;letter-spacing:.5px}h1{font-size:clamp(32px,5vw,54px);line-height:1.08;letter-spacing:-1.6px;margin:48px 0 20px}h2{font-size:21px;line-height:1.3;margin:0 0 20px}p{line-height:1.6}.lead{font-size:19px;max-width:780px;color:#54575b}.scope{font-size:13px;color:#60636a;max-width:850px;margin-bottom:30px}section{background:#fff;border:1px solid #deded8;border-radius:12px;padding:26px;margin-bottom:22px}.controls{display:grid;grid-template-columns:2fr 1fr;gap:18px}label{display:flex;flex-direction:column;gap:8px;font-size:13px;font-weight:650;min-width:0}select{padding:12px;border:1px solid #c8c9c4;border-radius:6px;font:inherit;font-weight:400;background:#fff;max-width:100%;color:#24262a}button{border:0;border-radius:6px;background:#2b3e50;color:#fff;font-size:15px;padding:13px 20px;cursor:pointer;justify-self:start}button:disabled,select:disabled{opacity:.55;cursor:wait}.mode-note{grid-column:1/-1;margin:0;color:#54575b;font-size:13px}.workspace{display:grid;grid-template-columns:.9fr 1.3fr;gap:22px}.muted,small{color:#60636a;font-size:12px}small{overflow-wrap:anywhere}a{color:#2c536e}a:hover{text-decoration-thickness:2px}.timeline{list-style:none;margin:0;padding:0 0 0 15px;border-left:2px solid #e1e2df}.timeline li{position:relative;padding:0 0 23px 10px}.timeline li:before{content:'';position:absolute;width:8px;height:8px;border-radius:50%;left:-20px;top:5px;background:#687f8f}.timeline strong{display:block;margin:5px 0}.timeline p{margin:5px 0;font-size:14px}.finding{border-top:1px solid #e5e5e0;padding:18px 0}.finding p{font-size:14px;margin:10px 0}.finding-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;font-size:14px}.badge{white-space:nowrap;padding:4px 7px;border-radius:4px;font-size:11px;background:#edf0f2;color:#445366}.badge.met{background:#edf5ef;color:#246037}.badge.attention{background:#f9eee1;color:#825216}.badge.unknown{background:#f2eeee;color:#725552}details{margin-top:16px;font-size:14px}summary{cursor:pointer;font-weight:600}footer{padding-top:10px;color:#60636a;font-size:12px}.error{padding:15px;background:#fbeceb;border:1px solid #d58f88;border-radius:6px;color:#8e2d23}:focus-visible{outline:3px solid #5f86a4;outline-offset:3px}@media(max-width:760px){main{padding:24px 16px}.workspace,.controls{grid-template-columns:1fr}section{padding:20px}.finding-head{flex-wrap:wrap}header{font-size:11px}h1{letter-spacing:-.8px;margin-top:36px}}@media print{.controls,button,header{display:none}body{background:#fff}.workspace{display:block}section{break-inside:avoid}main{padding:0}}
</style>
