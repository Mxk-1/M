<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ signals: Array, strategy: String })
const emit = defineEmits(['open-kline'])

const search = ref('')
const board  = ref('ALL')

const TN = { LIMIT_UP:'N字涨停', VOLUME_SPIKE:'爆量', MA_BREAKOUT:'均线', MACD_CROSS:'MACD', MACD_DIVERGENCE:'底背离', CONSECUTIVE:'连板', RESONANCE:'共振', BIG_MONEY:'大单', PULLBACK:'回踩', SECTOR_HOT:'板块联动', TOP_LIST:'龙虎榜' }
const TC = { LIMIT_UP:'l', VOLUME_SPIKE:'v', MA_BREAKOUT:'m', MACD_CROSS:'m', MACD_DIVERGENCE:'m', CONSECUTIVE:'m', RESONANCE:'r', BIG_MONEY:'b', PULLBACK:'p', SECTOR_HOT:'s', TOP_LIST:'t' }

const BOARDS = [
  { id: 'ALL',  label: '全板' },
  { id: 'MAIN', label: '主板' },
  { id: 'GEM',  label: '创业板' },
  { id: 'STAR', label: '科创板' },
  { id: 'BSE',  label: '北交所' },
  { id: 'ST',   label: 'ST' },
  { id: 'NONST',label: '非ST' },
]

function getBoard(code) {
  if (code.endsWith('.BJ'))                                              return { id: 'BSE',  label: '北交', cls: 'bj' }
  if (code.endsWith('.SH') && code.startsWith('688'))                   return { id: 'STAR', label: '科创', cls: 'kc' }
  if (code.endsWith('.SZ') && (code.startsWith('300') || code.startsWith('301'))) return { id: 'GEM',  label: '创业', cls: 'cy' }
  return null
}

const filtered = computed(() => {
  let rows = props.signals.filter(s => s.strategy === props.strategy)
  const q = search.value.trim().toLowerCase()
  if (q) rows = rows.filter(r => r.name.includes(q) || r.ts_code.toLowerCase().includes(q))

  if (board.value !== 'ALL') {
    if (board.value === 'MAIN')  rows = rows.filter(r => !getBoard(r.ts_code) && !r.ts_code.endsWith('.BJ'))
    else if (board.value === 'ST')    rows = rows.filter(r => r.name.includes('ST'))
    else if (board.value === 'NONST') rows = rows.filter(r => !r.name.includes('ST'))
    else rows = rows.filter(r => getBoard(r.ts_code)?.id === board.value)
  }

  return rows
})
</script>

<template>
  <div class="pane">
    <div class="toolbar">
      <input class="search-input" v-model="search" placeholder="搜索股票名称或代码..." />

      <!-- 板块筛选 -->
      <div class="btn-group">
        <button v-for="b in BOARDS" :key="b.id"
          class="filter-btn" :class="{ active: board === b.id }"
          @click="board = b.id">{{ b.label }}</button>
      </div>

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
            <td>
              <div class="name-row">
                <span class="sn">{{ s.name }}</span>
                <span v-if="getBoard(s.ts_code)" class="board-tag"
                  :class="`board-${getBoard(s.ts_code).cls}`">{{ getBoard(s.ts_code).label }}</span>
              </div>
              <div class="sc">{{ s.ts_code }}</div>
            </td>
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
.toolbar {
  padding: 10px 18px; display: flex; gap: 8px; align-items: center;
  flex-shrink: 0; border-bottom: 1px solid var(--border); background: var(--bg-tab-act);
  flex-wrap: wrap;
}
.search-input {
  background: var(--input-bg); border: 1px solid var(--border-card);
  border-radius: 8px; padding: 5px 10px; font-size: 12px; color: var(--text);
  outline: none; width: 180px; flex-shrink: 0;
}
.search-input:focus { border-color: rgba(10,132,255,.5); }
.btn-group { display: flex; gap: 4px; flex-wrap: wrap; }
.filter-btn {
  background: var(--bg-card); border: 1px solid var(--border-card);
  border-radius: 7px; padding: 4px 9px; cursor: pointer; font-size: 11px;
  color: var(--text-2); transition: all .15s; white-space: nowrap;
}
.filter-btn:hover { color: var(--text); }
.filter-btn.active { border-color: rgba(10,132,255,.4); color: #0a84ff; background: rgba(10,132,255,.08); }
.spacer { flex: 1; }
.count { font-size: 12px; color: var(--text-2); font-variant-numeric: tabular-nums; white-space: nowrap; }

.table-wrap { flex: 1; overflow-y: auto; background: var(--bg-table); padding: 0 18px 14px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead { position: sticky; top: 0; z-index: 1; background: var(--bg-table); }
thead tr { border-bottom: 1px solid var(--border); }
th { padding: 10px 10px 8px; text-align: left; font-size: 10px; font-weight: 600; color: var(--text-2); letter-spacing: .05em; text-transform: uppercase; white-space: nowrap; }
th:last-child, td:last-child { text-align: right; }
tbody tr { border-bottom: 1px solid var(--border); cursor: pointer; transition: background .1s; }
tbody tr:hover { background: var(--bg-row-hover); }
tbody tr:last-child { border-bottom: none; }
td { padding: 9px 10px; color: var(--text); vertical-align: middle; }

.name-row { display: flex; align-items: center; gap: 5px; }
.sn { font-weight: 600; font-size: 13px; }
.sc { font-size: 10px; color: var(--text-2); margin-top: 2px; font-family: "SF Mono", monospace; }

/* 板块标签 */
.board-tag {
  display: inline-block; padding: 1px 5px; border-radius: 4px;
  font-size: 10px; font-weight: 600; line-height: 1.6; white-space: nowrap;
}
.board-kc { background: rgba(90,200,250,.18); color: #5ac8fa; border: 1px solid rgba(90,200,250,.3); }
.board-cy { background: rgba(255,159,10,.15); color: #ff9f0a; border: 1px solid rgba(255,159,10,.28); }
.board-bj { background: rgba(191,90,242,.15); color: #bf5af2; border: 1px solid rgba(191,90,242,.28); }

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
.tag-b { background: rgba(52,199,89,.14);  color: #34c759; }
.tag-p { background: rgba(255,69,58,.14);  color: #ff6961; }
.tag-s { background: rgba(90,200,250,.14); color: #5ac8fa; }
.tag-t { background: rgba(255,214,10,.18); color: #b8860b; }
.empty { text-align: center; padding: 40px; color: var(--text-2); }
</style>
