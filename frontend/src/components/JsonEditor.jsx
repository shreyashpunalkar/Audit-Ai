import { useState, useEffect } from 'react'
import { Save, X, AlertTriangle } from 'lucide-react'
import { tryParseJson } from '../utils/jsonUtils'

export default function JsonEditor({ data, onSave, onCancel, saving }) {
  const [text, setText] = useState('')
  const [parseError, setParseError] = useState(null)

  useEffect(() => {
    setText(JSON.stringify(data, null, 2))
    setParseError(null)
  }, [data])

  const handleChange = (e) => {
    const val = e.target.value
    setText(val)
    const parsed = tryParseJson(val)
    if (parsed === null && val.trim()) {
      setParseError('Invalid JSON — check syntax before saving')
    } else {
      setParseError(null)
    }
  }

  const handleSave = () => {
    const parsed = tryParseJson(text)
    if (!parsed) {
      setParseError('Cannot save: invalid JSON syntax')
      return
    }
    onSave(parsed)
  }

  return (
    <div className="json-editor card">
      <div className="json-editor__toolbar">
        <div className="flex items-center gap-2">
          <span style={{ fontSize: '0.85rem', fontWeight: 600 }}>Edit JSON</span>
          {parseError && (
            <span className="parse-error-inline">
              <AlertTriangle size={12} /> {parseError}
            </span>
          )}
        </div>
        <div className="flex gap-2">
          <button
            className="btn btn-ghost btn-sm"
            onClick={onCancel}
            id="cancel-edit-btn"
            disabled={saving}
          >
            <X size={14} /> Cancel
          </button>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleSave}
            id="save-json-btn"
            disabled={!!parseError || saving}
          >
            {saving ? <span className="spinner" style={{width:14,height:14}} /> : <Save size={14} />}
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      <textarea
        className="json-textarea"
        value={text}
        onChange={handleChange}
        spellCheck={false}
        id="json-editor-textarea"
        aria-label="JSON editor"
      />

      <style>{`
        .json-editor {
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .json-editor__toolbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 14px 16px;
          border-bottom: 1px solid var(--border-glass);
          gap: 12px;
          flex-wrap: wrap;
        }
        .parse-error-inline {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          font-size: 0.75rem;
          color: #f87171;
          background: rgba(239,68,68,0.1);
          padding: 3px 8px;
          border-radius: 6px;
        }
        .json-textarea {
          flex: 1;
          min-height: 500px;
          background: rgba(0,0,0,0.3);
          border: none;
          outline: none;
          color: #86efac;
          font-family: var(--font-mono);
          font-size: 0.8125rem;
          line-height: 1.7;
          padding: 16px;
          resize: vertical;
          caret-color: var(--accent-primary);
        }
        .json-textarea::selection {
          background: rgba(99, 102, 241, 0.3);
        }
      `}</style>
    </div>
  )
}
