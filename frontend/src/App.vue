<script setup>
import { ref, onMounted } from 'vue'
const config = ref(null), result = ref(null), error = ref(''), busy = ref(false)
async function request(path, options) {
  const response = await fetch(path, options)
  if (!response.ok) {
    let message = `Ошибка ${response.status}`
    try { message = (await response.json()).detail || message } catch { /* no JSON from proxy */ }
    throw new Error(message)
  }
  return response.json()
}
onMounted(async () => {
  try { config.value = await request('/api/status') }
  catch { error.value = 'Сервер недоступен. Запустите backend по инструкции в README.' }
})
async function check() {
  busy.value = true; error.value = ''; result.value = null
  try { result.value = await request('/api/smoke', { method: 'POST' }) }
  catch (e) { error.value = e.message }
  finally { busy.value = false }
}
</script>

<template>
  <main>
    <header><span class="eyebrow">ИТМО · ЭТАП 01</span><span class="badge">Подготовка</span></header>
    <h1>Основа для проверки<br>медицинской документации</h1>
    <p class="intro">Первая функция будет находить недостающие сведения в синтетической истории болезни и показывать основания из клинических рекомендаций. Сейчас подготовлены спецификация и окружение.</p>
    <section aria-labelledby="connection">
      <h2 id="connection">Подключение модели</h2>
      <dl v-if="config"><div><dt>Провайдер</dt><dd>{{ config.provider }}</dd></div><div><dt>Модель</dt><dd>{{ config.model }}</dd></div><div><dt>Режим</dt><dd>{{ config.mode === 'mock' ? 'Локальная имитация' : 'Реальный API' }}</dd></div></dl>
      <p v-if="config?.mode === 'mock'">Тест проверяет работу приложения без ключа и обращения к Mistral. Он не подтверждает доступ к модели.</p>
      <p v-else-if="config">Проверка отправит один технический запрос в Mistral. Медицинские данные в нём отсутствуют.</p>
      <button :disabled="busy || !config" @click="check">{{ busy ? 'Проверяем…' : config?.mode === 'live' ? 'Проверить Mistral API' : 'Проверить локальный режим' }}</button>
      <p role="alert" class="error" v-if="error">{{ error }}</p>
      <div v-if="result" class="result" role="status"><strong>{{ result.mode === 'mock' ? 'Локальная проверка пройдена' : 'Ответ Mistral получен' }}</strong><p>{{ result.result.message }}</p><small>Режим: {{ result.mode }} · запросов к API: {{ result.attempts }}</small></div>
    </section>
    <aside><h2>Почему пока Mistral</h2><p>Google AI Studio перенаправлял на страницу доступных регионов. Ключ Gemini получить не удалось. Вернёмся к подключению Gemini/Gemma позже и сравним модели на одинаковых примерах.</p></aside>
    <footer>Учебный проект · Клиническая функция ещё не реализована · Только синтетические данные</footer>
  </main>
</template>

<style>
:root{font-family:system-ui,-apple-system,sans-serif;color:#173332;background:#f1f5f2;font-synthesis:none}*{box-sizing:border-box}body{margin:0}main{max-width:950px;margin:0 auto;padding:48px 28px}header{display:flex;justify-content:space-between;align-items:center}.eyebrow{font-size:12px;letter-spacing:2px;font-weight:700}.badge{background:#dfece5;padding:7px 12px;border-radius:20px;font-size:12px}h1{font-size:clamp(30px,5vw,48px);line-height:1.12;letter-spacing:-1.5px;margin:42px 0 22px}.intro{max-width:760px;font-size:18px;color:#4a6562;line-height:1.6}section{background:white;border:1px solid #d4e0d9;border-radius:20px;padding:28px;margin-top:32px}h2{font-size:20px;margin-top:0}p{line-height:1.6}dl{display:flex;flex-wrap:wrap;gap:32px;padding:10px 0}dt{color:#526c67;font-size:13px}dd{margin:5px 0;font-weight:600;overflow-wrap:anywhere}button{border:0;border-radius:10px;padding:13px 18px;background:#17614f;color:white;font-size:15px;cursor:pointer}button:disabled{opacity:.5;cursor:wait}.result{background:#edf6f0;border-left:3px solid #39846a;padding:16px;margin-top:20px}.result p{margin:8px 0}.error{color:#a33526}aside{padding:28px 0 8px;color:#4a6562}footer{border-top:1px solid #d4e0d9;padding-top:20px;font-size:12px;color:#526c67}@media(max-width:500px){main{padding:28px 18px}section{padding:20px}dl{gap:18px}h1{letter-spacing:-.8px}}
</style>
