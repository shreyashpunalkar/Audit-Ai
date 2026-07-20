import { useState, useMemo } from 'react'
import { Search, ChevronRight, ChevronDown, Copy, Check } from 'lucide-react'
import { copyToClipboard } from '../utils/jsonUtils'

// ─── Recursive JSON Node ──────────────────────────────────────────────────────

function JsonNode({ data, depth = 0, searchTerm = '' }) {
  const [collapsed, setCollapsed] = useState(depth > 2)
  const isObj = data !== null && typeof data === 'object' && !Array.isArray(data)
  const isArr = Array.isArray(data)

  if (!isObj && !isArr) {
    // Primitive
    const str = JSON.stringify(data)
    const highlighted = searchTerm && str.toLowerCase().includes(searchTerm.toLowerCase())
    return (
      <span
        className={`json-primitive ${typeof data} ${highlighted ? 'search-highlight' : ''}`}
      >
        {str}
      </span>
    )
  }

  const entries = isArr
    ? data.map((v, i) => [i, v])
    : Object.entries(data)

  if (entries.length === 0) {
    return <span className="json-empty">{isArr ? '[]' : '{}'}</span>
  }

  const openBrace = isArr ? '[' : '{'
  const closeBrace = isArr ? ']' : '}'

  return (
    <span className="json-node">
      <button
        className="json-collapse-btn"
        onClick={() => setCollapsed(c => !c)}
        aria-label={collapsed ? 'Expand' : 'Collapse'}
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
      </button>
      <span className="json-brace">{openBrace}</span>
      {collapsed ? (
        <span className="json-collapsed-hint" onClick={() => setCollapsed(false)}>
          {isArr ? `${entries.length} items` : `${entries.length} keys`}
        </span>
      ) : (
        <div className="json-children" style={{ paddingLeft: `${(depth + 1) * 16}px` }}>
          {entries.map(([key, val]) => {
            const keyStr = isArr ? null : JSON.stringify(key)
            const highlighted =
              searchTerm &&
              (keyStr?.toLowerCase().includes(searchTerm.toLowerCase()) ||
               JSON.stringify(val)?.toLowerCase().includes(searchTerm.toLowerCase()))
            return (
              <div key={key} className={`json-entry ${highlighted ? 'search-highlight-row' : ''}`}>
                {!isArr && (
                  <span className="json-key">{keyStr}: </span>
                )}
                <JsonNode data={val} depth={depth + 1} searchTerm={searchTerm} />
                <span className="json-comma">,</span>
              </div>
            )
          })}
        </div>
      )}
      <span className="json-brace">{closeBrace}</span>
    </span>
  )
}

// ─── Main Viewer ─────────────────────────────────────────────────────────────

export default function JsonViewer({ data }) {
  const [searchTerm, setSearchTerm] = useState('')
  const [copied, setCopied] = useState(false)

  const jsonStr = useMemo(() => JSON.stringify(data, null, 2), [data])

  const handleCopy = async () => {
    await copyToClipboard(jsonStr)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (!data) return null

  return (
    <div className="json-viewer card">
      {/* Toolbar */}
      <div className="json-viewer__toolbar">
        <div className="search-box">
          <Search size={14} color="var(--text-muted)" />
          <input
            className="search-input"
            type="text"
            placeholder="Search keys or values…"
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            id="json-search"
            aria-label="Search JSON"
          />
          {searchTerm && (
            <button className="search-clear" onClick={() => setSearchTerm('')}>×</button>
          )}
        </div>
        <button
          className="btn btn-ghost btn-sm"
          onClick={handleCopy}
          id="copy-json-btn"
          title="Copy JSON to clipboard"
        >
          {copied ? <Check size={14} color="var(--accent-green)" /> : <Copy size={14} />}
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>

      {/* Tree */}
      <div className="json-viewer__tree" role="tree" aria-label="JSON tree view">
        <JsonNode data={data} depth={0} searchTerm={searchTerm} />
      </div>

      <style>{`
        .json-viewer {
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .json-viewer__toolbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 12px;
          padding: 14px 16px;
          border-bottom: 1px solid var(--border-glass);
        }
        .search-box {
          display: flex;
          align-items: center;
          gap: 8px;
          flex: 1;
          background: rgba(255,255,255,0.04);
          border: 1px solid var(--border-glass);
          border-radius: var(--radius-sm);
          padding: 6px 10px;
        }
        .search-input {
          background: none;
          border: none;
          outline: none;
          color: var(--text-primary);
          font-size: 0.8rem;
          font-family: var(--font-sans);
          flex: 1;
          min-width: 0;
        }
        .search-input::placeholder { color: var(--text-muted); }
        .search-clear {
          background: none;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          font-size: 1rem;
          line-height: 1;
          padding: 0 2px;
        }
        .search-clear:hover { color: var(--text-primary); }

        .json-viewer__tree {
          padding: 16px;
          overflow: auto;
          font-family: var(--font-mono);
          font-size: 0.8125rem;
          line-height: 1.7;
          max-height: 600px;
        }

        .json-node { display: inline; }
        .json-children { display: block; }
        .json-entry { display: flex; align-items: flex-start; flex-wrap: wrap; gap: 2px; }

        .json-collapse-btn {
          background: none;
          border: none;
          cursor: pointer;
          padding: 1px 2px;
          color: var(--text-muted);
          display: inline-flex;
          align-items: center;
          vertical-align: middle;
          border-radius: 3px;
          transition: color var(--transition);
        }
        .json-collapse-btn:hover { color: var(--accent-primary); background: rgba(99,102,241,0.1); }

        .json-collapsed-hint {
          color: var(--text-muted);
          font-size: 0.75rem;
          cursor: pointer;
          padding: 0 6px;
          border-radius: 4px;
          background: rgba(255,255,255,0.04);
          border: 1px solid var(--border-glass);
        }
        .json-collapsed-hint:hover { color: var(--text-accent); }

        .json-brace { color: var(--text-secondary); font-weight: 600; }
        .json-comma { color: var(--text-muted); }
        .json-empty { color: var(--text-muted); }

        .json-key { color: #93c5fd; }
        .json-primitive.string { color: #86efac; }
        .json-primitive.number { color: #fca5a5; }
        .json-primitive.boolean { color: #c4b5fd; }
        .json-primitive.null { color: var(--text-muted); font-style: italic; }

        .search-highlight { background: rgba(251, 191, 36, 0.25); border-radius: 3px; }
        .search-highlight-row { background: rgba(99, 102, 241, 0.06); border-radius: 4px; }
      `}</style>
    </div>
  )
}
