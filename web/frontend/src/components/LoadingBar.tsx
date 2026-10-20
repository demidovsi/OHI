// Полоса загрузки поверх формы (правило оформления): не занимает места в разметке, поэтому
// форма не «дёргается», когда полоса появляется и исчезает. На странице — фиксированно под
// верхней панелью (AppBar, Toolbar dense = 48px), в диалоге — по верхнему краю окна диалога.
import LinearProgress from '@mui/material/LinearProgress'

interface Props {
  loading: boolean
  /** Внутри Dialog: полоса по верхнему краю окна диалога (Paper диалога — position: relative). */
  inDialog?: boolean
}

export default function LoadingBar({ loading, inDialog = false }: Props) {
  if (!loading) return null
  return (
    <LinearProgress
      sx={
        inDialog
          ? { position: 'absolute', top: 0, left: 0, right: 0, height: 3, zIndex: 1 }
          : { position: 'fixed', top: 48, left: 0, right: 0, height: 3, zIndex: (t) => t.zIndex.appBar + 1 }
      }
    />
  )
}
