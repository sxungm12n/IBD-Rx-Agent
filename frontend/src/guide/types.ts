export type GuideSource = {
  id: string
  page: number | null
  section: string
  title: string
  text: string
  drugs: string[]
  disease: string[]
}

export type GuideAnswer = {
  answer: string
  sources: GuideSource[]
}

export type GuideStatus = {
  passages: number | null
  reranker: 'loading' | 'ready' | 'error'
  detail: string | null
}

export type StageHit = GuideSource & {
  rank: number
  score: number
}

export type StageResult = {
  stage: string
  question: string
  hits: StageHit[]
}

export type StageTrace = {
  question: string
  answer_k: number
  bm25: StageHit[]
  vector: StageHit[]
  fusion: StageHit[]
  rerank: StageHit[]
}
