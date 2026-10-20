import Alert from '@mui/material/Alert'
import Stack from '@mui/material/Stack'
import type { FlashMessage } from '../api'
import { useT } from '../i18n'

const SEVERITY: Record<string, 'error' | 'warning' | 'info' | 'success'> = {
  error: 'error',
  danger: 'error',
  warning: 'warning',
  info: 'info',
  success: 'success',
  message: 'info',
}

export default function FlashMessages({ messages, onDismiss }: { messages: FlashMessage[]; onDismiss: (i: number) => void }) {
  const t = useT()
  if (!messages.length) return null
  return (
    <Stack spacing={1} sx={{ mb: 1.5, flexShrink: 0 }}>
      {messages.map(([cat, text], i) => (
        <Alert key={i} severity={SEVERITY[cat] ?? 'info'} onClose={() => onDismiss(i)} sx={{ whiteSpace: 'pre-wrap' }}>
          {t(text)}
        </Alert>
      ))}
    </Stack>
  )
}
