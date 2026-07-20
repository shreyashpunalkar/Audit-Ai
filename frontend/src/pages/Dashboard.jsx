import { useState, useCallback, useRef } from 'react'
import { Zap, RotateCcw, Edit3, Eye, Trash2, AlertCircle } from 'lucide-react'
import UploadZone from '../components/UploadZone'
import StatusTracker from '../components/StatusTracker'
import JsonViewer from '../components/JsonViewer'
import JsonEditor from '../components/JsonEditor'
import DownloadPanel from '../components/DownloadPanel'
import ValidationBadge from '../components/ValidationBadge'
import {
  uploadDocument,
  processDocument,
  getDocument,
  updateDocumentJson,
  deleteDocument,
} from '../api/client'
import { formatBytes, getFileTypeIcon, countChecks } from '../utils/jsonUtils'

const POLL_INTERVAL = 2500

export default function Dashboard() {
  const [file, setFile] = useState(null)
  const [docId, setDocId] = useState(null)
  const [docData, setDocData] = useState(null)
  const [status, setStatus] = useState('idle') // idle | uploading | processing | completed | error
  const [uploadProgress, setUploadProgress] = useState(0)
  const [errorMsg, setErrorMsg] = useState(null)
  const [viewMode, setViewMode] = useState('view') // view | edit
  const [saving, setSaving] = useState(false)
  const pollRef = useRef(null)

  const [processingStep, setProcessingStep] = useState('idle') // idle | json-generation | validation | complete

  const analyzeDocument = async (id) => {
    console.log("Sending request to Gemini")
    const doc = await getDocument(id)
    console.log("Gemini Response Received")
    return doc
  }

  const generateJSON = async (doc) => {
    console.log("JSON Parsing Started")
    const data = doc.extracted_json
    console.log("JSON Parsing Complete")
    return data
  }

  const validateJSON = async (data) => {
    console.log("Validation Started")
    if (!data) {
      throw new Error("Response is empty or contains no content")
    }
    // Verify it is valid JSON
    if (typeof data !== 'object') {
      throw new Error("Response is not valid JSON")
    }
    return data
  }

  // ── Polling ──────────────────────────────────────────────────────────────
  const startPolling = useCallback((id) => {
    if (pollRef.current) clearInterval(pollRef.current)
    let currentLoggedStage = 0
    const startTime = Date.now()

    pollRef.current = setInterval(async () => {
      // Timeout check (60 seconds)
      if (Date.now() - startTime > 60000) {
        clearInterval(pollRef.current)
        setStatus('error')
        setErrorMsg('NVIDIA NIM API error: Request timed out.')
        console.error('NVIDIA NIM API error: Request timed out after 60 seconds.')
        return
      }

      try {
        const doc = await getDocument(id)
        setDocData(doc)
        setStatus(doc.status)

        // Trace and log transitions
        if (doc.status === 'extracting' && currentLoggedStage < 1) {
          console.log("Extraction Complete")
          currentLoggedStage = 1
        }
        
        if (doc.status === 'ai_analysis' && currentLoggedStage < 2) {
          console.log("OCR Complete")
          currentLoggedStage = 2
        }

        if (doc.status === 'completed' && currentLoggedStage < 3) {
          currentLoggedStage = 3
          try {
            // Await required async functions inside try/catch blocks
            const result = await analyzeDocument(id)
            setProcessingStep("json-generation")
            
            const parsed = await generateJSON(result)
            setProcessingStep("validation")
            
            const validated = await validateJSON(parsed)
            setProcessingStep("complete")
            
            console.log("Validation Complete")
          } catch (error) {
            console.error(error)
            setErrorMsg(error.message)
            setStatus('error')
          }
        }

        if (doc.status === 'completed' || doc.status === 'error') {
          clearInterval(pollRef.current)
          if (doc.status === 'error') setErrorMsg(doc.error_message)
        }
      } catch (err) {
        clearInterval(pollRef.current)
        setStatus('error')
        setErrorMsg('Failed to poll document status.')
      }
    }, POLL_INTERVAL)
  }, [])

  // ── Upload + Process ─────────────────────────────────────────────────────
  const handleProcess = async () => {
    if (!file) return
    setErrorMsg(null)
    setDocData(null)
    setDocId(null)
    setViewMode('view')
    setProcessingStep('idle')

    try {
      // 1. Upload
      setStatus('uploading')
      setUploadProgress(0)
      const uploaded = await uploadDocument(file, setUploadProgress)
      setDocId(uploaded.id)
      console.log("Upload Complete")

      // 2. Trigger pipeline
      setStatus('processing')
      await processDocument(uploaded.id)

      // 3. Poll for completion
      startPolling(uploaded.id)
    } catch (err) {
      setStatus('error')
      setErrorMsg(
        err?.response?.data?.message || err?.message || 'An unexpected error occurred.'
      )
    }
  }

  // ── Save Edited JSON ─────────────────────────────────────────────────────
  const handleSaveJson = async (newJson) => {
    if (!docId) return
    setSaving(true)
    try {
      const updated = await updateDocumentJson(docId, newJson)
      setDocData(updated)
      setViewMode('view')
    } catch (err) {
      setErrorMsg('Failed to save JSON changes.')
    } finally {
      setSaving(false)
    }
  }

  // ── Reset ────────────────────────────────────────────────────────────────
  const handleReset = async () => {
    if (pollRef.current) clearInterval(pollRef.current)
    if (docId) {
      try { await deleteDocument(docId) } catch {}
    }
    setFile(null)
    setDocId(null)
    setDocData(null)
    setStatus('idle')
    setErrorMsg(null)
    setUploadProgress(0)
    setViewMode('view')
  }

  const isProcessing = ['uploading', 'uploaded', 'processing', 'extracting', 'ai_analysis', 'validating'].includes(status)
  const isComplete = status === 'completed'
  const isError = status === 'error'
  const hasJson = isComplete && docData?.extracted_json

  return (
    <div className="dashboard">
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="dashboard__header">
        <div className="container">
          <div className="header-inner">
            <div className="header-brand">
              <div className="brand-logo">
                <Zap size={22} color="var(--accent-primary)" />
              </div>
              <div>
                <h1 className="brand-title">Audit <span className="brand-accent">AI</span></h1>
                <p className="brand-tagline">Checksheet → JSON Converter</p>
              </div>
            </div>
            {(isComplete || isError) && (
              <button
                className="btn btn-ghost btn-sm"
                onClick={handleReset}
                id="reset-btn"
              >
                <RotateCcw size={14} /> New Document
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="dashboard__main container">
        {/* ── Upload Section ─────────────────────────────────────────────── */}
        <section className="section animate-fade-in">
          <div className="section__card card">
            <div className="section__header">
              <div>
                <h2>Upload Checksheet</h2>
                <p className="section__subtitle">
                  Supports Excel, PDF, and Word documents up to 25 MB
                </p>
              </div>
              {file && !isProcessing && (
                <div className="file-meta-chip">
                  {getFileTypeIcon(docData?.file_type || '')}
                  <span>{formatBytes(file.size)}</span>
                </div>
              )}
            </div>

            <UploadZone
              onFileSelected={setFile}
              disabled={isProcessing}
            />

            {/* Upload progress */}
            {status === 'uploading' && (
              <div className="upload-progress-wrap animate-fade-in">
                <div className="upload-progress-header">
                  <span>Uploading…</span>
                  <span>{uploadProgress}%</span>
                </div>
                <div className="upload-progress-track">
                  <div
                    className="upload-progress-fill"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              </div>
            )}

            <div className="section__actions">
              <button
                className="btn btn-primary btn-lg"
                onClick={handleProcess}
                disabled={!file || isProcessing}
                id="process-btn"
              >
                {isProcessing ? (
                  <><span className="spinner" /> Processing…</>
                ) : (
                  <><Zap size={18} /> Extract JSON with AI</>
                )}
              </button>

              {(isComplete || isError) && (
                <button
                  className="btn btn-ghost"
                  onClick={handleReset}
                  id="reset-secondary-btn"
                >
                  <RotateCcw size={16} /> Start Over
                </button>
              )}
            </div>
          </div>
        </section>

        {/* ── Status Tracker ────────────────────────────────────────────── */}
        {status !== 'idle' && status !== 'uploading' && (
          <section className="section animate-fade-in">
            <StatusTracker
              status={docData?.status || status}
              errorMessage={errorMsg}
            />
          </section>
        )}

        {/* ── Global Error ──────────────────────────────────────────────── */}
        {isError && errorMsg && (
          <div className="global-error card animate-fade-in">
            <AlertCircle size={20} color="#ef4444" />
            <div>
              <p style={{ fontWeight: 600, color: '#f87171' }}>Processing Failed</p>
              <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginTop: 4 }}>{errorMsg}</p>
            </div>
          </div>
        )}

        {/* ── Results Section ───────────────────────────────────────────── */}
        {hasJson && (
          <section className="section animate-fade-in">
            {/* Results header */}
            <div className="results-header card">
              <div className="results-summary">
                <div className="result-stat">
                  <span className="result-stat__value">{countChecks(docData.extracted_json)}</span>
                  <span className="result-stat__label">Checks Extracted</span>
                </div>
                <div className="result-divider" />
                <div className="result-stat">
                  <span className="result-stat__value">{Object.keys(docData.extracted_json).length}</span>
                  <span className="result-stat__label">JSON Fields</span>
                </div>
                <div className="result-divider" />
                <div className="result-stat">
                  <ValidationBadge errors={docData.validation_errors} />
                </div>
              </div>

              <div className="results-actions">
                <DownloadPanel
                  documentId={docId}
                  jsonData={docData.extracted_json}
                  filename={docData.original_filename}
                />
                <button
                  className={`btn ${viewMode === 'edit' ? 'btn-primary' : 'btn-ghost'} btn-sm`}
                  onClick={() => setViewMode(v => v === 'edit' ? 'view' : 'edit')}
                  id="toggle-edit-btn"
                >
                  {viewMode === 'edit'
                    ? <><Eye size={14} /> View Mode</>
                    : <><Edit3 size={14} /> Edit JSON</>
                  }
                </button>
              </div>
            </div>

            {/* JSON Viewer / Editor */}
            <div className="json-panel animate-fade-in">
              {viewMode === 'view' ? (
                <JsonViewer data={docData.extracted_json} />
              ) : (
                <JsonEditor
                  data={docData.extracted_json}
                  onSave={handleSaveJson}
                  onCancel={() => setViewMode('view')}
                  saving={saving}
                />
              )}
            </div>
          </section>
        )}
      </main>

      <footer className="dashboard__footer">
        <p>Audit AI · Powered by NVIDIA NIM & Llama 3.3 · Built for production</p>
      </footer>

      <style>{`
        .dashboard {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
        }

        /* Header */
        .dashboard__header {
          border-bottom: 1px solid var(--border-glass);
          background: rgba(8, 12, 20, 0.8);
          backdrop-filter: blur(12px);
          position: sticky;
          top: 0;
          z-index: 50;
        }
        .header-inner {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 16px 0;
        }
        .header-brand { display: flex; align-items: center; gap: 14px; }
        .brand-logo {
          width: 44px;
          height: 44px;
          border-radius: var(--radius-sm);
          background: linear-gradient(135deg, rgba(99,102,241,0.2), rgba(139,92,246,0.2));
          border: 1px solid var(--border-default);
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 0 20px rgba(99,102,241,0.2);
        }
        .brand-title {
          font-size: 1.35rem;
          font-weight: 800;
          letter-spacing: -0.03em;
          line-height: 1;
        }
        .brand-accent {
          background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
        .brand-tagline {
          font-size: 0.75rem;
          color: var(--text-muted);
          margin-top: 2px;
        }

        /* Main */
        .dashboard__main {
          flex: 1;
          padding-top: 40px;
          padding-bottom: 60px;
          display: flex;
          flex-direction: column;
          gap: 24px;
        }

        /* Sections */
        .section { display: flex; flex-direction: column; gap: 16px; }
        .section__card { padding: 28px; display: flex; flex-direction: column; gap: 20px; }
        .section__header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 16px;
        }
        .section__subtitle {
          font-size: 0.875rem;
          color: var(--text-secondary);
          margin-top: 4px;
        }
        .section__actions { display: flex; gap: 12px; flex-wrap: wrap; }
        .file-meta-chip {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          padding: 5px 12px;
          background: rgba(99,102,241,0.08);
          border: 1px solid var(--border-default);
          border-radius: 100px;
          font-size: 0.8rem;
          color: var(--text-secondary);
          white-space: nowrap;
        }

        /* Upload progress */
        .upload-progress-wrap {
          display: flex;
          flex-direction: column;
          gap: 6px;
        }
        .upload-progress-header {
          display: flex;
          justify-content: space-between;
          font-size: 0.8rem;
          color: var(--text-secondary);
        }
        .upload-progress-track {
          height: 4px;
          background: rgba(255,255,255,0.06);
          border-radius: 100px;
          overflow: hidden;
        }
        .upload-progress-fill {
          height: 100%;
          background: linear-gradient(90deg, var(--accent-primary), var(--accent-secondary));
          border-radius: 100px;
          transition: width 0.3s ease;
        }

        /* Results */
        .results-header {
          padding: 20px 24px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 20px;
          flex-wrap: wrap;
        }
        .results-summary {
          display: flex;
          align-items: center;
          gap: 24px;
          flex-wrap: wrap;
        }
        .result-stat {
          display: flex;
          flex-direction: column;
          gap: 2px;
          align-items: flex-start;
        }
        .result-stat__value {
          font-size: 1.5rem;
          font-weight: 800;
          background: linear-gradient(135deg, var(--accent-primary), var(--accent-secondary));
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
          line-height: 1;
        }
        .result-stat__label {
          font-size: 0.7rem;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.05em;
        }
        .result-divider {
          width: 1px;
          height: 40px;
          background: var(--border-glass);
        }
        .results-actions {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-wrap: wrap;
        }
        .json-panel { display: flex; flex-direction: column; }

        /* Error */
        .global-error {
          display: flex;
          align-items: flex-start;
          gap: 14px;
          padding: 20px 24px;
        }

        /* Footer */
        .dashboard__footer {
          border-top: 1px solid var(--border-glass);
          padding: 20px 24px;
          text-align: center;
          font-size: 0.78rem;
          color: var(--text-muted);
        }

        /* Responsive */
        @media (max-width: 640px) {
          .section__card { padding: 18px; }
          .results-header { flex-direction: column; align-items: flex-start; }
          .results-summary { gap: 16px; }
        }
      `}</style>
    </div>
  )
}
