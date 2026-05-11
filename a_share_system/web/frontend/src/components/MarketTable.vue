<script setup>
import { ref, computed } from 'vue'

const props = defineProps({ stocks: Array })
const emit = defineEmits(['open-kline'])

const search = ref('')
const filter = ref('ALL')
const board  = ref('ALL')
const sort   = ref({ col: 'pct_chg', dir: -1 })

const BOARDS = [
  { id: 'ALL',  label: '全板' },
  { id: 'MAIN', label: '主板' },
  { id: 'GEM',  label: '创业板' },
  { id: 'STAR', label: '科创板' },
  { id: 'BSE',  label: '北交所' },
]
const DIR_FILTERS = [
  { id: 'ALL',   label: '全部' },
  { id: 'UP',    label: '上涨' },
  { id: 'DOWN',  label: '下跌' },
  { id: 'LIMIT', label: '涨停' },
]

function getBoard(code) {
  if (code.endsWith('.BJ'))                                              return { id: 'BSE',  label: '北交', cls: 'bj' }
  if (code.endsWith('.SH') && code.startsWith('688'))                   return { id: 'STAR', label: '科创', cls: 'kc' }
  if (code.endsWith('.SZ') && (code.startsWith('300') || code.startsWith('301'))) return { id: 'GEM',  label: '创业', cls: 'cy' }
  return null
}

function setSort(col) {
  if (sort.value.col === col) sort.value.dir *= -1
  else { sort.value.col = col; sort.value.dir = -1 }
}
function sortIcon(col) {
  if (sort.value.col !== col) return ''
  return sort.value.dir === 1 ? ' ↑' : ' ↓'
}

const filtered = computed(() => {
  let rows = [...props.stocks]
  const q = search.value.trim().toLowerCase()
  if (q) rows = rows.filter(r => r.name.includes(q) || r.ts_code.toLowerCase().includes(q))

  if (filter.value === 'UP')    rows = rows.filter(r => r.pct_chg > 0)
  if (filter.value === 'DOWN')  rows = rows.filter(r => r.pct_chg < 0)
  if (filter.value === 'LIMIT') rows = rows.filter(r => r.pct_chg >= 9.5)

  if (board.value !== 'ALL') {
    if (board.value === 'MAIN') {
      rows = rows.filter(r => {
        const b = getBoard(r.ts_code)
        return !b && !r.ts_code.endsWith('.BJ')
      })
    } else {
      rows = rows.filter(r => getBoard(r.ts_code)?.id === board.value)
    }
  }

  const { col, dir } = sort.value
  rows.sort((a, b) => (a[col] > b[col] ? 1 : -1) * dir)
  return rows
})

function fmtAmt(v) {
  return v >= 1e8 ? `${(v / 1e8).toFixed(1)}亿` : v >= 1e4 ? `${(v / 1e4).toFixed(0)}万` : String(v)
}
function pctCls(v) { return v > 0 ? 'up' : v < 0 ? 'dn' : 'flat' }
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

      <div class="sep"></div>

      <!-- 涨跌筛选 -->
      <div class="btn-group">
        <button v-for="f in DIR_FILTERS" :key="f.id"
          class="filter-btn" :class="{ active: filter === f.id }"
          @click="filter = f.id">{{ f.label }}</button>
      </div>

      <span class="spacer"></span>
      <span class="count">{{ filtered.length }} 只</span>
    </div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th @click="setSort('name')">股票{{ sortIcon('name') }}</th>
            <th @click="setSort('pct_chg')">涨幅{{ sortIcon('pct_chg') }}</th>
            <th @click="setSort('close')">收盘{{ sortIcon('close') }}</th>
            <th @click="setSort('amount')">成交额{{ sortIcon('amount') }}</th>
            <th>行业</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="!filtered.length"><td colspan="6" class="empty">暂无数据</td></tr>
          <tr v-for="(r, i) in filtered" :key="r.ts_code" @click="emit('open-kline', r.ts_code, r.name)">
            <td class="num">{{ i + 1 }}</td>
            <td>
              <div class="name-row">
                <span class="sn">{{ r.name }}</span>
                <span v-if="getBoard(r.ts_code)" class="board-tag"
                  :class="`board-${getBoard(r.ts_code).cls}`">{{ getBoard(r.ts_code).label }}</span>
              </div>
              <div class="sc">{{ r.ts_code }}</div>
            </td>
            <td :class="pctCls(r.pct_chg)" class="mono fw">{{ r.pct_chg > 0 ? '+' : '' }}{{ r.pct_chg.toFixed(2) }}%</td>
            <td class="mono">{{ r.close.toFixed(2) }}</td>
            <td class="mono muted">{{ fmtAmt(r.amount) }}</td>
            <td class="muted small">{{ r.industry || '—' }}</td>
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
.sep { width: 1px; height: 18px; background: var(--border); flex-shrink: 0; margin: 0 2px; }
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
th {
  padding: 10px 10px 8px; text-align: left; font-size: 10px; font-weight: 600;
  color: var(--text-2); letter-spacing: .05em; text-transform: uppercase;
  cursor: pointer; user-select: none; white-space: nowrap;
}
th:hover { color: var(--text); }
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

.up { color: var(--up); } .dn { color: var(--dn); } .flat { color: var(--text-2); }
.mono { font-variant-numeric: tabular-nums; }
.fw { font-weight: 600; }
.muted { color: var(--text-2); }
.small { font-size: 12px; }
.num { color: var(--text-2); font-size: 12px; }
.empty { text-align: center; padding: 40px; color: var(--text-2); }
</style>
