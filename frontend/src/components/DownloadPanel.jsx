import { useState } from 'react'
import { Download, Copy, Check, ExternalLink } from 'lucide-react'
import { copyToClipboard } from '../utils/jsonUtils'
import { getDownloadUrl } from '../api/client'

export default function DownloadPanel({ documentId, jsonData, filename }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    if (!jsonData) return
    await copyToClipboard(JSON.stringify(jsonData, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 2500)
  }

  const handleDownload = () => {
    if (!jsonData) return
    const blob = new Blob([JSON.stringify(jsonData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${filename?.replace(/\.[^.]+$/, '') || 'extracted'}_extracted.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const handleOpenRaw = () => {
    if (!jsonData) return
    const blob = new Blob([JSON.stringify(jsonData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    window.open(url, '_blank')
    setTimeout(() => URL.revokeObjectURL(url), 10000)
  }

  return (
    <div className="download-panel">
      <button
        className="btn btn-primary"
        onClick={handleDownload}
        disabled={!documentId || !jsonData}
        id="download-json-btn"
        title="Download JSON file"
      >
        <Download size={16} />
        Download JSON
      </button>

      <button
        className="btn btn-ghost"
        onClick={handleCopy}
        disabled={!jsonData}
        id="copy-json-action-btn"
        title="Copy JSON to clipboard"
      >
        {copied ? <Check size={16} color="var(--accent-green)" /> : <Copy size={16} />}
        {copied ? 'Copied!' : 'Copy JSON'}
      </button>

      <button
        className="btn btn-ghost"
        onClick={handleOpenRaw}
        disabled={!jsonData}
        id="open-raw-json-btn"
        title="Open raw JSON in new tab"
      >
        <ExternalLink size={16} />
        Open Raw
      </button>

      <style>{`
        .download-panel {
          display: flex;
          gap: 10px;
          flex-wrap: wrap;
        }
      `}</style>
    </div>
  )
}
