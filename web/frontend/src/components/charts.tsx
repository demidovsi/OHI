import { useMemo, useRef, useState } from 'react'
import { Bar } from 'react-chartjs-2'
import {
  BarElement,
  CategoryScale,
  Chart,
  LinearScale,
  Tooltip,
  type ChartOptions,
  type Plugin,
} from 'chart.js'
import Box from '@mui/material/Box'
import Paper from '@mui/material/Paper'
import ToggleButton from '@mui/material/ToggleButton'
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup'
import Typography from '@mui/material/Typography'
import { useTheme } from '@mui/material/styles'
import { useT } from '../i18n'

// Общая обёртка над Chart.js для страниц-диаграмм старого UI
// (committee_plot.html, session_plot.js): горизонтальная гистограмма,
// подписи значений справа от столбика, цвета осей/сетки из темы MUI.

Chart.register(BarElement, CategoryScale, LinearScale, Tooltip)

// Палитра столбиков старого UI (backgroundColors в committee_plot.html / session_plot.js).
const BAR_COLORS = ['#3e95cd', '#8e5ea2', '#3cba9f', '#e8c3b9', '#c45850']

export const ROW_HEIGHT = 22
export const MIN_CHART_HEIGHT = 300

/** Высота канваса по числу строк — как neededChartHeight() в старом JS. */
export function neededChartHeight(count: number, initial = MIN_CHART_HEIGHT) {
  return Math.max(initial, count * ROW_HEIGHT + 60)
}

export function formatValueLabel(value: number, percent: boolean) {
  return percent ? value.toFixed(1) + '%' : String(Math.round(value))
}

interface HorizontalBarProps {
  labels: string[]
  /** «Сырые» количества — проценты считаются на клиенте от summa. */
  values: number[]
  percent: boolean
  summa: number
  legend: string
  /** Минимальная высота (par.height старого UI). */
  minHeight?: number
}

/** Ширина колонки подписей оси Y по самой длинной подписи (одинаковая у графика и у оси X). */
function yAxisWidth(labels: string[]) {
  const ctx = document.createElement('canvas').getContext('2d')
  if (!ctx) return 160
  ctx.font = '12px Roboto, "Helvetica Neue", Arial, sans-serif'
  const w = Math.max(0, ...labels.map((l) => ctx.measureText(l).width))
  return Math.min(Math.ceil(w) + 16, 420)
}

/** Толщина полосы прокрутки (theme.ts: *::-webkit-scrollbar) — под неё отступ у оси X. */
const SCROLLBAR = 10

export function HorizontalBarChart({ labels, values, percent, summa, legend, minHeight }: HorizontalBarProps) {
  const theme = useTheme()
  const t = useT()
  const tickColor = theme.palette.text.primary
  const gridColor = theme.palette.divider
  const labelColor = theme.palette.mode === 'dark' ? '#d0d0d0' : '#333333'

  const displayValues = useMemo(() => {
    if (!percent) return values
    if (!summa) return values.map(() => 0)
    return values.map((v) => (v / summa) * 100)
  }, [values, percent, summa])

  // Диаграмма прокручивается отдельно, ось X закреплена под ней (правило оформления):
  // столбики — в прокручиваемой области без подписей оси X, сама ось — отдельный график-полоска
  // с тем же диапазоном (min/max) и той же шириной колонки подписей Y, поэтому деления совпадают.
  const maxValue = Math.max(0, ...displayValues)
  const xMax = maxValue > 0 ? maxValue * 1.15 : 1 // запас справа под подпись значения
  const yWidth = useMemo(() => yAxisWidth(labels), [labels])
  const height = Math.max((minHeight ?? MIN_CHART_HEIGHT) - 40, labels.length * ROW_HEIGHT + 8)
  const fixWidth = (scale: { width: number }) => {
    scale.width = yWidth
  }
  const xTicks = { color: tickColor, callback: (v: string | number) => formatValueLabel(Number(v), percent) }

  const data = {
    labels,
    datasets: [
      {
        label: legend,
        data: displayValues,
        backgroundColor: labels.map((_, i) => BAR_COLORS[i % BAR_COLORS.length]),
        borderColor: 'rgba(75,192,192,1)',
        borderWidth: 0,
      },
    ],
  }

  // Подпись значения справа от столбика — аналог плагина valueLabels старого UI.
  const valueLabels: Plugin<'bar'> = {
    id: 'valueLabels',
    afterDatasetsDraw(chart) {
      const meta = chart.getDatasetMeta(0)
      if (meta.hidden) return
      const ctx = chart.ctx
      meta.data.forEach((bar, index) => {
        const value = chart.data.datasets[0].data[index] as number
        if (value === null || value === undefined || Number.isNaN(value)) return
        const props = bar.getProps(['x', 'y'], true)
        ctx.save()
        ctx.fillStyle = labelColor
        ctx.font = '12px Roboto, Verdana, sans-serif'
        ctx.textAlign = 'left'
        ctx.textBaseline = 'middle'
        ctx.fillText(formatValueLabel(value, percent), props.x + 6, props.y)
        ctx.restore()
      })
    },
  }

  const options: ChartOptions<'bar'> = {
    indexAxis: 'y',
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    layout: { padding: { right: 8 } },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (item) => `${legend}: ${formatValueLabel(Number(item.raw), percent)}`,
        },
      },
    },
    scales: {
      x: { min: 0, max: xMax, ticks: { ...xTicks, display: false }, grid: { color: gridColor }, border: { display: false } },
      y: { ticks: { color: tickColor, autoSkip: false }, grid: { color: gridColor }, afterFit: fixWidth },
    },
  }

  // Ось X отдельно: после отрисовки берём позиции делений самого графика и рисуем подписи
  // в закреплённой полоске под областью прокрутки (координаты совпадают: та же ширина).
  const [axis, setAxis] = useState<{ left: number; right: number; ticks: { x: number; label: string }[] }>({
    left: 0,
    right: 0,
    ticks: [],
  })
  const axisKey = useRef('')
  const axisCollector: Plugin<'bar'> = {
    id: 'axisCollector',
    afterRender(chart) {
      const sx = chart.scales.x
      const next = {
        left: chart.chartArea.left,
        right: chart.chartArea.right,
        ticks: sx.ticks.map((tk) => ({ x: sx.getPixelForValue(tk.value), label: formatValueLabel(Number(tk.value), percent) })),
      }
      const key = JSON.stringify(next)
      if (key !== axisKey.current) {
        axisKey.current = key
        setTimeout(() => setAxis(next), 0) // не менять состояние React во время отрисовки Chart.js
      }
    },
  }

  return (
    <Paper variant="outlined" sx={{ flex: '1 1 0', minHeight: 160, p: 1.5, display: 'flex', flexDirection: 'column' }}>
      <Typography variant="body2" align="center" sx={{ mb: 1, flexShrink: 0 }}>
        {legend}
      </Typography>
      {labels.length ? (
        <>
          <Box sx={{ flex: '1 1 0', minHeight: 0, overflowY: 'auto', overflowX: 'hidden', scrollbarGutter: 'stable' }}>
            <Box sx={{ height, position: 'relative' }}>
              <Bar data={data} options={options} plugins={[valueLabels, axisCollector]} />
            </Box>
          </Box>
          <Box sx={{ height: 22, flexShrink: 0, position: 'relative', mr: `${SCROLLBAR}px` }}>
            <Box sx={{ position: 'absolute', top: 0, left: axis.left, width: Math.max(0, axis.right - axis.left), borderTop: 1, borderColor: gridColor }} />
            {axis.ticks.map((tk) => (
              <Typography
                key={tk.x}
                component="span"
                sx={{ position: 'absolute', top: 3, left: tk.x, transform: 'translateX(-50%)', fontSize: 12, color: tickColor, whiteSpace: 'nowrap' }}
              >
                {tk.label}
              </Typography>
            ))}
          </Box>
        </>
      ) : (
        <Typography variant="body2" color="text.secondary" align="center" sx={{ py: 4 }}>
          {t('Нет данных')}
        </Typography>
      )}
    </Paper>
  )
}

/** Переключатель «% от регистрации / Количество» (radio name="source" в старом UI). */
export const SOURCE_PERCENT = '% от регистрации'
export const SOURCE_COUNT = 'Количество'

export function PercentModeToggle({ percent, onChange }: { percent: boolean; onChange: (percent: boolean) => void }) {
  const t = useT()
  return (
    <ToggleButtonGroup
      exclusive
      size="small"
      value={percent ? SOURCE_PERCENT : SOURCE_COUNT}
      onChange={(_, v) => {
        if (v === SOURCE_PERCENT) onChange(true)
        if (v === SOURCE_COUNT) onChange(false)
      }}
    >
      <ToggleButton value={SOURCE_PERCENT} title={t('Показать диаграмму в процентном отношении')}>
        {t(SOURCE_PERCENT)}
      </ToggleButton>
      <ToggleButton value={SOURCE_COUNT} title={t('Показать диаграмму в абсолютных величинах')}>
        {t(SOURCE_COUNT)}
      </ToggleButton>
    </ToggleButtonGroup>
  )
}
