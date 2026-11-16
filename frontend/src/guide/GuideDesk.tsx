import { useEffect, useState } from 'react'
import { askGuide, fetchGuideStatus } from './api'
import AskForm from './AskForm'
import SourceList from './SourceList'
import { SUGGESTIONS } from './suggestions'
import type { GuideAnswer, GuideStatus } from './types'

export default function GuideDesk() {
  const [status, setStatus] = useState<GuideStatus | null>(null)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<GuideAnswer | null>(null)
  const [asked, setAsked] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    let timer = 0

    const tick = async () => {
      try {
        const next = await fetchGuideStatus()
        if (cancelled) return
        setStatus(next)
        setConnectionError(null)
        if (next.reranker !== 'ready') timer = window.setTimeout(tick, 3000)
      } catch (err: unknown) {
        if (cancelled) return
        setConnectionError(err instanceof Error ? err.message : '연결에 실패했습니다')
        timer = window.setTimeout(tick, 3000)
      }
    }

    void tick()
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [])

  async function onAsk(question: string) {
    setPending(true)
    setError(null)
    setAsked(question)
    try {
      setResult(await askGuide(question))
    } catch (err: unknown) {
      setResult(null)
      setError(err instanceof Error ? err.message : '답변을 받지 못했습니다')
    } finally {
      setPending(false)
    }
  }

  const statusLine = connectionError
    ? `백엔드에 연결하지 못했습니다. ${connectionError}`
    : status?.reranker === 'ready'
      ? `가이드북 ${status.passages ?? 0}쪽을 검색할 수 있습니다.`
      : status?.reranker === 'error'
        ? status.detail || '검색 인덱스를 준비하지 못했습니다.'
        : '검색 인덱스를 준비하고 있습니다. 처음 한 번은 재정렬 모델을 받느라 시간이 걸립니다.'

  return (
    <section className="desk">
      <h1>급여 기준을 물어보세요</h1>
      <p className="lead">
        2024 대한장연구학회 염증성장질환 보험가이드북만 근거로 답합니다. BM25와 FAISS 검색을
        합친 뒤 BAAI/bge-reranker-v2-m3가 원문을 다시 정렬합니다.
      </p>
      <p className={status?.reranker === 'error' || connectionError ? 'error' : 'status'}>{statusLine}</p>

      <AskForm pending={pending} onAsk={onAsk} />

      <div className="suggestions">
        {SUGGESTIONS.map((question) => (
          <button key={question} type="button" disabled={pending} onClick={() => onAsk(question)}>
            {question}
          </button>
        ))}
      </div>

      {pending && <p className="status">근거 문서를 고르고 답변을 쓰고 있습니다.</p>}
      {error && <p className="error">{error}</p>}

      {result && (
        <>
          {asked && <p className="asked">{asked}</p>}
          <article className="answer">
            <h2>답변</h2>
            <div className="answer-body">{result.answer}</div>
            <p className="disclaimer">
              가이드북 발췌에 근거한 참고입니다. 고시 원문과 환자 상태를 함께 확인해야 하며, 진료
              결정을 대신하지 않습니다.
            </p>
          </article>
          <SourceList sources={result.sources} />
        </>
      )}
    </section>
  )
}
