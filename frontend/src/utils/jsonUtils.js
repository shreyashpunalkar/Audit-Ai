/**
 * JSON utility functions for the frontend.
 */

/** Safely parse a JSON string. Returns null on failure. */
export function tryParseJson(str) {
  try {
    return JSON.parse(str)
  } catch {
    return null
  }
}

/** Format bytes to human-readable size string. */
export function formatBytes(bytes, decimals = 1) {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const dm = decimals < 0 ? 0 : decimals
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`
}

/** Format an ISO date string to local date string. */
export function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString()
}

/** Copy text to clipboard. Returns true on success. */
export async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    // Fallback
    const el = document.createElement('textarea')
    el.value = text
    document.body.appendChild(el)
    el.select()
    document.execCommand('copy')
    document.body.removeChild(el)
    return true
  }
}

/** Get file extension label. */
export function getFileTypeLabel(filename) {
  const ext = filename?.split('.').pop()?.toLowerCase()
  const map = {
    xlsx: 'Excel',
    xls: 'Excel',
    pdf: 'PDF',
    docx: 'Word Document',
  }
  return map[ext] || ext?.toUpperCase() || 'Unknown'
}

/** Get icon name for file type. */
export function getFileTypeIcon(fileType) {
  const map = {
    excel: '📊',
    pdf: '📄',
    docx: '📝',
  }
  return map[fileType] || '📎'
}

/** Count checks in extracted JSON. */
export function countChecks(json) {
  if (!json) return 0
  if (Array.isArray(json.checks)) return json.checks.length

  let count = 0

  // Try counting template -> sections -> rows
  if (json.template && Array.isArray(json.template.sections)) {
    for (const section of json.template.sections) {
      if (section && Array.isArray(section.rows)) {
        if (section.section_type !== 'header') {
          count += section.rows.length
        }
      }
    }
    if (count > 0) return count
  }

  // Try counting top-level sections -> rows
  if (Array.isArray(json.sections)) {
    for (const section of json.sections) {
      if (section && Array.isArray(section.rows)) {
        if (section.section_type !== 'header') {
          count += section.rows.length
        }
      }
    }
    if (count > 0) return count
  }

  // Fallback counting any sheets -> sections -> rows
  if (Array.isArray(json.sheets)) {
    for (const sheet of json.sheets) {
      if (sheet && Array.isArray(sheet.sections)) {
        for (const section of sheet.sections) {
          if (section && Array.isArray(section.rows)) {
            if (section.section_type !== 'header') {
              count += section.rows.length
            }
          }
        }
      }
    }
  }

  return count
}

/** Get validation summary text. */
export function getValidationSummary(errors) {
  if (!errors || errors.length === 0) return { type: 'success', text: 'Valid JSON' }
  const hasErrors = errors.some(e => !e.startsWith('Warning'))
  const warnings = errors.filter(e => e.startsWith('Warning'))
  if (hasErrors) return { type: 'error', text: `${errors.length} validation error(s)` }
  if (warnings.length) return { type: 'warning', text: `${warnings.length} warning(s)` }
  return { type: 'success', text: 'Valid JSON' }
}
