import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/roboto/400.css'
import '@fontsource/roboto/500.css'
import '@fontsource/roboto/700.css'
import App from './App'

// Прежний адрес интерфейса /ui/... (закладки; nginx домена шлёт «/» на /ui/) — тот же адрес без префикса.
// Без запроса к серверу: серверный редирект /ui/ → / вместе с редиректом nginx дал бы петлю.
{
  const { pathname, search, hash } = window.location
  if (pathname === '/ui' || pathname.startsWith('/ui/')) {
    window.history.replaceState(null, '', (pathname.slice(3) || '/') + search + hash)
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
