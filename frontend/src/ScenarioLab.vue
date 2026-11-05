<script setup>
import {ref, computed, onMounted} from 'vue'
const hour=ref(0), course=ref('improving'), actions=ref([]), result=ref(null), error=ref(''), busy=ref(false)
const names={measure_spo2:'Измерить SpO2',antibiotic_order:'Записать назначение',antibiotic_start:'Записать начало лечения',reassessment:'Провести повторный осмотр',treatment_review:'Записать пересмотр тактики'}
const labels={met:'Подтверждено',pending:'Срок ещё идёт',unknown:'Недостаточно данных',attention:'Нужен разбор',not_applicable:'Не применяется'}
const has=kind=>actions.value.some(a=>a.kind===kind)
const disabled=kind=>busy.value || actions.value.length>=40 || ((kind==='antibiotic_order'||kind==='antibiotic_start') && has(kind)) || (kind==='antibiotic_start'&&!has('antibiotic_order')) || (['reassessment','treatment_review'].includes(kind)&&!has('antibiotic_start')) || (kind==='treatment_review'&&!has('reassessment'))
const elapsed=computed(()=>result.value?.temporal_facts.review_since_start_seconds)
async function update(nextActions=actions.value,nextHour=hour.value){
  busy.value=true;error.value=''
  try{
    const response=await fetch('/api/therapy/simulate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({elapsed_hours:nextHour,response:course.value,actions:nextActions})})
    if(!response.ok)throw new Error('Не удалось рассчитать сценарий. Проверьте последовательность действий.')
    result.value=await response.json();actions.value=nextActions;hour.value=nextHour
  }catch(e){error.value=e.message}finally{busy.value=false}
}
const act=kind=>update([...actions.value,{kind,hour:hour.value}])
const advance=hours=>update(actions.value,hour.value+hours)
const reset=()=>update([],0)
onMounted(()=>update())
</script>
<template>
<section aria-labelledby="lab-title">
  <h2 id="lab-title">Попробовать свои действия</h2>
  <p>Учебный пациент, 59 лет, подтверждённая нетяжёлая пневмония. Запишите действия врача и переведите часы вперёд. Проверки пересчитываются после каждого шага, запросы к моделям не расходуются.</p>
  <label>Ветка ответа на лечение<select v-model="course" @change="update()" :disabled="actions.length>0||busy"><option value="improving">Улучшение</option><option value="unchanged">Без изменений</option><option value="worsening">Ухудшение</option></select></label>
  <p class="muted">Ветка задана автором и появится в записи повторного осмотра. Программа не предсказывает эффект препарата и не рассчитывает вероятность исхода. Чтобы сменить ветку, начните заново.</p>
  <p><strong>От диагноза: {{hour}} ч</strong><span v-if="elapsed!=null"> · От начала терапии: {{elapsed/3600}} ч</span></p>
  <div class="lab-buttons"><button v-for="n in [2,24,48]" :key="n" @click="advance(n)" :disabled="busy||hour+n>168">+{{n}} ч</button><button @click="reset" :disabled="busy">Начать заново</button></div>
  <div class="lab-buttons"><button v-for="(name,kind) in names" :key="kind" @click="act(kind)" :disabled="disabled(kind)">{{name}}</button></div>
  <p role="alert" class="error" v-if="error">{{error}}</p>
  <p v-if="!actions.length" class="muted">Действий пока нет.</p>
  <ol class="lab-history"><li v-for="(a,i) in actions" :key="i">{{a.hour}} ч · {{names[a.kind]}}</li></ol>
  <div v-if="result" class="lab-checks" aria-live="polite"><article class="finding" v-for="c in result.formal_reference.checks" :key="c.rule_id"><strong>{{c.rule_id}} · {{labels[c.status]}}</strong><p>{{c.explanation}}</p></article></div>
</section>
</template>
<style scoped>
.lab-buttons{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}.lab-buttons button{font-size:13px;padding:10px 12px}.lab-history{padding-left:22px;font-size:14px;line-height:1.8}.lab-checks{display:grid;grid-template-columns:1fr 1fr;gap:0 24px}label{max-width:350px}@media(max-width:760px){.lab-checks{grid-template-columns:1fr}}
</style>
