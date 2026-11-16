import type { GuideAnswer, GuideStatus, StageResult, StageTrace } from './types'

async function readError(response: Response): Promise<string> {
  const body = (await response.json().catch(() => null)) as { detail?: unknown } | null
  if (body && typeof body.detail === 'string' && body.detail) return body.detail
  return `HTTP ${response.status}`
}

export async function fetchGuideStatus(): Promise<GuideStatus> {
  const response = await fetch('/api/guide/status')
  if (!response.ok) throw new Error(await readError(response))
  return (await response.json()) as GuideStatus
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new Error(await readError(response))
  return (await response.json()) as T
}

export function fetchBm25(question: string, k = 12): Promise<StageResult> {
  return postJson('/api/guide/stages/bm25', { question, k })
}

export function fetchVector(question: string, k = 12): Promise<StageResult> {
  return postJson('/api/guide/stages/vector', { question, k })
}

export function fetchFusion(question: string): Promise<StageResult> {
  return postJson('/api/guide/stages/fusion', { question })
}

export function fetchRerank(question: string): Promise<StageResult> {
  return postJson('/api/guide/stages/rerank', { question })
}

export function fetchTrace(question: string): Promise<StageTrace> {
  return postJson('/api/guide/stages/trace', { question })
}

export async function askGuide(question: string): Promise<GuideAnswer> {
  const response = await fetch('/api/guide/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question }),
  })
  if (!response.ok) throw new Error(await readError(response))
  return (await response.json()) as GuideAnswer
}
