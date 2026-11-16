import { useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'

type Props = {
  pending: boolean
  onAsk: (question: string) => void
}

export default function AskForm({ pending, onAsk }: Props) {
  const [question, setQuestion] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    const cleaned = question.trim()
    if (cleaned.length < 2 || pending) return
    onAsk(cleaned)
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) {
      event.preventDefault()
      event.currentTarget.form?.requestSubmit()
    }
  }

  return (
    <form className="ask" onSubmit={submit}>
      <label className="ask-label" htmlFor="question">
        질문
      </label>
      <textarea
        id="question"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        onKeyDown={onKeyDown}
        rows={4}
        maxLength={2000}
        placeholder="예: 중등도 크론병에서 인플릭시맙 급여를 받으려면 어떤 조건이 필요한가요?"
      />
      <div className="ask-actions">
        <p className="hint">⌘ Enter 또는 Ctrl Enter로 보낼 수 있습니다.</p>
        <button className="primary" type="submit" disabled={pending || question.trim().length < 2}>
          {pending ? '답변 작성 중' : '답변 받기'}
        </button>
      </div>
    </form>
  )
}
