<script setup>
import { ref } from 'vue'
import LegacyCap from './LegacyCap.vue'
import MultiTherapy from './MultiTherapy.vue'
import { staticMode } from './demoTransport'
const tab=ref('multi')
</script>
<template>
  <nav v-if="!staticMode" class="app-tabs" aria-label="Версия прототипа">
    <button @click="tab='multi'" :aria-pressed="tab==='multi'">Пять направлений терапии</button>
    <button @click="tab='legacy'" :aria-pressed="tab==='legacy'">Предыдущий пилот: пневмония</button>
  </nav>
  <MultiTherapy v-if="tab==='multi'"/><LegacyCap v-else/>
</template>
<style>
.app-tabs{display:flex;gap:10px;max-width:1280px;margin:20px auto;padding:0 24px;flex-wrap:wrap}.app-tabs button{background:white;color:#334155;border:1px solid #cbd5e1;padding:10px 16px;border-radius:8px;cursor:pointer}.app-tabs button[aria-pressed=true]{background:#1e3a5f;color:white}
</style>
