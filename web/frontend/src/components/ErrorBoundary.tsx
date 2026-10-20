import { Component, type ErrorInfo, type ReactNode } from 'react'
import Alert from '@mui/material/Alert'
import AlertTitle from '@mui/material/AlertTitle'
import Button from '@mui/material/Button'
import Box from '@mui/material/Box'
import { readLang, translate } from '../i18n'

interface Props {
  children: ReactNode
}
interface State {
  error: Error | null
}

// Ловит ошибки рендера страницы: вместо белого экрана — сообщение и кнопка перезагрузки.
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('UI error', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error" action={<Button color="inherit" size="small" onClick={() => window.location.reload()}>{translate(readLang(), 'Перезагрузить')}</Button>}>
          <AlertTitle>{translate(readLang(), 'Ошибка интерфейса')}</AlertTitle>
          <Box component="pre" sx={{ m: 0, whiteSpace: 'pre-wrap', fontSize: 12 }}>
            {this.state.error.message}
          </Box>
        </Alert>
      </Box>
    )
  }
}
