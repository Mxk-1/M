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
  { id: 'RESONANCE',       label: '共振精选',  tip: '同一只股票同时触发 2 个及以上策略信号，多重共鸣说明它当天被市场从多个维度认可，综合得分最高的票出现在这里。' },
  { id: 'LIMIT_UP',        label: 'N字涨停',   tip: '当日涨幅 ≥ 9.5% 且有封单确认涨停。N 字形态指昨日涨停、今日低开再度封板，是主力二次发动的强势信号。' },
  { id: 'VOLUME_SPIKE',    label: '突然爆量',   tip: '今日成交量是近 5 日均量的 3 倍以上，且股价上涨超 3%。异常放量通常意味着大资金介入，是行情启动的早期预警。' },
  { id: 'CONSECUTIVE',     label: '连板龙头',   tip: '连续 2 天及以上涨停的股票。连板本身就是最强的资金集中信号，市场用真金白银投票，龙头效应明显。' },
  { id: 'MA_BREAKOUT',     label: '均线突破',   tip: '5 日均线上穿 10 日均线（短期趋势转强），或股价站上 60 日均线（中期趋势扭转）。均线是市场平均持仓成本，突破意味着多方占优。' },
  { id: 'MACD_CROSS',      label: 'MACD金叉',  tip: 'DIF 线从下方穿越 DEA 线形成金叉。零轴上方金叉是强势延续，零轴下方金叉是底部反转信号，两类均收录。' },
  { id: 'MACD_DIVERGENCE', label: '底背离',     tip: '近 30 日内股价创出新低，但 MACD 的 DIF 指标没有同步新低。价格与动能出现背离，意味着下跌动力衰竭，可能是阶段性底部。' },
  { id: 'BIG_MONEY',       label: '大单净流入', tip: '当日大单净买入占成交额 ≥ 8%，且价格收阳线。大单代表机构/主力真实动向，净买入说明聪明钱在悄悄进场，而非散户追涨。' },
  { id: 'PULLBACK',        label: '龙头回踩',   tip: '5-15日内曾涨停、随后缩量回调不超过15%、今日放量阳线二次启动。主力洗盘后重新发力，是参与强势股二波行情的经典形态。' },
  { id: 'SECTOR_HOT',     label: '板块联动',   tip: '同行业当日涨停数 ≥ 3 且本股涨幅 ≥ 2%。行业集体涨停说明主题正在发酵，联动股是还未涨停的补涨机会，行业涨停越多热度越高。' },
  { id: 'TOP_LIST',       label: '龙虎榜买入', tip: '当日登上龙虎榜且净买入 > 0，股价上涨。龙虎榜是大资金真实动向的证明，净买入说明机构/游资在主动进场而非出货。' },
]
const ALL_TABS = [{ id: 'MARKET', label: '行情浏览', isMarket: true, tip: '当日全市场 A 股行情，支持按涨跌、板块、交易所筛选，点击任意个股查看 K 线图。' }, ...SIGNAL_TABS]

// Tooltip
const tooltip = ref({ visible: false, text: '', x: 0, y: 0 })
let tooltipTimer = null
function showTip(e, text) {
  if (!text) return
  clearTimeout(tooltipTimer)
  tooltipTimer = setTimeout(() => {
    const r = e.target.getBoundingClientRect()
    tooltip.value = { visible: true, text, x: r.left + r.width / 2, y: r.bottom + 8 }
  }, 600)
}
function hideTip() {
  clearTimeout(tooltipTimer)
  tooltip.value.visible = false
}
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
            @click="activeTab = t.id"
            @mouseenter="e => showTip(e, t.tip)"
            @mouseleave="hideTip">
            {{ t.label }}<span class="badge">{{ tabCount(t) }}</span>
          </div>
        </div>

        <!-- 全局 Tooltip -->
        <Teleport to="body">
          <div v-if="tooltip.visible" class="tab-tooltip"
            :style="{ left: tooltip.x + 'px', top: tooltip.y + 'px' }">
            {{ tooltip.text }}
          </div>
        </Teleport>
        <MarketTable v-if="activeTab === 'MARKET'" :stocks="stocks" @open-kline="openKline" />
        <SignalTable v-else :signals="signals" :strategy="activeTab" @open-kline="openKline" />
      </div>
    </div>
    <KlineModal v-if="kline.open" :ts-code="kline.code" :name="kline.name" @close="closeKline" />
  </div>
</template>

<style>
/* Tooltip */
.tab-tooltip {
  position: fixed;
  transform: translateX(-50%);
  z-index: 200;
  max-width: 280px;
  background: var(--bg-sidebar);
  border: 1px solid var(--border-card);
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-2);
  box-shadow: 0 8px 32px rgba(0,0,0,.2);
  pointer-events: none;
  white-space: normal;
}

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
