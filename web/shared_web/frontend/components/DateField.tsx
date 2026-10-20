import { useEffect, useRef, useState } from 'react'
import TextField, { type TextFieldProps } from '@mui/material/TextField'

// Поле даты фильтра/навигации обоих сайтов (shared_web/README.md). Дата принимается (onCommit):
//  - сразу после выбора или сброса во всплывающем календаре браузера;
//  - при наборе с клавиатуры — по Enter или уходу из поля (а не на каждой цифре: «2» в году уже даёт
//    дату 0002-…). Набор отличаем по нажатой клавише перед change: календарь клавиш не вызывает.
// onCommit получает 'YYYY-MM-DD' или '' (сброс); повторно ту же дату не отправляет, пока сервер не ответил.

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/
/** change позже нажатия клавиши на столько мс — это уже не набор, а календарь. */
const TYPING_MS = 500

const complete = (v: string) => v === '' || (DATE_RE.test(v) && Number(v.slice(0, 4)) >= 1900)

export type DateFieldProps = Omit<TextFieldProps, 'type' | 'value' | 'onChange' | 'onBlur' | 'onKeyDown'> & {
  value: string | null | undefined
  onCommit: (v: string) => void
  /** Пустую дату (сброс) не принимать — поле, у которого дата обязательна (навигация по суткам). */
  required?: boolean
  width?: number
}

export default function DateField({ value, onCommit, required, width = 170, sx, slotProps, ...props }: DateFieldProps) {
  const [local, setLocal] = useState(value ?? '')
  const committed = useRef(value ?? '')
  const lastKey = useRef(0)
  useEffect(() => {
    setLocal(value ?? '')
    committed.current = value ?? ''
  }, [value])

  const commit = (v: string) => {
    if (v === committed.current || !complete(v) || (required && !v)) return
    committed.current = v
    onCommit(v)
  }

  return (
    <TextField
      {...props}
      type="date"
      value={local}
      onChange={(e) => {
        const v = e.target.value
        setLocal(v)
        if (Date.now() - lastKey.current > TYPING_MS) commit(v)
      }}
      onBlur={() => commit(local)}
      onKeyDown={(e) => {
        lastKey.current = Date.now()
        if (e.key === 'Enter') commit(local)
      }}
      slotProps={{ ...slotProps, inputLabel: { shrink: true, ...(slotProps?.inputLabel as object) } }}
      sx={[{ width }, ...(Array.isArray(sx) ? sx : [sx])]}
    />
  )
}
