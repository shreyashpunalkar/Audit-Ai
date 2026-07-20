import { useState } from 'react'
import { CheckCircle, AlertTriangle, Info } from 'lucide-react'
import { getValidationSummary } from '../utils/jsonUtils'

export default function ValidationBadge({ errors }) {
  const [expanded, setExpanded] = useState(false)
  if (!errors) return null

  const { type, text } = getValidationSummary(errors)
  const hasMessages = errors.length > 0

  const icons = {
    success: <CheckCircle size={14} />,
    warning: <AlertTriangle size={14} />,
    error: <AlertTriangle size={14} />,
    info: <Info size={14} />,
  }

  return (
    <div className="validation-badge-wrapper">
      <button
        className={`badge badge-${type} validation-toggle`}
        onClick={() => hasMessages && setExpanded(e => !e)}
        style={{ cursor: hasMessages ? 'pointer' : 'default' }}
        id="validation-badge"
        title={hasMessages ? 'Click to see details' : ''}
      >
        {icons[type]}
        {text}
        {hasMessages && <span style={{ marginLeft: 4 }}>{expanded ? '▲' : '▼'}</span>}
      </button>

      {expanded && hasMessages && (
        <div className="validation-messages animate-fade-in">
          {errors.map((err, i) => {
            const isWarning = err.startsWith('Warning')
            return (
              <div key={i} className={`validation-msg ${isWarning ? 'warning' : 'error'}`}>
                {isWarning ? <AlertTriangle size={13} /> : <AlertTriangle size={13} />}
                <span>{err}</span>
              </div>
            )
          })}
        </div>
      )}

      <style>{`
        .validation-badge-wrapper { display: flex; flex-direction: column; gap: 8px; }
        .validation-toggle { font-size: 0.78rem; }
        .validation-messages {
          display: flex;
          flex-direction: column;
          gap: 4px;
          max-height: 200px;
          overflow-y: auto;
        }
        .validation-msg {
          display: flex;
          align-items: flex-start;
          gap: 6px;
          padding: 6px 10px;
          border-radius: 6px;
          font-size: 0.78rem;
          line-height: 1.4;
        }
        .validation-msg.error {
          background: rgba(239, 68, 68, 0.08);
          color: #f87171;
          border-left: 2px solid #ef4444;
        }
        .validation-msg.warning {
          background: rgba(245, 158, 11, 0.08);
          color: #fbbf24;
          border-left: 2px solid #f59e0b;
        }
        .validation-msg svg { flex-shrink: 0; margin-top: 1px; }
      `}</style>
    </div>
  )
}
