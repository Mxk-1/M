<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({ tsCode: String, name: String })
const emit = defineEmits(['close'])

const klineData = ref([])
const days = ref(250)
const tip = ref('')
const activeQ = ref(0)   // 0=全部, 1~4=季度
const chartWrap = ref(null)
const cvBase = ref(null)
const cvCross = ref(null)

// ── 工具函数 ────────────────────────────────────────────────
function getQ(dateInt) {
  return Math.ceil(parseInt(String(dateInt).slice(4, 6)) / 3)
}
function isDark() {
  const t = document.documentElement.getAttribute('data-theme')
  return t === 'dark' || (t === 'auto' && window.matchMedia('(prefers-color-scheme:dark)').matches)
}

// ── 数据加载 ────────────────────────────────────────────────
async function load() {
  tip.value = '加载中...'
  const data = await fetch(`/api/kline/${props.tsCode}?days=${days.value}`).then(r => r.json())
  klineData.value = data
  await nextTick()
  requestAnimationFrame(() => requestAnimationFrame(draw))
}

function setPeriod(d) { days.value = d; load() }
function setQ(q) { activeQ.value = q; draw() }

// ── 计算季度区间（连续的相同季度段合并为一个区间）─────────
function calcQuarterBands(data) {
  // 返回 [{q, startIdx, endIdx, year}, ...]，每个自然季度一段
  if (!data.length) return []
  const bands = []
  let cur = { q: getQ(data[0].date), year: parseInt(String(data[0].date).slice(0, 4)), startIdx: 0 }
  for (let i = 1; i < data.length; i++) {
    const q = getQ(data[i].date)
    const y = parseInt(String(data[i].date).slice(0, 4))
    if (q !== cur.q || y !== cur.year) {
      bands.push({ ...cur, endIdx: i - 1 })
      cur = { q, year: y, startIdx: i }
    }
  }
  bands.push({ ...cur, endIdx: data.length - 1 })
  return bands
}

// ── 主绘制 ──────────────────────────────────────────────────
function draw() {
  const wrap = chartWrap.value
  if (!wrap) return
  const W = wrap.clientWidth, H = wrap.clientHeight
  if (!W || !H) { requestAnimationFrame(draw); return }

  const dark = isDark()
  const dpr = window.devicePixelRatio || 1

  for (const cv of [cvBase.value, cvCross.value]) {
    cv.width = W * dpr; cv.height = H * dpr
    cv.style.width = W + 'px'; cv.style.height = H + 'px'
    cv.getContext('2d').scale(dpr, dpr)
  }

  const data = klineData.value
  if (!data.length) return

  // 布局
  const PAD = { top: 28, right: 64, bottom: 64, left: 8 }
  const VOL_H = Math.floor(H * 0.18)
  const XAXIS_H = 40   // X 轴区域（双层：季度 + 年份）
  const priceH = H - PAD.top - PAD.bottom - VOL_H - 8
  const chartW = W - PAD.left - PAD.right

  // 价格/量范围
  const maxP = Math.max(...data.map(d => d.high))
  const minP = Math.min(...data.map(d => d.low))
  const rangeP = maxP - minP || 1
  const pHigh = maxP + rangeP * 0.06
  const pLow  = minP - rangeP * 0.06
  const maxVol = Math.max(...data.map(d => d.vol)) || 1

  // 颜色系统
  const cs = getComputedStyle(document.documentElement)
  const C = {
    up:      cs.getPropertyValue('--up').trim() || '#30d158',
    dn:      cs.getPropertyValue('--dn').trim() || '#ff453a',
    grid:    dark ? 'rgba(255,255,255,.05)' : 'rgba(0,0,0,.05)',
    gridQ:   dark ? 'rgba(255,255,255,.12)' : 'rgba(0,0,0,.12)',  // 季度分隔线
    gridY:   dark ? 'rgba(255,255,255,.22)' : 'rgba(0,0,0,.18)',  // 年份分隔线
    text:    dark ? '#636366' : '#8e8e93',
    textY:   dark ? '#aeaeb2' : '#6e6e73',  // 年份标签稍亮
    bg:      dark ? '#1c1c1e' : '#ffffff',
    hlBand:  dark ? 'rgba(10,132,255,.07)' : 'rgba(10,132,255,.06)',  // 高亮背景带
    dimAlpha: 0.18,  // 非选中蜡烛 alpha
  }

  // 坐标变换
  const toX    = i  => PAD.left + chartW * (i + 0.5) / data.length
  const toY    = p  => PAD.top + priceH * (1 - (p - pLow) / (pHigh - pLow))
  const toVolY = v  => H - PAD.bottom - VOL_H * (v / maxVol)

  const ctx = cvBase.value.getContext('2d')
  ctx.clearRect(0, 0, W, H)
  ctx.fillStyle = C.bg
  ctx.fillRect(0, 0, W, H)

  // 季度区间
  const bands = calcQuarterBands(data)
  const q = activeQ.value

  // ── 高亮背景带（在网格之前画，不遮盖网格）────────────────
  if (q !== 0) {
    for (const b of bands) {
      if (b.q !== q) continue
      const x1 = PAD.left + chartW * b.startIdx / data.length
      const x2 = PAD.left + chartW * (b.endIdx + 1) / data.length
      ctx.fillStyle = C.hlBand
      ctx.fillRect(x1, PAD.top, x2 - x1, priceH + 8 + VOL_H)
    }
  }

  // ── 水平网格 + 价格标签 ───────────────────────────────────
  ctx.font = '10px -apple-system,sans-serif'
  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const p = pLow + (pHigh - pLow) * i / 4
    const y = toY(p)
    ctx.strokeStyle = C.grid; ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(W - PAD.right, y); ctx.stroke()
    ctx.fillStyle = C.text
    ctx.fillText(p.toFixed(2), W - 4, y + 3.5)
  }

  // ── 垂直分隔线 + 双层 X 轴标签 ───────────────────────────
  // 收集年份和季度边界
  const yearBounds = []  // { year, startIdx }
  const seenYears = new Set()

  for (const b of bands) {
    if (!seenYears.has(b.year)) {
      seenYears.add(b.year)
      yearBounds.push({ year: b.year, startIdx: b.startIdx })
    }

    const x = PAD.left + chartW * b.startIdx / data.length

    if (b.startIdx === 0) {
      // 第一根不画线，只画标签
    } else {
      // 判断是年边界还是季度边界
      const isYearBound = b.q === 1   // Q1 开头 = 新年
      ctx.strokeStyle = isYearBound ? C.gridY : C.gridQ
      ctx.lineWidth = isYearBound ? 1.5 : 1
      ctx.setLineDash(isYearBound ? [] : [3, 3])
      ctx.beginPath(); ctx.moveTo(x, PAD.top); ctx.lineTo(x, H - PAD.bottom); ctx.stroke()
      ctx.setLineDash([])
    }

    // 季度标签（第一层，靠近图表底部）
    const bandMidX = PAD.left + chartW * (b.startIdx + b.endIdx + 1) / 2 / data.length
    const qlabel = `Q${b.q}`
    const isActive = q === 0 || b.q === q
    ctx.fillStyle = isActive ? (dark ? '#c7d2fe' : '#0a84ff') : C.text
    ctx.font = isActive ? 'bold 10px -apple-system,sans-serif' : '10px -apple-system,sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(qlabel, bandMidX, H - PAD.bottom + 14)
  }

  // 年份标签（第二层，更下方）
  ctx.font = '11px -apple-system,sans-serif'
  ctx.fillStyle = C.textY
  ctx.textAlign = 'center'
  for (const yb of yearBounds) {
    // 找该年所有 band，取中点
    const yearBands = bands.filter(b => b.year === yb.year)
    const firstIdx = yearBands[0].startIdx
    const lastIdx  = yearBands[yearBands.length - 1].endIdx
    const midX = PAD.left + chartW * (firstIdx + lastIdx + 1) / 2 / data.length
    ctx.fillText(String(yb.year), midX, H - PAD.bottom + 30)
  }

  // ── 蜡烛图 ────────────────────────────────────────────────
  const cw = Math.max(1, Math.floor(chartW / data.length * 0.7))

  data.forEach((d, i) => {
    const dq = getQ(d.date)
    const active = q === 0 || dq === q
    const alpha = active ? 1 : C.dimAlpha

    const x = toX(i)
    const isUp = d.close >= d.open

    // 解析 RGB 颜色用于设置 alpha
    const col = isUp ? C.up : C.dn
    ctx.globalAlpha = alpha
    ctx.strokeStyle = col
    ctx.fillStyle = col
    ctx.lineWidth = 1

    // 影线
    ctx.beginPath(); ctx.moveTo(x, toY(d.high)); ctx.lineTo(x, toY(d.low)); ctx.stroke()

    // 实体
    const yO = toY(d.open), yC = toY(d.close)
    const rectY = Math.min(yO, yC), rectH = Math.max(1, Math.abs(yO - yC))
    if (isUp) ctx.strokeRect(x - cw / 2, rectY, cw, rectH)
    else      ctx.fillRect(x - cw / 2, rectY, cw, rectH)

    // 成交量
    ctx.fillStyle = isUp ? 'rgba(48,209,88,.5)' : 'rgba(255,69,58,.5)'
    ctx.fillRect(x - cw / 2, toVolY(d.vol), cw, H - PAD.bottom - toVolY(d.vol))

    ctx.globalAlpha = 1
  })

  // ── 量价分隔线 ────────────────────────────────────────────
  ctx.strokeStyle = dark ? 'rgba(255,255,255,.07)' : 'rgba(0,0,0,.07)'
  ctx.lineWidth = 1; ctx.setLineDash([])
  ctx.beginPath()
  ctx.moveTo(PAD.left, H - PAD.bottom - VOL_H)
  ctx.lineTo(W - PAD.right, H - PAD.bottom - VOL_H)
  ctx.stroke()

  // ── 绑定十字准线 ──────────────────────────────────────────
  const dpr2 = dpr  // 闭包
  cvCross.value.onmousemove = e => drawCross(e, data, W, H, PAD, priceH, pHigh, pLow, toX, toY, chartW, dark, dpr2)
  cvCross.value.onmouseleave = () => {
    cvCross.value.getContext('2d').clearRect(0, 0, W * dpr2, H * dpr2)
    tip.value = ''
  }
  tip.value = ''
}

// ── 十字准线 ────────────────────────────────────────────────
function drawCross(e, data, W, H, PAD, priceH, pHigh, pLow, toX, toY, chartW, dark, dpr) {
  const rect = e.target.getBoundingClientRect()
  const mx = e.clientX - rect.left, my = e.clientY - rect.top
  const idx = Math.max(0, Math.min(data.length - 1,
    Math.round((mx - PAD.left) / chartW * data.length - 0.5)))
  const d = data[idx]
  const x = toX(idx)

  const ctx = cvCross.value.getContext('2d')
  ctx.clearRect(0, 0, W * dpr, H * dpr)

  ctx.strokeStyle = dark ? 'rgba(255,255,255,.28)' : 'rgba(0,0,0,.22)'
  ctx.lineWidth = 1; ctx.setLineDash([3, 3])
  ctx.beginPath(); ctx.moveTo(x, PAD.top); ctx.lineTo(x, H - PAD.bottom); ctx.stroke()
  if (my > PAD.top && my < H - PAD.bottom) {
    ctx.beginPath(); ctx.moveTo(PAD.left, my); ctx.lineTo(W - PAD.right, my); ctx.stroke()
  }
  ctx.setLineDash([])

  // 右侧价格标签
  const price = pLow + (pHigh - pLow) * (1 - (my - PAD.top) / priceH)
  if (my > PAD.top && my < PAD.top + priceH) {
    ctx.fillStyle = dark ? '#3a3a3c' : '#e5e5ea'
    ctx.fillRect(W - PAD.right, my - 9, PAD.right - 2, 18)
    ctx.fillStyle = dark ? '#f5f5f7' : '#1d1d1f'
    ctx.font = '10px -apple-system,sans-serif'; ctx.textAlign = 'right'
    ctx.fillText(price.toFixed(2), W - 4, my + 3.5)
  }

  // Tooltip 文字
  const cs = getComputedStyle(document.documentElement)
  const up = cs.getPropertyValue('--up').trim() || '#30d158'
  const dn = cs.getPropertyValue('--dn').trim() || '#ff453a'
  const ds = String(d.date)
  const fmt = v => v >= 1e8 ? `${(v / 1e8).toFixed(1)}亿` : v >= 1e4 ? `${(v / 1e4).toFixed(0)}万` : String(v)
  const sign = d.pct_chg >= 0 ? '+' : ''
  const qLabel = `Q${getQ(d.date)}`
  tip.value = `${ds.slice(0,4)}-${ds.slice(4,6)}-${ds.slice(6)} ${qLabel}　开 ${d.open.toFixed(2)}  高 ${d.high.toFixed(2)}  低 ${d.low.toFixed(2)}  收 ${d.close.toFixed(2)}  ${sign}${d.pct_chg.toFixed(2)}%  量 ${fmt(d.vol)}`
}

function onKeydown(e) { if (e.key === 'Escape') emit('close') }
onMounted(() => { document.addEventListener('keydown', onKeydown); load() })
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <div class="overlay" @click.self="emit('close')">
    <div class="modal">
      <div class="modal-header">
        <div>
          <div class="modal-title">{{ name }}</div>
          <div class="modal-sub">{{ tsCode }}</div>
        </div>
        <button class="close-btn" @click="emit('close')">✕</button>
      </div>

      <div class="modal-toolbar">
        <!-- 时间范围 -->
        <div class="btn-group">
          <button v-for="d in [120, 250, 500]" :key="d"
            class="tool-btn" :class="{ active: days === d }"
            @click="setPeriod(d)">{{ d === 500 ? '全部' : d + '日' }}</button>
        </div>

        <div class="divider"></div>

        <!-- 季度高亮 -->
        <div class="btn-group">
          <button class="tool-btn" :class="{ active: activeQ === 0 }" @click="setQ(0)">全部</button>
          <button v-for="q in [1,2,3,4]" :key="q"
            class="tool-btn q-btn" :class="{ active: activeQ === q }"
            @click="setQ(q)">Q{{ q }}</button>
        </div>

        <span class="tip">{{ tip }}</span>
      </div>

      <div class="chart-wrap" ref="chartWrap">
        <canvas ref="cvBase" class="canvas"></canvas>
        <canvas ref="cvCross" class="canvas cross"></canvas>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 100;
  display: flex; align-items: center; justify-content: center;
  backdrop-filter: blur(4px);
}
.modal {
  background: var(--bg-sidebar); border: 1px solid var(--border);
  border-radius: 16px; width: min(960px, 96vw); height: min(640px, 92vh);
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 24px 80px rgba(0,0,0,.4);
}
.modal-header {
  padding: 14px 20px; display: flex; justify-content: space-between;
  align-items: center; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.modal-title { font-size: 16px; font-weight: 600; }
.modal-sub { font-size: 11px; color: var(--text-2); margin-top: 2px; }
.close-btn {
  background: var(--bg-card); border: 1px solid var(--border-card);
  border-radius: 50%; width: 26px; height: 26px; cursor: pointer;
  font-size: 13px; color: var(--text-2); display: flex; align-items: center;
  justify-content: center; transition: all .15s; flex-shrink: 0;
}
.close-btn:hover { color: var(--text); }
.modal-toolbar {
  padding: 8px 18px; display: flex; gap: 8px; align-items: center;
  border-bottom: 1px solid var(--border); flex-shrink: 0; flex-wrap: wrap;
}
.btn-group { display: flex; gap: 4px; }
.tool-btn {
  background: var(--bg-card); border: 1px solid var(--border-card);
  border-radius: 6px; padding: 3px 10px; cursor: pointer;
  font-size: 11px; color: var(--text-2); transition: all .15s; white-space: nowrap;
}
.tool-btn:hover { color: var(--text); }
.tool-btn.active {
  background: rgba(10,132,255,.14); border-color: rgba(10,132,255,.4);
  color: #0a84ff; font-weight: 500;
}
/* Q 按钮激活时每个季度用不同强调色 */
.q-btn.active:nth-of-type(1) { background: rgba(10,132,255,.14); border-color: rgba(10,132,255,.4); color: #0a84ff; }
.q-btn.active:nth-of-type(2) { background: rgba(48,209,88,.12);  border-color: rgba(48,209,88,.35);  color: #30d158; }
.q-btn.active:nth-of-type(3) { background: rgba(255,159,10,.12); border-color: rgba(255,159,10,.35); color: #ff9f0a; }
.q-btn.active:nth-of-type(4) { background: rgba(191,90,242,.12); border-color: rgba(191,90,242,.35); color: #bf5af2; }
.divider { width: 1px; height: 18px; background: var(--border); flex-shrink: 0; }
.tip { margin-left: auto; font-size: 11px; color: var(--text-2); font-variant-numeric: tabular-nums; min-height: 15px; }
.chart-wrap { position: relative; flex: 1; min-height: 0; padding: 12px 16px 8px; }
.canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
.cross { pointer-events: auto; }
</style>
