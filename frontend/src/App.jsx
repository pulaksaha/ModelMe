import { useCallback, useEffect, useRef, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { Environment, Grid, OrbitControls, useGLTF } from '@react-three/drei'
import { Activity, ArrowDownToLine, Check, ChevronRight, CircleAlert, FileJson2, LoaderCircle, RotateCcw, Sparkles, Upload, UserRound } from 'lucide-react'

// Same-origin in production; Vite proxies /api to the local backend in dev.
const API = import.meta.env.VITE_API_URL || ''
const TERMINAL = new Set(['complete', 'failed'])

function Model({ url }) {
  const { scene } = useGLTF(url)
  return <primitive object={scene} position={[0, -0.9, 0]} />
}

function Viewer({ jobId }) {
  const modelUrl = jobId ? `${API}/api/reconstruction/download/${jobId}` : null
  return <div className="viewer">
    {modelUrl ? <Canvas camera={{ position: [2.4, 1.45, 3.4], fov: 36 }}>
      <color attach="background" args={['#e9e8e2']} />
      <ambientLight intensity={1.6} /><directionalLight position={[3, 5, 4]} intensity={2.2} />
      <Environment preset="studio" /><Grid args={[8, 8]} position={[0, -0.92, 0]} cellSize={0.25} cellThickness={0.5} sectionSize={1} sectionThickness={1} fadeDistance={8} infiniteGrid />
      <Model key={modelUrl} url={modelUrl} /><OrbitControls makeDefault minDistance={1.5} maxDistance={7} target={[0, 0, 0]} />
    </Canvas> : <div className="preview-placeholder"><div className="silhouette"><span /></div><span>YOUR MODEL PREVIEW</span><small>Upload measurements to begin</small></div>}
    <div className="viewer-tag"><span className="live-dot" /> 3D PREVIEW <span className="tag-divider" /> DRAG TO ROTATE</div>
  </div>
}

function App() {
  const [file, setFile] = useState(null)
  const [job, setJob] = useState(null)
  const [status, setStatus] = useState(null)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const inputRef = useRef(null)
  const timer = useRef(null)

  const poll = useCallback(async (id) => {
    try {
      const response = await fetch(`${API}/api/reconstruction/status/${id}`)
      const data = await response.json()
      if (!response.ok) throw new Error(data.detail || 'Could not read job status')
      setStatus(data)
      if (data.status === 'complete') {
        const res = await fetch(`${API}/api/reconstruction/result/${id}`)
        const body = await res.json()
        if (!res.ok) throw new Error(body.detail || 'Could not load result')
        setResult(body)
      }
      if (data.status === 'failed') setError(data.error || data.stage_message || 'Reconstruction failed')
      return data.status
    } catch (err) { setError(err.message); return 'failed' }
  }, [])

  useEffect(() => () => clearInterval(timer.current), [])

  async function start() {
    if (!file) return
    setBusy(true); setError(''); setStatus(null); setResult(null)
    try {
      const form = new FormData(); form.append('file', file)
      const upload = await fetch(`${API}/api/reconstruction/upload`, { method: 'POST', body: form })
      const data = await upload.json()
      if (!upload.ok) throw new Error(data.detail || 'Upload failed')
      setJob(data)
      const response = await fetch(`${API}/api/reconstruction/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ job_id: data.job_id }),
      })
      const generated = await response.json()
      if (!response.ok) throw new Error(generated.detail || 'Could not start reconstruction')
      const initial = await poll(data.job_id)
      if (!TERMINAL.has(initial)) timer.current = setInterval(async () => {
        const current = await poll(data.job_id)
        if (TERMINAL.has(current)) clearInterval(timer.current)
      }, 1800)
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }

  function reset() { clearInterval(timer.current); setFile(null); setJob(null); setStatus(null); setResult(null); setError(''); if (inputRef.current) inputRef.current.value = '' }
  const running = status && !TERMINAL.has(status.status)
  const percent = Math.max(0, Math.min(100, status?.progress ?? 0))

  return <main className="shell">
    <header className="topbar">
      <a className="brand" href="#top"><span className="brand-mark"><i /><i /><i /></span><span>form<span className="brand-dot">.</span></span></a>
      <div className="topbar-meta"><span className="status-led" /> LOCAL WORKSPACE <span className="topbar-divider">/</span> BODY LAB</div>
      <div className="avatar"><UserRound size={17} /></div>
    </header>

    <section className="intro" id="top">
      <div><div className="eyebrow"><span>01</span> PERSONALIZED BODY MODELING</div><h1>Your shape,<br /><em>made visible.</em></h1>
        <p className="intro-copy">A precise 3D body model, shaped from your measurements.<br />Upload your data and let the form engine do the rest.</p>
      </div>
      <div className="step-indicator"><div className="step active"><b>01</b><span>Measurements</span></div><i /><div className={`step ${status ? 'active' : ''}`}><b>02</b><span>Reconstruction</span></div><i /><div className={`step ${result ? 'active' : ''}`}><b>03</b><span>Your model</span></div></div>
    </section>

    <section className="workspace">
      <div className="panel input-panel">
        <div className="panel-heading"><div><div className="eyebrow">INPUT</div><h2>Measurements</h2></div><span className="section-number">01 / 03</span></div>
        <p className="panel-copy">Start with an exported measurement file. We’ll check it before building your model.</p>
        <input ref={inputRef} className="hidden-input" type="file" accept=".json,application/json" onChange={e => { setFile(e.target.files?.[0] || null); setError('') }} />
        <button className={`dropzone ${file ? 'has-file' : ''}`} onClick={() => inputRef.current?.click()} onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); const picked = e.dataTransfer.files?.[0]; if (picked) { setFile(picked); setError('') } }}>
          <span className="drop-icon">{file ? <FileJson2 size={21} /> : <Upload size={21} />}</span>
          <strong>{file ? file.name : 'Drop your JSON file here'}</strong><span>{file ? `${(file.size / 1024).toFixed(1)} KB · ready to process` : <>or <u>browse files</u> · JSON up to 10 MB</>}</span>
        </button>
        {job && <div className="data-summary"><div className="summary-top"><span>FILE CHECK</span><span className="valid-pill"><Check size={12} /> {job.validation_status || 'Ready'}</span></div><div className="summary-grid"><div><b>{job.available_measurements?.length ?? '—'}</b><span>measurements</span></div><div><b>{job.landmark_count ?? '—'}</b><span>landmarks</span></div><div><b>{job.unit || '—'}</b><span>unit</span></div></div>{job.validation_warnings?.length > 0 && <p className="warning-note"><CircleAlert size={14} /> {job.validation_warnings[0]}</p>}</div>}
        {error && <div className="error-note"><CircleAlert size={15} /> <span>{error}</span></div>}
        <button className="primary-button" onClick={start} disabled={!file || busy || running}>{busy ? <><LoaderCircle className="spin" size={16} /> Starting…</> : running ? <><LoaderCircle className="spin" size={16} /> Building your model</> : <><Sparkles size={16} /> Generate my model <ChevronRight size={16} /></>}</button>
        <div className="privacy-note"><Activity size={14} /> Your measurements are processed locally.</div>
      </div>

      <div className="panel preview-panel">
        <div className="panel-heading preview-heading"><div><div className="eyebrow">OUTPUT</div><h2>{result ? 'Your model' : 'Model preview'}</h2></div><span className="section-number">02 / 03</span></div>
        <Viewer jobId={result ? job?.job_id : null} />
        {running && <div className="progress-wrap"><div className="progress-label"><span><LoaderCircle className="spin" size={14} /> {status.stage_message || 'Preparing reconstruction'}</span><b>{percent}%</b></div><div className="progress-track"><i style={{ width: `${percent}%` }} /></div></div>}
        {result && <div className="result-actions"><div className="result-copy"><span className="result-kicker"><Check size={13} /> RECONSTRUCTION READY</span><b>{result.converged ? 'Measurements matched' : 'Model generated'}</b><small>{result.iterations ?? 0} optimization iterations</small></div><div className="buttons"><a className="download-button" href={`${API}/api/reconstruction/download/${job.job_id}`}><ArrowDownToLine size={15} /> Download GLB</a><a className="report-link" href={`${API}/api/reconstruction/report/${job.job_id}`} target="_blank" rel="noreferrer">Validation report</a><button className="icon-button" title="Start another model" onClick={reset}><RotateCcw size={15} /></button></div></div>}
        {!running && !result && <div className="preview-foot"><span><i /> REAL-TIME 3D VIEW</span><span>GLB EXPORT</span></div>}
      </div>
    </section>
    <footer><span>FORM ENGINE <span className="brand-dot">●</span> 0.1</span><span>MEASUREMENT TO MODEL, MADE SIMPLE</span></footer>
  </main>
}

export default App
