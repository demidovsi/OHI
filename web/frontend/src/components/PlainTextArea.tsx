import Box from '@mui/material/Box'
import type { SxProps, Theme } from '@mui/material/styles'

interface Props {
  value: string
  onChange?: (v: string) => void
  readOnly?: boolean
  placeholder?: string
  name?: string
  /** Цвет текста — токен палитры ('error.main', 'secondary.main', ...). */
  color?: string
  minRows?: number
  /**
   * Направление текста атрибутом dir (например 'rtl' для текстов на иврите). Атрибут, а не
   * CSS direction: RTL-плагин Emotion в интерфейсе на иврите переворачивает CSS direction/text-align.
   */
  dir?: 'rtl' | 'ltr' | 'auto'
  sx?: SxProps<Theme>
}

/**
 * Обычная <textarea> в стиле MUI. Используется вместо TextField multiline —
 * тексты законопроектов/стенограмм весят сотни КБ, авторасчёт высоты
 * TextField на них тормозит.
 */
export default function PlainTextArea({ value, onChange, readOnly, placeholder, name, color, minRows = 6, dir, sx }: Props) {
  return (
    <Box
      component="textarea"
      name={name}
      dir={dir}
      value={value}
      placeholder={placeholder}
      readOnly={readOnly || !onChange}
      onChange={onChange ? (e: React.ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value) : undefined}
      rows={minRows}
      sx={[
        {
          width: '100%',
          boxSizing: 'border-box',
          resize: 'vertical',
          fontFamily: 'Roboto, Helvetica, Arial, sans-serif',
          fontSize: 13,
          lineHeight: 1.4,
          p: 1,
          borderRadius: 1,
          border: 1,
          borderColor: 'divider',
          bgcolor: 'background.paper',
          color: color ?? 'text.primary',
          outline: 'none',
          '&:focus': { borderColor: 'primary.main' },
        },
        ...(Array.isArray(sx) ? sx : sx ? [sx] : []),
      ]}
    />
  )
}
