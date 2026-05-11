import { ref } from 'vue'

export function useMarketData() {
  const date = ref(null)
  const indices = ref([])
  const sentiment = ref({})
  const sectors = ref([])
  const signals = ref([])
  const stocks = ref([])
  const loading = ref(true)

  async function load() {
    loading.value = true
    const dates = await fetch('/api/dates').then(r => r.json())
    date.value = dates[0]
    const d = dates[0]
    const [market, sec, sigs, stks] = await Promise.all([
      fetch(`/api/market/${d}`).then(r => r.json()),
      fetch(`/api/sectors/${d}`).then(r => r.json()),
      fetch(`/api/signals/${d}`).then(r => r.json()),
      fetch(`/api/stocks/${d}`).then(r => r.json()),
    ])
    indices.value = market.indices
    sentiment.value = market.sentiment
    sectors.value = sec
    signals.value = sigs
    stocks.value = stks
    loading.value = false
  }

  return { date, indices, sentiment, sectors, signals, stocks, loading, load }
}
