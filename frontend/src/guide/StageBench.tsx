import { useState } from 'react'
import { fetchBm25, fetchFusion, fetchRerank, fetchTrace, fetchVector } from './api'
import { SUGGESTIONS } from './suggestions'
import type { StageHit, StageResult, StageTrace } from './types'

const SINGLE = [
  { id: 'bm25', label: 'BM25', run: fetchBm25 },
  { id: 'vector', label: '임베딩', run: fetchVector },
  { id: 'fusion', label: '융합', run: fetchFusion },
  { id: 'rerank', label: '재정렬', run: fetchRerank },
] as const

const STAGE_LABEL: Record<string, string> = {
  bm25: 'BM25',
  vector: '임베딩 (FAISS)',
  fusion: '융합 (RRF)',
  rerank: '재정렬 (bge-reranker-v2-m3)',
}

function preview(text: string): string {
  const flat = text.replace(/\s+/g, ' ').trim()
  if (flat.length <= 160) return flat
  return `${flat.slice(0, 160)}…`
}

function HitList({ hits, mark }: { hits: StageHit[]; mark?: number }) {
  if (hits.length === 0) return <p className="status">해당하는 쪽이 없습니다.</p>
  return (
    <ol className="stage-hits">
      {hits.map((hit) => (
        <li key={`${hit.rank}-${hit.id}`} className="source">
          <p className="source-kicker">
            #{hit.rank} · 점수 {hit.score.toFixed(4)} · {hit.page != null ? `p.${hit.page}` : '페이지 없음'}
            {mark != null && hit.rank <= mark ? ' · 답변에 사용' : ''}
          </p>
          <h3>{hit.title || hit.id}</h3>
          <p className="source-preview">{preview(hit.text)}</p>
        </li>
      ))}
    </ol>
  )
}

export default function StageBench() {
  const [question, setQuestion] = useState(SUGGESTIONS[0])
  const [pending, setPending] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [single, setSingle] = useState<StageResult | null>(null)
  const [trace, setTrace] = useState<StageTrace | null>(null)

  async function run(id: string, task: () => Promise<StageResult | StageTrace>, kind: 'single' | 'trace') {
    const cleaned = question.trim()
    if (cleaned.length < 2 || pending) return
    setPending(id)
    setError(null)
    try {
      const result = await task()
      if (kind === 'single') {
        setSingle(result as StageResult)
        setTrace(null)
      } else {
        setTrace(result as StageTrace)
        setSingle(null)
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : '단계 결과를 받지 못했습니다')
    } finally {
      setPending(null)
    }
  }

  return (
    <section className="desk">
      <h1>단계별로 검사합니다</h1>
      <p className="lead">
        BM25, 임베딩 검색, 순위 융합, 재정렬을 각각 호출합니다. 점수는 그 단계의 정렬 점수입니다.
        답변에 들어가는 쪽은 재정렬 상위 5개입니다.
      </p>

      <form
        className="ask"
        onSubmit={(event) => {
          event.preventDefault()
          void run('trace', () => fetchTrace(question), 'trace')
        }}
      >
        <label className="ask-label" htmlFor="stage-question">
          검사할 질문
        </label>
        <textarea
          id="stage-question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
        />
        <div className="stage-actions">
          {SINGLE.map((stage) => (
            <button
              key={stage.id}
              type="button"
              disabled={pending !== null || question.trim().length < 2}
              onClick={() => run(stage.id, () => stage.run(question), 'single')}
            >
              {pending === stage.id ? '검색 중' : stage.label}
            </button>
          ))}
          <button className="primary" type="submit" disabled={pending !== null || question.trim().length < 2}>
            {pending === 'trace' ? '비교 중' : '전 단계 비교'}
          </button>
        </div>
      </form>

      <div className="suggestions">
        {SUGGESTIONS.map((item) => (
          <button key={item} type="button" disabled={pending !== null} onClick={() => setQuestion(item)}>
            {item}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}

      {single && (
        <section className="sources">
          <h2>
            {STAGE_LABEL[single.stage] ?? single.stage}
            <span className="stage-path">POST /api/guide/stages/{single.stage}</span>
          </h2>
          <HitList hits={single.hits} mark={single.stage === 'rerank' ? 5 : undefined} />
        </section>
      )}

      {trace && (
        <div className="trace">
          {(
            [
              ['bm25', trace.bm25],
              ['vector', trace.vector],
              ['fusion', trace.fusion],
              ['rerank', trace.rerank],
            ] as const
          ).map(([stage, hits]) => (
            <section key={stage} className="sources">
              <h2>
                {STAGE_LABEL[stage]}
                <span className="stage-path">POST /api/guide/stages/{stage}</span>
              </h2>
              <HitList hits={hits} mark={stage === 'rerank' ? trace.answer_k : undefined} />
            </section>
          ))}
        </div>
      )}
    </section>
  )
}
