// Display formatters for energy / currency / percentage values.

const eur0 = new Intl.NumberFormat('en-IE', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 0,
})

const eur2 = new Intl.NumberFormat('en-IE', {
  style: 'currency',
  currency: 'EUR',
  maximumFractionDigits: 2,
})

const num1 = new Intl.NumberFormat('en-IE', { maximumFractionDigits: 1 })
const num2 = new Intl.NumberFormat('en-IE', { maximumFractionDigits: 2 })

export function fmtEur(value: number): string {
  return eur0.format(value)
}

export function fmtEurMillion(value: number): string {
  return `${num2.format(value / 1_000_000)}M €`
}

export function fmtEurPerMwh(value: number): string {
  return `${eur2.format(value)}/MWh`
}

export function fmtMwh(value: number): string {
  return `${num1.format(value)} MWh`
}

export function fmtGwh(value: number): string {
  return `${num1.format(value / 1000)} GWh`
}

export function fmtPercent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`
}

export function fmtNumber(value: number, digits = 1): string {
  return new Intl.NumberFormat('en-IE', {
    maximumFractionDigits: digits,
  }).format(value)
}
