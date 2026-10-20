// Поле ввода поискового образа с «крестиком» очистки (правило оформления): крестик виден,
// пока в поле есть текст; нажатие очищает поле и применяет фильтр — то же, что Enter
// с пустым значением (onClear должен отправить форму с пустым образом).
import type { ReactNode } from 'react'
import TextField, { type TextFieldProps } from '@mui/material/TextField'
import IconButton from '@mui/material/IconButton'
import InputAdornment from '@mui/material/InputAdornment'
import ClearIcon from '@mui/icons-material/Clear'
import { useT } from '@app/i18n'

type Props = TextFieldProps & {
  /** Очистить поле и применить фильтр (как Enter с пустым значением). */
  onClear: () => void
}

export default function SearchField({ onClear, slotProps, ...rest }: Props) {
  const t = useT()
  const hasValue = rest.value != null && String(rest.value) !== ''
  const inputSlot = (slotProps?.input ?? {}) as { endAdornment?: ReactNode } & Record<string, unknown>
  return (
    <TextField
      {...rest}
      slotProps={{
        ...slotProps,
        input: {
          ...inputSlot,
          endAdornment: hasValue ? (
            <InputAdornment position="end">
              <IconButton
                size="small"
                edge="end"
                title={t('Очистить')}
                aria-label={t('Очистить')}
                // не терять фокус поля: иначе onBlur успел бы отправить старое значение
                onMouseDown={(e) => e.preventDefault()}
                onClick={onClear}
              >
                <ClearIcon fontSize="small" />
              </IconButton>
            </InputAdornment>
          ) : (
            inputSlot.endAdornment
          ),
        },
      }}
    />
  )
}
