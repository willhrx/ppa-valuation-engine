import { useState, type CSSProperties } from 'react'

import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Slider } from '@/components/ui/slider'
import type { PPAConfig } from '@/lib/api'

interface ConfigPanelProps {
  initial: PPAConfig
  onApply: (config: PPAConfig, baseStrike: number) => void
  onReset: () => Promise<PPAConfig>
  baseStrike: number
  busy?: boolean
}

interface SliderRowProps {
  id: string
  label: string
  value: number
  min: number
  max: number
  step: number
  unit?: string
  digits?: number
  tone: string
  onChange: (v: number) => void
}

type ToneStyle = CSSProperties & {
  ['--primary']?: string
  ['--ring']?: string
}

function SliderRow({
  id,
  label,
  value,
  min,
  max,
  step,
  unit,
  digits = 2,
  tone,
  onChange,
}: SliderRowProps) {
  const toneStyle: ToneStyle = { '--primary': tone, '--ring': tone }
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <Label htmlFor={id} className="text-[11.5px] text-[color:var(--text-soft)]">
          {label}
        </Label>
        <span className="font-mono text-[11px] font-semibold tabular-nums">
          {value.toFixed(digits)}
          {unit ? (
            <span className="ml-0.5 font-normal text-muted-foreground">
              {unit}
            </span>
          ) : null}
        </span>
      </div>
      <div style={toneStyle}>
        <Slider
          id={id}
          min={min}
          max={max}
          step={step}
          value={[value]}
          onValueChange={(v) => onChange(v[0])}
        />
      </div>
    </div>
  )
}

interface SectionChipProps {
  color: string
  icon: string
  title: string
  count: string
}

function SectionChip({ color, icon, title, count }: SectionChipProps) {
  return (
    <div className="mb-2 flex items-center gap-2.5">
      <div
        className="flex h-[22px] w-[22px] items-center justify-center rounded-md text-xs font-bold text-white"
        style={{
          background: color,
          boxShadow: `0 1px 3px color-mix(in oklch, ${color} 30%, transparent)`,
        }}
      >
        {icon}
      </div>
      <span className="text-xs font-semibold">{title}</span>
      <span className="ml-auto font-mono text-[10px] text-muted-foreground">
        {count}
      </span>
    </div>
  )
}

export function ConfigPanel({
  initial,
  onApply,
  onReset,
  baseStrike: initialBaseStrike,
  busy,
}: ConfigPanelProps) {
  const [draft, setDraft] = useState<PPAConfig>(initial)
  const [baseStrike, setBaseStrike] = useState<number>(initialBaseStrike)

  const setSolar = (patch: Partial<PPAConfig['solar']>) =>
    setDraft((d) => ({ ...d, solar: { ...d.solar, ...patch } }))
  const setMarket = (patch: Partial<PPAConfig['market']>) =>
    setDraft((d) => ({ ...d, market: { ...d.market, ...patch } }))
  const setLoad = (patch: Partial<PPAConfig['load']>) =>
    setDraft((d) => ({ ...d, load: { ...d.load, ...patch } }))
  const setDeal = (patch: Partial<PPAConfig['deal']>) =>
    setDraft((d) => ({ ...d, deal: { ...d.deal, ...patch } }))

  const handleReset = async () => {
    const defaults = await onReset()
    setDraft(defaults)
    setBaseStrike(65.0)
  }

  const solar = 'var(--solar)'
  const price = 'var(--price)'
  const load = 'var(--load)'
  const text = 'var(--foreground)'
  const accent = 'var(--accent)'

  return (
    <Card size="sm" className="h-full">
      <CardContent className="space-y-5 overflow-y-auto pb-4">
        <div>
          <div className="text-[13px] font-semibold">Asset configuration</div>
          <div className="mt-0.5 text-[11px] text-muted-foreground">
            14 parameters · live preview on apply
          </div>
        </div>

        <section className="space-y-2.5">
          <SectionChip color={solar} icon="☀" title="Solar PV" count="6 params" />
          <div className="flex flex-col gap-2.5 pl-0.5">
            <SliderRow
              id="capacity_mw"
              label="Capacity"
              unit="MW"
              digits={0}
              min={10}
              max={500}
              step={5}
              tone={solar}
              value={draft.solar.capacity_mw}
              onChange={(v) => setSolar({ capacity_mw: v })}
            />
            <SliderRow
              id="performance_ratio"
              label="Performance ratio"
              min={0.7}
              max={0.92}
              step={0.01}
              tone={solar}
              value={draft.solar.performance_ratio}
              onChange={(v) => setSolar({ performance_ratio: v })}
            />
            <SliderRow
              id="degradation_rate"
              label="Degradation"
              unit="/yr"
              digits={3}
              min={0.001}
              max={0.01}
              step={0.001}
              tone={solar}
              value={draft.solar.degradation_rate}
              onChange={(v) => setSolar({ degradation_rate: v })}
            />
            <SliderRow
              id="cloud_factor_phi"
              label="Cloud persistence φ"
              min={0.7}
              max={0.97}
              step={0.01}
              tone={solar}
              value={draft.solar.cloud_factor_phi}
              onChange={(v) => setSolar({ cloud_factor_phi: v })}
            />
            <SliderRow
              id="tilt"
              label="Tilt"
              unit="°"
              digits={0}
              min={10}
              max={60}
              step={1}
              tone={solar}
              value={draft.solar.tilt_deg}
              onChange={(v) => setSolar({ tilt_deg: v })}
            />
            <SliderRow
              id="azimuth"
              label="Azimuth"
              unit="°"
              digits={0}
              min={135}
              max={225}
              step={5}
              tone={solar}
              value={draft.solar.azimuth_deg}
              onChange={(v) => setSolar({ azimuth_deg: v })}
            />
          </div>
        </section>

        <section className="space-y-2.5">
          <SectionChip color={price} icon="€" title="Market price" count="6 params" />
          <div className="flex flex-col gap-2.5 pl-0.5">
            <SliderRow
              id="base_price"
              label="Base price 2027"
              unit="€/MWh"
              digits={0}
              min={40}
              max={130}
              step={1}
              tone={price}
              value={draft.market.base_price}
              onChange={(v) => setMarket({ base_price: v })}
            />
            <SliderRow
              id="drift"
              label="Drift"
              unit="€/MWh/yr"
              digits={2}
              min={-5}
              max={1}
              step={0.25}
              tone={price}
              value={draft.market.drift}
              onChange={(v) => setMarket({ drift: v })}
            />
            <SliderRow
              id="ar1_sigma"
              label="AR(1) σ"
              unit="€/MWh"
              digits={1}
              min={2}
              max={20}
              step={0.5}
              tone={price}
              value={draft.market.ar1_sigma}
              onChange={(v) => setMarket({ ar1_sigma: v })}
            />
            <SliderRow
              id="ar1_phi"
              label="AR(1) φ"
              min={0.3}
              max={0.95}
              step={0.05}
              tone={price}
              value={draft.market.ar1_phi}
              onChange={(v) => setMarket({ ar1_phi: v })}
            />
            <SliderRow
              id="alpha_2027"
              label="Cannib. α 2027"
              digits={0}
              min={20}
              max={100}
              step={5}
              tone={price}
              value={draft.market.cannibalisation_alpha_2027}
              onChange={(v) => setMarket({ cannibalisation_alpha_2027: v })}
            />
            <SliderRow
              id="alpha_2036"
              label="Cannib. α 2036"
              digits={0}
              min={40}
              max={150}
              step={5}
              tone={price}
              value={draft.market.cannibalisation_alpha_2036}
              onChange={(v) => setMarket({ cannibalisation_alpha_2036: v })}
            />
          </div>
        </section>

        <section className="space-y-2.5">
          <SectionChip color={load} icon="⚡" title="Offtaker load" count="3 params" />
          <div className="flex flex-col gap-2.5 pl-0.5">
            <SliderRow
              id="annual_gwh"
              label="Annual consumption"
              unit="GWh"
              digits={0}
              min={20}
              max={500}
              step={10}
              tone={load}
              value={draft.load.annual_consumption_gwh}
              onChange={(v) => setLoad({ annual_consumption_gwh: v })}
            />
            <SliderRow
              id="seasonal_amp"
              label="Seasonal amplitude"
              min={0}
              max={0.3}
              step={0.01}
              tone={load}
              value={draft.load.seasonal_amplitude}
              onChange={(v) => setLoad({ seasonal_amplitude: v })}
            />
            <SliderRow
              id="noise_sigma"
              label="Hourly noise σ"
              min={0.01}
              max={0.15}
              step={0.01}
              tone={load}
              value={draft.load.noise_sigma}
              onChange={(v) => setLoad({ noise_sigma: v })}
            />
          </div>
        </section>

        <section className="space-y-2.5">
          <SectionChip color={text} icon="◆" title="Deal" count="3 params" />
          <div className="flex flex-col gap-2.5 pl-0.5">
            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <Label htmlFor="start_date" className="text-[11px] text-muted-foreground">
                  Start
                </Label>
                <Input
                  id="start_date"
                  type="date"
                  className="font-mono text-[11.5px]"
                  value={draft.deal.start_date}
                  onChange={(e) => setDeal({ start_date: e.target.value })}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="end_date" className="text-[11px] text-muted-foreground">
                  End
                </Label>
                <Input
                  id="end_date"
                  type="date"
                  className="font-mono text-[11.5px]"
                  value={draft.deal.end_date}
                  onChange={(e) => setDeal({ end_date: e.target.value })}
                />
              </div>
            </div>
            <SliderRow
              id="discount_rate"
              label="Discount rate"
              digits={3}
              min={0.03}
              max={0.15}
              step={0.005}
              tone={text}
              value={draft.deal.discount_rate}
              onChange={(v) => setDeal({ discount_rate: v })}
            />
            <SliderRow
              id="base_strike"
              label="Base strike"
              unit="€/MWh"
              digits={1}
              min={30}
              max={120}
              step={0.5}
              tone={accent}
              value={baseStrike}
              onChange={(v) => setBaseStrike(v)}
            />
          </div>
        </section>

        <div className="flex gap-2 pt-1">
          <Button
            size="sm"
            className="h-9 flex-1 rounded-[9px] text-[13px] font-semibold text-primary-foreground"
            style={{
              background:
                'linear-gradient(180deg, var(--accent), var(--accent-deep))',
              boxShadow:
                'inset 0 1px 0 var(--accent-deep), 0 3px 10px color-mix(in oklch, var(--accent) 25%, transparent)',
            }}
            onClick={() => onApply(draft, baseStrike)}
            disabled={busy}
          >
            {busy ? 'Running…' : 'Apply changes'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-9 rounded-[9px] text-[13px]"
            onClick={handleReset}
            disabled={busy}
          >
            Reset
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}
