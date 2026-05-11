<script setup>
import { computed } from 'vue'
import { useSettingsStore } from '../stores/settings'

const props = defineProps({ dateStr: String })
const settings = useSettingsStore()

const themeIcon = computed(() => ({ auto: '🌗', light: '☀️', dark: '🌙' }[settings.theme]))
const themeLabel = computed(() => ({ auto: '自动', light: '浅色', dark: '深色' }[settings.theme]))
const colorIcon = computed(() => settings.colorMode === 'rg' ? '🔴' : '🟢')
const colorLabel = computed(() => settings.colorMode === 'rg' ? '红涨绿跌' : '绿涨红跌')
</script>

<template>
  <header class="titlebar">
    <span class="title">A股交易系统</span>
    <div class="right">
      <span class="date">{{ dateStr }}</span>
      <button class="btn" @click="settings.toggleColor()">{{ colorIcon }} {{ colorLabel }}</button>
      <button class="btn" @click="settings.cycleTheme()">{{ themeIcon }} {{ themeLabel }}</button>
    </div>
  </header>
</template>

<style scoped>
.titlebar {
  background: var(--bg-sidebar); border-bottom: 1px solid var(--border);
  padding: 12px 20px; display: flex; justify-content: space-between;
  align-items: center; flex-shrink: 0;
}
.title { font-size: 15px; font-weight: 600; }
.right { display: flex; align-items: center; gap: 14px; }
.date { font-size: 12px; color: var(--text-2); font-variant-numeric: tabular-nums; }
.btn {
  background: var(--bg-card); border: 1px solid var(--border-card);
  border-radius: 20px; padding: 4px 10px; cursor: pointer;
  font-size: 12px; color: var(--text-2); display: flex; align-items: center;
  gap: 5px; transition: all .15s;
}
.btn:hover { color: var(--text); }
</style>
