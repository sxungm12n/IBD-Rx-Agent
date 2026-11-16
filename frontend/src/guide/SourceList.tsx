import type { GuideSource } from './types'

function preview(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  if (flat.length <= 180) return flat
  return `${flat.slice(0, 180)}…`
}

export default function SourceList({ sources }: { sources: GuideSource[] }) {
  if (sources.length === 0) return null

  return (
    <section className="sources" aria-label="근거 원문">
      <h2>근거 원문</h2>
      <ol>
        {sources.map((source) => (
          <li key={source.id} className="source">
            <p className="source-kicker">
              {source.page != null ? `p.${source.page}` : '페이지 없음'}
              {source.section ? ` · ${source.section}` : ''}
            </p>
            <h3>{source.title || source.id}</h3>
            {source.drugs.length > 0 && (
              <ul className="tags">
                {source.drugs.map((drug) => (
                  <li key={drug}>{drug}</li>
                ))}
              </ul>
            )}
            <p className="source-preview">{preview(source.text)}</p>
            <details>
              <summary>원문 전체</summary>
              <p className="source-text">{source.text}</p>
            </details>
          </li>
        ))}
      </ol>
    </section>
  )
}
