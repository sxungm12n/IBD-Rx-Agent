import { useState } from 'react'
import GuideDesk from './guide/GuideDesk'
import StageBench from './guide/StageBench'
import './App.css'

export default function App() {
  const [view, setView] = useState<'ask' | 'stages'>('ask')

  return (
    <main className="page">
      <header className="brand">
        <img className="brand-icon" src="/icon.png" alt="" width={56} height={56} />
        <div>
          <p className="eyebrow">IBD Rx Agent</p>
          <p className="brand-sub">2024 보험가이드북</p>
        </div>
      </header>
      <nav className="views" aria-label="화면">
        <button type="button" className={view === 'ask' ? 'view-on' : ''} onClick={() => setView('ask')}>
          질문
        </button>
        <button type="button" className={view === 'stages' ? 'view-on' : ''} onClick={() => setView('stages')}>
          단계 검사
        </button>
      </nav>
      {view === 'ask' ? <GuideDesk /> : <StageBench />}
    </main>
  )
}
