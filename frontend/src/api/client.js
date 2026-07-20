import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000, // 2 min for AI processing
})

// ─── Upload ─────────────────────────────────────────────────────────────────

export async function uploadDocument(file, onProgress) {
  const form = new FormData()
  form.append('file', file)
  const res = await api.post('/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded * 100) / e.total))
      }
    },
  })
  return res.data
}

// ─── Process ────────────────────────────────────────────────────────────────

export async function processDocument(documentId) {
  const res = await api.post(`/process/${documentId}`)
  return res.data
}

// ─── Poll Status ────────────────────────────────────────────────────────────

export async function getDocument(documentId) {
  const res = await api.get(`/document/${documentId}`)
  return res.data
}

// ─── Update JSON ─────────────────────────────────────────────────────────────

export async function updateDocumentJson(documentId, jsonData) {
  const res = await api.put(`/document/${documentId}/json`, { json_data: jsonData })
  return res.data
}

// ─── Download ───────────────────────────────────────────────────────────────

export function getDownloadUrl(documentId) {
  return `/api/download/${documentId}`
}

// ─── Delete ─────────────────────────────────────────────────────────────────

export async function deleteDocument(documentId) {
  await api.delete(`/document/${documentId}`)
}

// ─── Health ─────────────────────────────────────────────────────────────────

export async function healthCheck() {
  const res = await api.get('/health')
  return res.data
}

export default api
