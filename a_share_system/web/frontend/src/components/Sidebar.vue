<script setup>
const props = defineProps({
  indices: Array,
  sentiment: Object,
  sectors: Array,
})

function pctClass(v, threshold = 0.05) {
  return v > threshold ? 'up' : v < -threshold ? 'dn' : 'flat'
}
function arrow(v, threshold = 0.05) {
  return v > threshold ? '▲' : v < -threshold ? '▼' : '▸'
}
function fmtSector(shown) {
  return [...shown.slice(0, 5), ...shown.slice(-3)].slice(0, 8)
}
function sectorCls(p) {
  return p >= 2 ? 'sc-us' : p >= 0 ? 'sc-um' : p >= -2 ? 'sc-dm' : 'sc-ds'
}
</script>

<template>
  <aside class="sidebar">
    <section>
      <div class="sec-lbl">大盘指数</div>
      <div v-for="idx in indices" :key="idx.code" class="idx-card">
        <span class="idx-name">{{ idx.name }}</span>
        <div style="text-align:right">
          <div class="idx-price" :class="pctClass(idx.pct_chg)">{{ idx.close.toFixed(2) }}</div>
          <div class="idx-chg" :class="pctClass(idx.pct_chg)">{{ arrow(idx.pct_chg) }} {{ idx.pct_chg.toFixed(3) }}%</div>
        </div>
      </div>
    </section>

    <section>
      <div class="sec-lbl">市场情绪</div>
      <div class="sentiment-row">
        <div class="s-chip"><div class="s-val up">{{ sentiment.up }}</div><div class="s-lbl">上涨</div></div>
        <div class="s-chip"><div class="s-val dn">{{ sentiment.down }}</div><div class="s-lbl">下跌</div></div>
        <div class="s-chip"><div class="s-val" style="color:#ff9f0a">{{ sentiment.limit_up }}</div><div class="s-lbl">涨停</div></div>
        <div class="s-chip"><div class="s-val dn">{{ sentiment.limit_down }}</div><div class="s-lbl">跌停</div></div>
        <div class="s-chip"><div class="s-val" style="color:#bf5af2">{{ sentiment.max_boards }}</div><div class="s-lbl">连板高</div></div>
        <div class="s-chip"><div class="s-val" style="color:#0a84ff">{{ sentiment.resonance_count }}</div><div class="s-lbl">共振</div></div>
      </div>
    </section>

    <section>
      <div class="sec-lbl">板块热力</div>
      <div class="sector-grid">
        <div v-for="s in fmtSector(sectors)" :key="s.name" class="sc-cell" :class="sectorCls(s.pct_chg)">
          <span class="sc-name">{{ s.name }}</span>
          <span class="sc-pct" :class="s.pct_chg >= 0 ? 'up' : 'dn'">{{ s.pct_chg >= 0 ? '+' : '' }}{{ s.pct_chg.toFixed(1) }}%</span>
        </div>
      </div>
    </section>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 240px; flex-shrink: 0; background: var(--bg-sidebar);
  border-right: 1px solid var(--border); padding: 18px 14px;
  display: flex; flex-direction: column; gap: 18px; overflow-y: auto;
}
.sec-lbl { font-size: 10px; font-weight: 600; color: var(--text-2); letter-spacing: .08em; text-transform: uppercase; margin-bottom: 8px; }
.idx-card {
  background: var(--bg-card); border: 1px solid var(--border-card);
  border-radius: 10px; padding: 10px 12px;
  display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;
}
.idx-name { font-size: 12px; color: var(--text-2); }
.idx-price { font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; }
.idx-chg { font-size: 11px; font-variant-numeric: tabular-nums; margin-top: 2px; }
.up { color: var(--up); } .dn { color: var(--dn); } .flat { color: var(--text-2); }
.sentiment-row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 5px; }
.s-chip { background: var(--bg-card); border: 1px solid var(--border-card); border-radius: 8px; padding: 7px 4px; text-align: center; }
.s-val { font-size: 16px; font-weight: 700; font-variant-numeric: tabular-nums; }
.s-lbl { font-size: 9px; color: var(--text-2); margin-top: 2px; }
.sector-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 5px; }
.sc-cell { border-radius: 7px; padding: 6px 8px; font-size: 10px; display: flex; justify-content: space-between; align-items: center; }
.sc-us { background: rgba(48,209,88,.15); border: 1px solid rgba(48,209,88,.22); }
.sc-um { background: rgba(48,209,88,.07); border: 1px solid rgba(48,209,88,.12); }
.sc-dm { background: rgba(255,69,58,.07); border: 1px solid rgba(255,69,58,.12); }
.sc-ds { background: rgba(255,69,58,.15); border: 1px solid rgba(255,69,58,.22); }
.sc-name { color: var(--s-name-col); }
.sc-pct { font-weight: 600; font-variant-numeric: tabular-nums; }
</style>
