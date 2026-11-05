<script setup>
import {ref} from 'vue'
const query=ref('пульсоксиметрия'),scope=ref('inpatient'),results=ref(null),busy=ref(false),error=ref('')
async function search(){
 busy.value=true;error.value=''
 try{
  const r=await fetch('/api/therapy/search',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:query.value,scope:scope.value})})
  const body=await r.json();if(!r.ok)throw new Error(typeof body.detail==='string'?body.detail:'Проверьте запрос.')
  results.value=body.results
 }catch(e){error.value=e.message}finally{busy.value=false}
}
</script>
<template>
<section aria-labelledby="search-title"><h2 id="search-title">Найти положение в документе</h2><p>Поиск по КР «Внебольничная пневмония у взрослых», 2024. Результаты ведут на страницу источника; совпадение слов ещё не подтверждает применимость рекомендации.</p>
<form @submit.prevent="search" class="search-form"><label>Запрос<input v-model="query" minlength="2" maxlength="200" required></label><label>Разделы<select v-model="scope"><option value="clinical">Основной текст без приложений и литературы</option><option value="inpatient">Диагностика и стационар</option><option value="all">Весь документ</option></select></label><button :disabled="busy">{{busy?'Ищу…':'Найти в КР'}}</button></form>
<p role="alert" v-if="error" class="error">{{error}}</p><div aria-live="polite"><p v-if="results?.length===0">Подходящих фрагментов не найдено. Попробуйте слова из документа или другой раздел.</p><article class="finding" v-for="r in results" :key="r.id"><a :href="r.url" target="_blank" rel="noopener"><strong>КР 2024 · стр. {{r.page}}</strong></a><p>{{r.snippet}}</p><small>{{r.id}} · найдено {{Math.round(r.coverage*100)}} % групп слов запроса</small></article></div>
<p class="muted">Индекс локальный, API не вызывается. Поиск пока проверен на небольшом наборе запросов; статус «Применяется» для 654_2 проверен 04.11.2026, формализация ожидает согласования.</p></section>
</template>
<style scoped>
.search-form{display:grid;grid-template-columns:1fr 1fr;gap:16px}input{padding:12px;font:inherit;border:1px solid #c8c9c4;border-radius:6px;min-width:0}@media(max-width:760px){.search-form{grid-template-columns:1fr}}
</style>
