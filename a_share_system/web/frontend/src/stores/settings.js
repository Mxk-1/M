import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

export const useSettingsStore = defineStore('settings', () => {
  const theme = ref(localStorage.getItem('theme') || 'auto')
  const colorMode = ref(localStorage.getItem('colorMode') || 'gr')

  function applyTheme(t) {
    document.documentElement.setAttribute('data-theme', t)
  }
  function applyColor(c) {
    document.documentElement.setAttribute('data-color', c)
  }

  function cycleTheme() {
    const order = ['auto', 'light', 'dark']
    theme.value = order[(order.indexOf(theme.value) + 1) % order.length]
  }
  function toggleColor() {
    colorMode.value = colorMode.value === 'gr' ? 'rg' : 'gr'
  }

  watch(theme, t => { localStorage.setItem('theme', t); applyTheme(t) }, { immediate: true })
  watch(colorMode, c => { localStorage.setItem('colorMode', c); applyColor(c) }, { immediate: true })

  return { theme, colorMode, cycleTheme, toggleColor }
})
