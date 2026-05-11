<script setup>
import { ref, computed, onMounted } from 'vue'
import { useMarketData } from './composables/useMarketData'
import Titlebar from './components/Titlebar.vue'
import Sidebar from './components/Sidebar.vue'
import MarketTable from './components/MarketTable.vue'
import SignalTable from './components/SignalTable.vue'
import KlineModal from './components/KlineModal.vue'

const { date, indices, sentiment, sectors, signals, stocks, loading, load } = useMarketData()

const SIGNAL_TABS = [
  { id: 'RESONANCE',       label: '共振精选' },
  { id: 'LIMIT_UP',        label: 'N字涨停' },
  { id: 'VOLUME_SPIKE',    label: '突然爆量' },
  { id: 'CONSECUTIVE',     label: '连板龙头' },
  { id: 'MA_BREAKOUT',     label: '均线突破' },
  { id: 'MACD_CROSS',      label: 'MACD金叉' },
  { id: 'MACD_DIVERGENCE', label: '底背离' },
]
const ALL_TABS = [{ id: 'MARKET', label: '行情浏览', isMarket: true }, ...SIGNAL_TABS]
const activeTab = ref('MARKET')

const signalCounts = computed(() => {
  const m = {}
  signals.value.forEach(s => m[s.strategy] = (m[s.strategy] || 0) + 1)
  return m
})

function tabCount(t) {
  return t.isMarket ? stocks.value.length : (signalCounts.value[t.id] || 0)
}

const dateStr = computed(() => {
  if (!date.value) return '加载中...'
  const d = String(date.value)
  return `${d.slice(0,4)}-${d.slice(4,6)}-${d.slice(6)} 盘后`
})

// K线
const kline = ref({ open: false, code: '', name: '' })
function openKline(code, name) { kline.value = { open: true, code, name } }
function closeKline() { kline.value.open = false }

onMounted(load)
</script>

<template>
  <div class="app">
    <Titlebar :date-str="dateStr" />
    <div class="body">
      <Sidebar :indices="indices" :sentiment="sentiment" :sectors="sectors" />
      <div class="main">
        <div class="tabs-bar">
          <div v-for="t in ALL_TABS" :key="t.id"
            class="tab" :class="{ active: activeTab === t.id }"
            @click="activeTab = t.id">
            {{ t.label }}<span class="badge">{{ tabCount(t) }}</span>
          </div>
        </div>
        <MarketTable v-if="activeTab === 'MARKET'" :stocks="stocks" @open-kline="openKline" />
        <SignalTable v-else :signals="signals" :strategy="activeTab" @open-kline="openKline" />
      </div>
    </div>
    <KlineModal v-if="kline.open" :ts-code="kline.code" :name="kline.name" @close="closeKline" />
  </div>
</template>

<style>
/* 全局 tabs 样式放这里（不 scoped） */
.tabs-bar {
  padding: 14px 18px 0; display: flex; gap: 4px;
  border-bottom: 1px solid var(--border); background: var(--bg-tab-bar);
  overflow-x: auto; flex-shrink: 0;
}
.tab {
  padding: 7px 13px; font-size: 12px; font-weight: 500;
  color: var(--text-2); border-radius: 7px 7px 0 0; cursor: pointer;
  white-space: nowrap; border: 1px solid transparent; border-bottom: none;
  position: relative; bottom: -1px; transition: all .15s;
}
.tab:hover { color: var(--text); }
.tab.active {
  color: var(--text); background: var(--bg-tab-act);
  border-color: var(--tab-bdr-act); border-bottom-color: var(--bg-tab-act);
}
.badge {
  display: inline-block; background: var(--bg-card); border-radius: 10px;
  padding: 0 5px; font-size: 10px; margin-left: 4px; font-variant-numeric: tabular-nums;
}
.tab.active .badge { background: rgba(10,132,255,.2); color: #0a84ff; }
</style>

<style scoped>
.app { height: 100vh; display: flex; flex-direction: column; }
.body { display: flex; flex: 1; overflow: hidden; }
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
</style>
