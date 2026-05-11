<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ signals: Array, strategy: String })
const emit = defineEmits(['open-kline'])

const search = ref('')

const TN = { LIMIT_UP:'N字涨停', VOLUME_SPIKE:'爆量', MA_BREAKOUT:'均线', MACD_CROSS:'MACD', MACD_DIVERGENCE:'底背离', CONSECUTIVE:'连板', RESONANCE:'共振' }
const TC = { LIMIT_UP:'l', VOLUME_SPIKE:'v', MA_BREAKOUT:'m', MACD_CROSS:'m', MACD_DIVERGENCE:'m', CONSECUTIVE:'m', RESONANCE:'r' }

const filtered = computed(() => {
  let rows = props.signals.filter(s => s.strategy === props.strategy)
  const q = search.value.trim().toLowerCase()
  if (q) rows = rows.filter(r => r.name.includes(q) || r.ts_code.toLowerCase().includes(q))
  return rows
})
</script>

<template>
  <div class="pane">
    <div class="toolbar">
      <input class="search-input" v-model="search" placeholder="搜索股票名称或代码..." />
      <span class="spacer"></span>
      <span class="count">{{ filtered.length }} 只</span>
    </div>
    <div class="table-wrap">
      <table>
        <thead>
          <tr><th>#</th><th>股票</th><th>涨幅</th><th>量比</th><th>连板</th><th>触发策略</th><th>评分</th></tr>
        </thead>
        <tbody>
          <tr v-if="!filtered.length"><td colspan="7" class="empty">暂无信号</td></tr>
          <tr v-for="(s, i) in filtered" :key="`${s.ts_code}-${s.strategy}`" @click="emit('open-kline', s.ts_code, s.name)">
            <td class="num">{{ i + 1 }}</td>
            <td><div class="sn">{{ s.name }}</div><div class="sc">{{ s.ts_code }}</div></td>
            <td :class="s.pct_chg >= 0 ? 'up' : 'dn'" class="mono fw">{{ s.pct_chg >= 0 ? '+' : '' }}{{ s.pct_chg.toFixed(2) }}%</td>
            <td class="mono">{{ s.vol_ratio.toFixed(2) }}x</td>
            <td>
              <span v-if="s.boards >= 2" class="board-badge">{{ s.boards }}板</span>
              <span v-else class="muted">—</span>
            </td>
            <td>
              <span v-for="t in s.triggered" :key="t" class="tag" :class="`tag-${TC[t]||'m'}`">{{ TN[t] || t }}</span>
            </td>
            <td class="score">{{ s.score.toFixed(1) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.pane { display: flex; flex-direction: column; flex: 1; overflow: hidden; }
.toolbar { padding: 10px 18px; display: flex; gap: 10px; align-items: center; flex-shrink: 0; border-bottom: 1px solid var(--border); background: var(--bg-tab-act); }
.search-input { background: var(--input-bg); border: 1px solid var(--border-card); border-radius: 8px; padding: 5px 10px; font-size: 12px; color: var(--text); outline: none; width: 200px; }
.search-input:focus { border-color: rgba(10,132,255,.5); }
.spacer { flex: 1; }
.count { font-size: 12px; color: var(--text-2); font-variant-numeric: tabular-nums; }
.table-wrap { flex: 1; overflow-y: auto; background: var(--bg-table); padding: 0 18px 14px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead { position: sticky; top: 0; z-index: 1; background: var(--bg-table); }
thead tr { border-bottom: 1px solid var(--border); }
th { padding: 10px 10px 8px; text-align: left; font-size: 10px; font-weight: 600; color: var(--text-2); letter-spacing: .05em; text-transform: uppercase; white-space: nowrap; }
th:last-child, td:last-child { text-align: right; }
tbody tr { border-bottom: 1px solid var(--border); cursor: pointer; transition: background .1s; }
tbody tr:hover { background: var(--bg-row-hover); }
tbody tr:last-child { border-bottom: none; }
td { padding: 10px; color: var(--text); vertical-align: middle; }
.sn { font-weight: 600; font-size: 13px; }
.sc { font-size: 10px; color: var(--text-2); margin-top: 1px; font-family: "SF Mono", monospace; }
.up { color: var(--up); } .dn { color: var(--dn); }
.mono { font-variant-numeric: tabular-nums; }
.fw { font-weight: 600; }
.muted { color: var(--text-2); }
.num { color: var(--text-2); font-size: 12px; }
.score { font-weight: 700; color: var(--score-col); font-variant-numeric: tabular-nums; }
.board-badge { background: rgba(255,159,10,.18); color: #ff9f0a; border-radius: 5px; padding: 2px 6px; font-size: 10px; font-weight: 700; }
.tag { display: inline-block; padding: 2px 7px; border-radius: 5px; font-size: 10px; font-weight: 500; margin-right: 3px; }
.tag-r { background: rgba(191,90,242,.18); color: #bf5af2; }
.tag-l { background: rgba(255,69,58,.14); color: #ff6961; }
.tag-v { background: rgba(10,132,255,.14); color: #0a84ff; }
.tag-m { background: rgba(255,159,10,.14); color: #ff9f0a; }
.empty { text-align: center; padding: 40px; color: var(--text-2); }
</style>
