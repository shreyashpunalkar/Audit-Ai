import { useState, useCallback, useRef } from 'react'
import { Upload, FileText, Table, FileType } from 'lucide-react'
import { formatBytes, getFileTypeLabel } from '../utils/jsonUtils'

const ALLOWED_TYPES = {
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'excel',
  'application/vnd.ms-excel': 'excel',
  'application/pdf': 'pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
}

const ALLOWED_EXTS = ['.xlsx', '.xls', '.pdf', '.docx']
const MAX_SIZE = 25 * 1024 * 1024

const FILE_TYPE_ICONS = {
  excel: <Table size={20} color="#22c55e" />,
  pdf: <FileText size={20} color="#ef4444" />,
  docx: <FileType size={20} color="#6366f1" />,
}

function validateFile(file) {
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  if (!ALLOWED_EXTS.includes(ext)) {
    return `Unsupported file type "${ext}". Allowed: ${ALLOWED_EXTS.join(', ')}`
  }
  if (file.size > MAX_SIZE) {
    return `File is too large (${formatBytes(file.size)}). Maximum is 25 MB.`
  }
  return null
}

export default function UploadZone({ onFileSelected, disabled }) {
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const inputRef = useRef()

  const handleFile = useCallback((file) => {
    if (!file) return
    const err = validateFile(file)
    if (err) {
      setError(err)
      setSelectedFile(null)
      return
    }
    setError(null)
    setSelectedFile(file)
    onFileSelected(file)
  }, [onFileSelected])

  const onDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    if (disabled) return
    const file = e.dataTransfer.files[0]
    handleFile(file)
  }, [handleFile, disabled])

  const onDragOver = (e) => { e.preventDefault(); if (!disabled) setDragging(true) }
  const onDragLeave = () => setDragging(false)
  const onInputChange = (e) => handleFile(e.target.files[0])
  const openPicker = () => { if (!disabled) inputRef.current?.click() }

  const ext = selectedFile ? '.' + selectedFile.name.split('.').pop().toLowerCase() : null
  const typeKey = ext ? {
    '.xlsx': 'excel', '.xls': 'excel', '.pdf': 'pdf', '.docx': 'docx'
  }[ext] : null

  return (
    <div className="upload-zone-wrapper">
      <div
        className={`upload-zone card ${dragging ? 'dragging' : ''} ${disabled ? 'disabled' : ''}`}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={openPicker}
        id="upload-dropzone"
        role="button"
        tabIndex={0}
        onKeyDown={e => e.key === 'Enter' && openPicker()}
        aria-label="Upload checksheet document"
      >
        <input
          ref={inputRef}
          type="file"
          accept={ALLOWED_EXTS.join(',')}
          style={{ display: 'none' }}
          onChange={onInputChange}
          id="file-input"
        />

        {!selectedFile ? (
          <div className="upload-zone__empty">
            <div className="upload-icon-ring">
              <Upload size={28} color="var(--accent-primary)" />
            </div>
            <div>
              <p className="upload-zone__title">Drop your checksheet here</p>
              <p className="upload-zone__subtitle">or <span className="upload-zone__link">browse files</span></p>
            </div>
            <div className="upload-zone__formats">
              {[
                { icon: <Table size={14} />, label: 'Excel', color: '#22c55e' },
                { icon: <FileText size={14} />, label: 'PDF', color: '#ef4444' },
                { icon: <FileType size={14} />, label: 'DOCX', color: '#6366f1' },
              ].map(f => (
                <span key={f.label} className="format-chip" style={{ color: f.color, borderColor: f.color + '33' }}>
                  {f.icon} {f.label}
                </span>
              ))}
            </div>
            <p className="upload-zone__limit">Maximum file size: 25 MB</p>
          </div>
        ) : (
          <div className="upload-zone__selected">
            <div className="file-preview-icon">{FILE_TYPE_ICONS[typeKey] || <FileText size={20} />}</div>
            <div className="file-preview-info">
              <p className="file-preview-name">{selectedFile.name}</p>
              <p className="file-preview-meta">
                {getFileTypeLabel(selectedFile.name)} · {formatBytes(selectedFile.size)}
              </p>
            </div>
            <button
              className="btn btn-ghost btn-sm"
              onClick={e => { e.stopPropagation(); setSelectedFile(null); setError(null); onFileSelected(null) }}
              style={{ marginLeft: 'auto' }}
              id="change-file-btn"
            >
              Change
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="upload-error animate-fade-in">
          <span>⚠️</span> {error}
        </div>
      )}

      <style>{`
        .upload-zone-wrapper { display: flex; flex-direction: column; gap: 10px; }

        .upload-zone {
          padding: 40px 32px;
          cursor: pointer;
          border: 2px dashed var(--border-glass);
          transition: all 0.2s ease;
          user-select: none;
          outline: none;
        }
        .upload-zone:hover:not(.disabled) {
          border-color: var(--accent-primary);
          background: rgba(99, 102, 241, 0.04);
        }
        .upload-zone:focus-visible {
          border-color: var(--accent-primary);
          box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.2);
        }
        .upload-zone.dragging {
          border-color: var(--accent-primary);
          background: rgba(99, 102, 241, 0.08);
          box-shadow: 0 0 0 4px rgba(99, 102, 241, 0.15), var(--shadow-glow);
          transform: scale(1.005);
        }
        .upload-zone.disabled { opacity: 0.5; cursor: not-allowed; }

        .upload-zone__empty {
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 14px;
          text-align: center;
        }
        .upload-icon-ring {
          width: 64px;
          height: 64px;
          border-radius: 50%;
          background: rgba(99, 102, 241, 0.1);
          border: 2px solid rgba(99, 102, 241, 0.25);
          display: flex;
          align-items: center;
          justify-content: center;
          animation: pulse-glow 3s ease-in-out infinite;
        }
        .upload-zone__title {
          font-size: 1.1rem;
          font-weight: 600;
          color: var(--text-primary);
        }
        .upload-zone__subtitle {
          font-size: 0.875rem;
          color: var(--text-secondary);
          margin-top: 4px;
        }
        .upload-zone__link {
          color: var(--text-accent);
          font-weight: 600;
          text-decoration: underline;
          text-underline-offset: 3px;
        }
        .upload-zone__formats {
          display: flex;
          gap: 8px;
          flex-wrap: wrap;
          justify-content: center;
        }
        .format-chip {
          display: inline-flex;
          align-items: center;
          gap: 4px;
          padding: 4px 10px;
          border-radius: 100px;
          font-size: 0.75rem;
          font-weight: 600;
          border: 1px solid;
          background: rgba(0,0,0,0.2);
        }
        .upload-zone__limit {
          font-size: 0.75rem;
          color: var(--text-muted);
        }

        .upload-zone__selected {
          display: flex;
          align-items: center;
          gap: 14px;
        }
        .file-preview-icon {
          width: 44px;
          height: 44px;
          border-radius: var(--radius-sm);
          background: rgba(99, 102, 241, 0.1);
          border: 1px solid var(--border-glass);
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
        }
        .file-preview-name {
          font-size: 0.9rem;
          font-weight: 600;
          color: var(--text-primary);
          word-break: break-all;
        }
        .file-preview-meta {
          font-size: 0.8rem;
          color: var(--text-secondary);
          margin-top: 2px;
        }

        .upload-error {
          padding: 10px 14px;
          background: rgba(239, 68, 68, 0.1);
          border: 1px solid rgba(239, 68, 68, 0.3);
          border-radius: var(--radius-sm);
          color: #f87171;
          font-size: 0.875rem;
          display: flex;
          align-items: center;
          gap: 8px;
        }
      `}</style>
    </div>
  )
}
