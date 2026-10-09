type Criterion = { criterion_id?: number; content?: string; weight?: number; score?: number; max_score?: number; reason?: string; comment?: string }
type Module = { max_score?: number; score_percent?: number; criteria_items?: Criterion[]; criteria_results?: Criterion[] }

export function aiResultRows(module: Module, assignmentMax: number) {
  const results = module.criteria_results ?? []
  const criteria = module.criteria_items?.length ? module.criteria_items : results
  const totalWeight = criteria.reduce((sum, item) => sum + Number(item.weight ?? 0), 0)
  const maximum = Number(module.max_score ?? assignmentMax * Number(module.score_percent ?? 0) / 100)
  const cents = Math.round(maximum * 100)
  const exact = criteria.map(item => totalWeight > 0 ? cents * Number(item.weight ?? 0) / totalWeight : 0)
  const caps = exact.map(Math.floor)
  const order = exact.map((value, index) => ({ index, remainder: value - caps[index]! })).sort((a, b) => b.remainder - a.remainder)
  const remaining = totalWeight > 0 ? cents - caps.reduce((sum, value) => sum + value, 0) : 0
  order.slice(0, remaining).forEach(item => { caps[item.index]! += 1 })
  return results.map((result, index) => {
    const matched = result.criterion_id != null ? result.criterion_id - 1 : criteria.findIndex(item => item.content === result.content)
    const position = matched >= 0 && matched < criteria.length ? matched : index
    const weight = Number(result.weight ?? criteria[position]?.weight ?? 0)
    return { ...result, max_score: result.max_score ?? (caps[position] != null ? caps[position]! / 100 : undefined),
      weight_percent: totalWeight > 0 ? Math.round(weight / totalWeight * 10000) / 100 : 0 }
  })
}
