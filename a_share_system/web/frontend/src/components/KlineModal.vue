<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'

const props = defineProps({ tsCode: String, name: String })
const emit = defineEmits(['close'])

const klineData = ref([])
const days = ref(60)
const tip = ref('')
const chartWrap = ref(null)
const cvBase = ref(null)
const cvCross = ref(null)

async function load() {
  tip.value = '加载中...'
  const data = await fetch(`/api/kline/${props.tsCode}?days=${days.value}`).then(r => r.json())
  klineData.value = data
  await nextTick()
  requestAnimationFrame(() => requestAnimationFrame(draw))
}

function setPeriod(d) {
  days.value = d
  load()
}

function draw() {
  const wrap = chartWrap.value
  if (!wrap) return
  const W = wrap.clientWidth, H = wrap.clientHeight
  if (!W || !H) { requestAnimationFrame(draw); return }

  const dpr = window.devicePixelRatio || 1
  for (const cv of [cvBase.value, cvCross.value]) {
    cv.width = W * dpr; cv.height = H * dpr
    cv.style.width = W + 'px'; cv.style.height = H + 'px'
    cv.getContext('2d').scale(dpr, dpr)
  }

  const data = klineData.value
  if (!data.length) return

  const isDark = document.documentElement.getAttribute('data-theme') === 'dark'
    || (document.documentElement.getAttribute('data-theme') === 'auto' && window.matchMedia('(prefers-color-scheme:dark)').matches)

  const PAD = { top: 24, right: 60, bottom: 56, left: 8 }
  const VOL_H = Math.floor(H * 0.2)
  const priceH = H - PAD.top - PAD.bottom - VOL_H - 8
  const chartW = W - PAD.left - PAD.right

  const maxP = Math.max(...data.map(d => d.high))
  const minP = Math.min(...data.map(d => d.low))
  const range = maxP - minP || 1
  const pad = range * 0.06
  const pHigh = maxP + pad, pLow = minP - pad
  const maxVol = Math.max(...data.map(d => d.vol)) || 1

  const cs = getComputedStyle(document.documentElement)
  const C = {
    up: cs.getPropertyValue('--up').trim() || '#30d158',
    dn: cs.getPropertyValue('--dn').trim() || '#ff453a',
    grid: isDark ? 'rgba(255,255,255,.06)' : 'rgba(0,0,0,.06)',
    text: isDark ? '#636366' : '#8e8e93',
    bg: isDark ? '#1c1c1e' : '#ffffff',
  }

  const toX = i => PAD.left + chartW * (i + 0.5) / data.length
  const toY = p => PAD.top + priceH * (1 - (p - pLow) / (pHigh - pLow))
  const toVolY = v => H - PAD.bottom - VOL_H * (v / maxVol)

  const ctx = cvBase.value.getContext('2d')
  ctx.clearRect(0, 0, W, H)
  ctx.fillStyle = C.bg
  ctx.fillRect(0, 0, W, H)

  ctx.font = '10px -apple-system,sans-serif'
  ctx.fillStyle = C.text
  ctx.textAlign = 'right'
  for (let i = 0; i <= 4; i++) {
    const p = pLow + (pHigh - pLow) * i / 4
    const y = toY(p)
    ctx.strokeStyle = C.grid; ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(PAD.left, y); ctx.lineTo(W - PAD.right, y); ctx.stroke()
    ctx.fillText(p.toFixed(2), W - 4, y + 3.5)
  }

  const step = Math.max(1, Math.floor(data.length / 6))
  for (let i = 0; i < data.length; i += step) {
    const x = toX(i)
    ctx.strokeStyle = C.grid; ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(x, PAD.top); ctx.lineTo(x, H - PAD.bottom); ctx.stroke()
    const ds = String(data[i].date)
    ctx.fillStyle = C.text; ctx.textAlign = 'center'
    ctx.fillText(`${ds.slice(4, 6)}/${ds.slice(6)}`, x, H - PAD.bottom + 14)
  }

  const cw = Math.max(1, Math.floor(chartW / data.length * 0.7))
  data.forEach((d, i) => {
    const x = toX(i)
    const isUp = d.close >= d.open
    const col = isUp ? C.up : C.dn
    ctx.strokeStyle = col; ctx.fillStyle = col
    ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(x, toY(d.high)); ctx.lineTo(x, toY(d.low)); ctx.stroke()
    const yO = toY(d.open), yC = toY(d.close)
    const rectY = Math.min(yO, yC), rectH = Math.max(1, Math.abs(yO - yC))
    if (isUp) ctx.strokeRect(x - cw / 2, rectY, cw, rectH)
    else ctx.fillRect(x - cw / 2, rectY, cw, rectH)
    ctx.fillStyle = isUp ? 'rgba(48,209,88,.5)' : 'rgba(255,69,58,.5)'
    ctx.fillRect(x - cw / 2, toVolY(d.vol), cw, H - PAD.bottom - toVolY(d.vol))
  })

  ctx.strokeStyle = isDark ? 'rgba(255,255,255,.08)' : 'rgba(0,0,0,.08)'
  ctx.lineWidth = 1
  ctx.beginPath(); ctx.moveTo(PAD.left, H - PAD.bottom - VOL_H); ctx.lineTo(W - PAD.right, H - PAD.bottom - VOL_H); ctx.stroke()

  // crosshair
  cvCross.value.onmousemove = e => drawCross(e, data, W, H, PAD, priceH, pHigh, pLow, maxVol, isDark, toX, toY, chartW)
  cvCross.value.onmouseleave = () => { cvCross.value.getContext('2d').clearRect(0, 0, W * dpr, H * dpr); tip.value = '' }
  tip.value = ''
}

function drawCross(e, data, W, H, PAD, priceH, pHigh, pLow, maxVol, isDark, toX, toY, chartW) {
  const rect = e.target.getBoundingClientRect()
  const mx = e.clientX - rect.left, my = e.clientY - rect.top
  const idx = Math.round((mx - PAD.left) / chartW * data.length - 0.5)
  if (idx < 0 || idx >= data.length) return
  const d = data[idx]
  const x = toX(idx)
  const dpr = window.devicePixelRatio || 1
  const ctx = cvCross.value.getContext('2d')
  ctx.clearRect(0, 0, W * dpr, H * dpr)
  const lineCol = isDark ? 'rgba(255,255,255,.3)' : 'rgba(0,0,0,.25)'
  ctx.strokeStyle = lineCol; ctx.lineWidth = 1; ctx.setLineDash([3, 3])
  ctx.beginPath(); ctx.moveTo(x, PAD.top); ctx.lineTo(x, H - PAD.bottom); ctx.stroke()
  if (my > PAD.top && my < H - PAD.bottom) {
    ctx.beginPath(); ctx.moveTo(PAD.left, my); ctx.lineTo(W - PAD.right, my); ctx.stroke()
  }
  ctx.setLineDash([])
  const price = pLow + (pHigh - pLow) * (1 - (my - PAD.top) / priceH)
  if (my > PAD.top && my < PAD.top + priceH) {
    ctx.fillStyle = isDark ? '#3a3a3c' : '#e5e5ea'
    ctx.fillRect(W - PAD.right, my - 9, PAD.right - 2, 18)
    ctx.fillStyle = isDark ? '#f5f5f7' : '#1d1d1f'
    ctx.font = '10px -apple-system,sans-serif'; ctx.textAlign = 'right'
    ctx.fillText(price.toFixed(2), W - 4, my + 3.5)
  }
  const cs = getComputedStyle(document.documentElement)
  const up = cs.getPropertyValue('--up').trim() || '#30d158'
  const dn = cs.getPropertyValue('--dn').trim() || '#ff453a'
  const ds = String(d.date)
  const fmt = v => v >= 1e8 ? `${(v / 1e8).toFixed(1)}亿` : v >= 1e4 ? `${(v / 1e4).toFixed(0)}万` : String(v)
  const sign = d.pct_chg >= 0 ? '+' : ''
  tip.value = `${ds.slice(0,4)}-${ds.slice(4,6)}-${ds.slice(6)}  开 ${d.open.toFixed(2)}  高 ${d.high.toFixed(2)}  低 ${d.low.toFixed(2)}  收 ${d.close.toFixed(2)}  ${sign}${d.pct_chg.toFixed(2)}%  量 ${fmt(d.vol)}`
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
        <button v-for="d in [60, 120, 250]" :key="d"
          class="period-btn" :class="{ active: days === d }"
          @click="setPeriod(d)">{{ d }}日</button>
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
  border-radius: 16px; width: min(900px, 94vw); height: min(600px, 90vh);
  display: flex; flex-direction: column; overflow: hidden;
  box-shadow: 0 24px 80px rgba(0,0,0,.4);
}
.modal-header {
  padding: 16px 20px; display: flex; justify-content: space-between;
  align-items: flex-start; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.modal-title { font-size: 17px; font-weight: 600; }
.modal-sub { font-size: 12px; color: var(--text-2); margin-top: 3px; }
.close-btn {
  background: var(--bg-card); border: 1px solid var(--border-card);
  border-radius: 50%; width: 28px; height: 28px; cursor: pointer;
  font-size: 14px; color: var(--text-2); display: flex; align-items: center;
  justify-content: center; transition: all .15s;
}
.close-btn:hover { color: var(--text); }
.modal-toolbar {
  padding: 10px 20px; display: flex; gap: 8px; align-items: center;
  border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.period-btn {
  background: var(--bg-card); border: 1px solid var(--border-card);
  border-radius: 7px; padding: 4px 12px; cursor: pointer;
  font-size: 12px; color: var(--text-2); transition: all .15s;
}
.period-btn.active { background: rgba(10,132,255,.15); border-color: rgba(10,132,255,.4); color: #0a84ff; }
.tip { margin-left: auto; font-size: 11px; color: var(--text-2); font-variant-numeric: tabular-nums; }
.chart-wrap { position: relative; flex: 1; min-height: 0; padding: 16px 20px 12px; }
.canvas { position: absolute; top: 0; left: 0; width: 100%; height: 100%; }
.cross { pointer-events: auto; }
</style>
