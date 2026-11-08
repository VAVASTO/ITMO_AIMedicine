export const staticMode = import.meta.env.VITE_STATIC_DEMO === '1'
let archivePromise
async function archive() {
  if (!archivePromise) archivePromise = fetch('./static-demo.json').then(r => {
    if (!r.ok) throw Error('Не удалось загрузить подготовленные результаты.')
    return r.json()
  })
  return archivePromise
}
export async function request(path, body) {
  if (staticMode) {
    const data = await archive()
    if (path === '/api/multi/catalog') return data.catalog
    if (path === '/api/multi/search') throw Error('В статическом демо доступны ссылки на документы. Полнотекстовый поиск работает в локальной версии.')
    if (path !== '/api/multi/evaluate') throw Error('Этот режим доступен только локально.')
    const c = data.catalog.cases.find(c => c.id === body.case_id)
    const index = c?.review_times.indexOf(body.review_at)
    const extra = body.additions || []
    if (extra.length > 1) throw Error('В статическом демо можно добавить одну подготовленную запись.')
    const key = `${body.case_id}|${index}|${body.assume_therapy ? 1 : 0}|${extra[0]?.kind || 'none'}`
    if (!data.views[key]) throw Error('Для выбранного сочетания результат не подготовлен.')
    return data.views[key]
  }
  const response = await fetch(path, body ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)} : undefined)
  const data = await response.json()
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Проверьте параметры запроса.')
  return data
}
