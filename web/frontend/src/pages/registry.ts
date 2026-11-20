import type { ComponentType } from 'react'
import NewsBoardPage from './NewsBoardPage'
import AnalysesPage from './AnalysesPage'
import RssPage from './RssPage'
import SearchWordsPage from './SearchWordsPage'
import ChatLogsPage from './ChatLogsPage'
import LogsPage from './LogsPage'
import GuestsPage from './GuestsPage'
import FunctionsPage from './FunctionsPage'

// page (роут SPA и имя формы API) → React-страница.
export const PAGES: Record<string, ComponentType> = {
  news_board: NewsBoardPage,
  analyses: AnalysesPage,
  rss: RssPage,
  search_words: SearchWordsPage,
  chat_logs: ChatLogsPage,
  logs: LogsPage,
  guests: GuestsPage,
  functions: FunctionsPage,
}
