import { useState } from 'react'

/** Раскрытые длинные тексты ячеек (ClampedText): помнит страница, поэтому обновление таблицы (автообновление, страницы,
 * сутки) их не закрывает — как в форме Log. Ключ — строка + колонка, например `${id}:answer`. */
export function useOpened() {
  const [opened, setOpened] = useState<Set<string>>(() => new Set())
  const toggle = (key: string) =>
    setOpened((prev) => {
      const next = new Set(prev)
      if (!next.delete(key)) next.add(key)
      return next
    })
  return { has: (key: string) => opened.has(key), toggle }
}
