// Общий компонент обоих сайтов (shared_web/frontend).
import type { ReactNode } from 'react'
import Box from '@mui/material/Box'

/**
 * Контейнер диаграммы Chart.js (responsive, maintainAspectRatio: false), забирающий остаток высоты панели.
 * Холст — в абсолютном слое: размер задаёт контейнер, а не диаграмма. Если холст лежит прямо во flex-контейнере,
 * Chart.js и контейнер растягивают друг друга: форма уходит за экран, при перерисовке видны «лишние» диаграммы.
 */
export default function FitChartBox({ children, minHeight = 0 }: { children: ReactNode; minHeight?: number }) {
  return (
    <Box sx={{ flex: '1 1 0', minHeight, minWidth: 0, position: 'relative', overflow: 'hidden' }}>
      <Box sx={{ position: 'absolute', inset: 0 }}>{children}</Box>
    </Box>
  )
}
