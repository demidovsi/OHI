import { useCallback, useEffect, useRef, useState } from 'react'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import FormControl from '@mui/material/FormControl'
import IconButton from '@mui/material/IconButton'
import InputLabel from '@mui/material/InputLabel'
import Link from '@mui/material/Link'
import MenuItem from '@mui/material/MenuItem'
import Select from '@mui/material/Select'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import useMediaQuery from '@mui/material/useMediaQuery'
import { useTheme } from '@mui/material/styles'
import CloseIcon from '@mui/icons-material/Close'
import DownloadIcon from '@mui/icons-material/Download'
import * as api from '../api'
import type { FlashMessage, FormFields, Par } from '../api'
import { useAuth } from '../auth'
import { useT } from '../i18n'
import FlashMessages from './FlashMessages'
import LoadingBar from './LoadingBar'
import PlainTextArea from './PlainTextArea'

// Карточка новости — модальное окно ленты новостей (бывшие templates/new.html и модалка news_board.js).
// Бэкенд — форма new (new.py): поля new_id, select_lang, title, description, full; кнопки refresh, save,
// translate_ru/en/he, need_article, load_file. Изменять новость может только администратор.

export interface NewsUnit {
  id: number
  lang: string | null
  name_rss: string | null
  public_date: string | null
  name_theme: string | null
  title: string | null
  title_init: string | null
  description: string | null
  description_init: string | null
  full: string | null
  full_init: string | null
  url: string | null
  meta_img: string | null
  author: string | null
  file: number | null
  title_ru: string | null
  title_en: string | null
  title_he: string | null
  description_ru: string | null
  description_en: string | null
  description_he: string | null
}

const LANGS = ['ru', 'en', 'he'] as const

interface Props {
  newsId: number | null
  /** Язык текста новости при открытии (язык отображения ленты). */
  lang?: string
  onClose: () => void
  /** Новость изменилась (перевод/сохранение) — строку таблицы можно обновить без перезапроса суток. */
  onChanged?: (unit: NewsUnit) => void
}

const norm = (s: string | null | undefined) => (s ?? '').trim()

export default function NewsDialog({ newsId, lang = 'ru', onClose, onChanged }: Props) {
  const t = useT()
  const theme = useTheme()
  const fullScreen = useMediaQuery(theme.breakpoints.down('md'))
  const { setUpr } = useAuth()
  const [par, setPar] = useState<Par | null>(null)
  const [messages, setMessages] = useState<FlashMessage[]>([])
  const [loading, setLoading] = useState(false)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [full, setFull] = useState('')
  const onChangedRef = useRef(onChanged)
  useEffect(() => {
    onChangedRef.current = onChanged
  })

  const run = useCallback(
    async (fields: FormFields) => {
      setLoading(true)
      try {
        const res = await api.form('new', [], fields)
        if (res.upr) setUpr(res.upr)
        setMessages(res.messages)
        if (res.redirect) {
          window.location.assign(api.legacyRedirectToRoute(res.redirect))
          return
        }
        const unit = res.par.unit as NewsUnit | undefined
        setPar(res.par)
        if (unit) {
          setTitle(unit.title ?? '')
          setDescription(unit.description ?? '')
          setFull(unit.full ?? '')
          onChangedRef.current?.(unit)
        }
      } catch (e) {
        setMessages([['error', (e as Error).message]])
      } finally {
        setLoading(false)
      }
    },
    [setUpr],
  )

  // Открытие новости (поле open: new.py читает новость из БД заново)
  useEffect(() => {
    if (newsId == null) return
    setPar(null)
    setMessages([])
    run({ new_id: newsId, open: 1, select_lang: lang })
    // eslint-disable-next-line react-hooks/exhaustive-deps -- язык — только при открытии новости
  }, [newsId, run])

  const unit = (par?.unit ?? null) as NewsUnit | null
  const admin = Boolean(par?.admin)
  const selectLang: string = par?.select_lang ?? 'ru'
  const changed =
    admin &&
    unit != null &&
    (norm(title) !== norm(unit.title_init ?? unit.title) ||
      norm(description) !== norm(unit.description_init ?? unit.description) ||
      norm(full) !== norm(unit.full_init ?? unit.full))

  const fields = (extra: FormFields): FormFields => ({
    new_id: newsId ?? '',
    select_lang: selectLang,
    title,
    description,
    full,
    ...extra,
  })

  // Текст на иврите — справа налево в своём поле (атрибут dir), независимо от языка интерфейса
  const textDir = selectLang === 'he' ? 'rtl' : 'ltr'

  return (
    <Dialog open={newsId != null} onClose={onClose} maxWidth="xl" fullWidth fullScreen={fullScreen}>
      <LoadingBar loading={loading} inDialog />
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1, pe: 1 }}>
        <Box component="span" sx={{ flexGrow: 1 }}>
          {t('Информация по новости')}{' '}
          <Box component="span" sx={{ opacity: 0.6 }}>
            #{newsId}
          </Box>
        </Box>
        <IconButton onClick={onClose} aria-label={t('Закрыть')} title={t('Закрыть')}>
          <CloseIcon />
        </IconButton>
      </DialogTitle>
      <DialogContent dividers sx={{ display: 'flex', flexDirection: 'column', minHeight: { md: '70vh' } }}>
        <FlashMessages messages={messages} onDismiss={(i) => setMessages((m) => m.filter((_, j) => j !== i))} />
        {unit && (
          <>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, alignItems: 'center', mb: 1.5, flexShrink: 0 }}>
              <FormControl size="small" sx={{ minWidth: 110 }}>
                <InputLabel id="nd_lang">{t('Язык')}</InputLabel>
                <Select
                  labelId="nd_lang"
                  label={t('Язык')}
                  value={selectLang}
                  title={t('Язык для вывода текста новости')}
                  onChange={(e) => run(fields({ select_lang: e.target.value }))}
                >
                  {LANGS.map((l) => (
                    <MenuItem key={l} value={l}>
                      {l.toUpperCase()}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              {admin &&
                LANGS.filter((l) => l !== unit.lang).map((l) => (
                  <Button
                    key={l}
                    size="small"
                    variant="outlined"
                    color={l === 'ru' ? 'secondary' : l === 'en' ? 'primary' : 'error'}
                    title={t(l === 'ru' ? 'Перевести на русский язык' : l === 'en' ? 'Перевести на английский язык' : 'Перевести на иврит')}
                    onClick={() => run(fields({ ['translate_' + l]: 1 }))}
                  >
                    {l.toUpperCase()}
                  </Button>
                ))}
              {admin && (
                <Button size="small" title={t('Заново прочитать статью с сайта (только для админа)')} onClick={() => run(fields({ need_article: 1 }))}>
                  {t('Статья')}
                </Button>
              )}
              <Box sx={{ flexGrow: 1 }} />
              <Typography variant="body2" color="text.secondary">
                {t('Длина текста')}: <b>{unit.file ?? ''}</b>, {t('Исходный язык')}: <b>{unit.lang ?? ''}</b>
              </Typography>
              {admin && (
                <Tooltip title={t('Загрузить файл в исходном языке')}>
                  <IconButton size="small" onClick={() => run(fields({ load_file: 1 }))}>
                    <DownloadIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              )}
            </Box>
            <Box sx={{ flex: '1 1 auto', minHeight: 0, display: 'flex', flexDirection: { xs: 'column', md: 'row' }, gap: 2 }}>
              <Box sx={{ flex: { md: '0 0 40%' }, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                <Typography variant="body2">
                  {t('Источник:')} <Box component="b" sx={{ color: 'error.main' }}>{unit.name_rss}</Box>{' '}
                  ({t('Время:')} {unit.public_date ?? ''})
                </Typography>
                <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 0.5, alignItems: 'center' }}>
                  <Typography variant="body2">{t('Тема:')}</Typography>
                  {(unit.name_theme ?? '')
                    .split(',')
                    .map((s) => s.trim())
                    .filter(Boolean)
                    .map((s) => (
                      <Chip key={s} size="small" label={s} color="secondary" variant="outlined" />
                    ))}
                </Box>
                <TextField
                  label={t('Заголовок')}
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  multiline
                  minRows={2}
                  slotProps={{ input: { readOnly: !admin }, htmlInput: { dir: textDir } }}
                  sx={{ '& textarea': { fontWeight: 600 } }}
                />
                <TextField
                  label={t('Описание')}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  multiline
                  minRows={3}
                  maxRows={10}
                  slotProps={{ input: { readOnly: !admin }, htmlInput: { dir: textDir } }}
                />
                <Typography variant="body2">
                  {t('Сайт:')}{' '}
                  {unit.url ? (
                    <Link href={unit.url} target="_blank" rel="noopener">
                      {t('Переход на страницу сайта с новостью')}
                    </Link>
                  ) : (
                    '—'
                  )}
                </Typography>
                {unit.meta_img && (
                  <Box component="img" src={unit.meta_img} alt="" sx={{ maxWidth: '100%', maxHeight: 260, objectFit: 'contain', alignSelf: 'flex-start' }} />
                )}
                {unit.author && (
                  <Typography variant="body2">
                    {t('Автор:')} <Box component="b" sx={{ color: 'error.main' }}>{unit.author}</Box>
                  </Typography>
                )}
              </Box>
              <Box sx={{ flex: '1 1 0', minWidth: 0, minHeight: { xs: 300, md: 0 }, display: 'flex', flexDirection: 'column' }}>
                <PlainTextArea
                  value={full}
                  onChange={admin ? setFull : undefined}
                  readOnly={!admin}
                  dir={textDir}
                  placeholder={t('Текст статьи отсутствует')}
                  sx={{ flex: '1 1 0', minHeight: 0, height: '100%', resize: 'none' }}
                />
              </Box>
            </Box>
          </>
        )}
      </DialogContent>
      <DialogActions>
        {changed && (
          <>
            <Button onClick={() => run(fields({ refresh: 1 }))} title={t('Отменить сделанные изменения')}>
              {t('Восстановить')}
            </Button>
            <Button variant="contained" onClick={() => run(fields({ save: 1 }))} title={t('Записать изменения в базу данных')}>
              {t('Сохранить')}
            </Button>
          </>
        )}
        <Button onClick={onClose}>{t('Закрыть')}</Button>
      </DialogActions>
    </Dialog>
  )
}
