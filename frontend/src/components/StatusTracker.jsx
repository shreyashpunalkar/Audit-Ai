import { CheckCircle, Circle, Loader2, AlertCircle } from 'lucide-react'

const STAGES = [
  { id: 'uploaded',    label: 'Uploading',          desc: 'Saving your file securely' },
  { id: 'extracting', label: 'Extracting Content',  desc: 'Parsing document structure' },
  { id: 'ocr',        label: 'OCR Processing',       desc: 'Reading text from document' },
  { id: 'ai_analysis',label: 'AI Analysis',          desc: 'AI is analysing the checksheet' },
  { id: 'validating', label: 'JSON Generation',      desc: 'Building structured JSON' },
  { id: 'completed',  label: 'Validation Complete',  desc: 'Schema validation passed' },
]

function getStageIndex(status) {
  const map = {
    uploaded:    0,
    extracting:  1,
    ocr:         2,
    ai_analysis: 3,
    validating:  4,
    completed:   5,
    processing:  1,
    error:       -1,
  }
  return map[status] ?? 0
}

function StageIcon({ stageIdx, currentIdx, isError }) {
  if (isError) return <AlertCircle size={18} color="var(--accent-red)" />
  if (stageIdx < currentIdx) return <CheckCircle size={18} color="var(--accent-green)" />
  if (stageIdx === currentIdx) return <Loader2 size={18} color="var(--accent-primary)" className="animate-spin" />
  return <Circle size={18} color="var(--text-muted)" />
}

export default function StatusTracker({ status, errorMessage }) {
  const currentIdx = getStageIndex(status)
  const isError = status === 'error'
  const isComplete = status === 'completed'

  if (!status || status === 'idle') return null

  return (
    <div className="status-tracker card animate-fade-in">
      <div className="status-tracker__header">
        <h3>Processing Status</h3>
        {isComplete && <span className="badge badge-success">✓ Complete</span>}
        {isError && <span className="badge badge-error">✗ Error</span>}
        {!isComplete && !isError && <span className="badge badge-info">In Progress</span>}
      </div>

      {/* Progress bar */}
      <div className="progress-bar-track">
        <div
          className={`progress-bar-fill ${isError ? 'error' : ''} ${isComplete ? 'complete' : ''}`}
          style={{ width: isError ? '100%' : `${Math.round((currentIdx / (STAGES.length - 1)) * 100)}%` }}
        />
      </div>

      {/* Stages */}
      <div className="stages-list">
        {STAGES.map((stage, idx) => {
          const isPast = idx < currentIdx
          const isCurrent = idx === currentIdx && !isError && !isComplete
          const isDone = isComplete
          return (
            <div
              key={stage.id}
              className={`stage-item ${isPast || isDone ? 'past' : ''} ${isCurrent ? 'current' : ''}`}
            >
              <div className="stage-icon">
                <StageIcon
                  stageIdx={idx}
                  currentIdx={isComplete ? STAGES.length : currentIdx}
                  isError={isError && idx === currentIdx}
                />
              </div>
              <div className="stage-info">
                <span className="stage-label">{stage.label}</span>
                {isCurrent && <span className="stage-desc">{stage.desc}…</span>}
                {(isPast || isDone) && <span className="stage-desc" style={{color:'var(--accent-green)'}}>Done</span>}
              </div>
              {idx < STAGES.length - 1 && <div className="stage-connector" />}
            </div>
          )
        })}
      </div>

      {isError && errorMessage && (
        <div className="status-error animate-fade-in">
          <AlertCircle size={16} />
          <span>{errorMessage}</span>
        </div>
      )}

      <style>{`
        .status-tracker {
          padding: 24px;
          display: flex;
          flex-direction: column;
          gap: 20px;
        }
        .status-tracker__header {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }
        .progress-bar-track {
          height: 4px;
          background: rgba(255,255,255,0.06);
          border-radius: 100px;
          overflow: hidden;
        }
        .progress-bar-fill {
          height: 100%;
          background: linear-gradient(90deg, var(--accent-primary), var(--accent-secondary));
          border-radius: 100px;
          transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
          background-size: 200% 100%;
        }
        .progress-bar-fill.complete {
          background: linear-gradient(90deg, var(--accent-green), #16a34a);
        }
        .progress-bar-fill.error {
          background: var(--accent-red);
        }
        .stages-list {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
          gap: 8px;
        }
        .stage-item {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 6px;
          text-align: center;
          padding: 10px 6px;
          border-radius: var(--radius-sm);
          transition: background var(--transition);
          position: relative;
        }
        .stage-item.current {
          background: rgba(99, 102, 241, 0.08);
        }
        .stage-item.past {
          opacity: 0.8;
        }
        .stage-icon {
          width: 32px;
          height: 32px;
          border-radius: 50%;
          background: rgba(255,255,255,0.04);
          display: flex;
          align-items: center;
          justify-content: center;
        }
        .stage-label {
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--text-primary);
        }
        .stage-desc {
          font-size: 0.7rem;
          color: var(--text-secondary);
        }
        .status-error {
          display: flex;
          align-items: flex-start;
          gap: 8px;
          padding: 12px 14px;
          background: rgba(239, 68, 68, 0.1);
          border: 1px solid rgba(239, 68, 68, 0.25);
          border-radius: var(--radius-sm);
          color: #f87171;
          font-size: 0.875rem;
        }
      `}</style>
    </div>
  )
}
