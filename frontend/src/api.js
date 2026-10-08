const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

export async function apiRequest(path, { token, ...options } = {}) {
  const headers = new Headers(options.headers)
  if (options.body && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
  }
  if (token) headers.set('Authorization', `Bearer ${token}`)

  let response
  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers })
  } catch (error) {
    if (error.name === 'AbortError') throw error
    throw new Error(`Не удалось связаться с сервером по адресу ${API_URL}.`)
  }

  const data = response.status === 204 ? null : await response.json().catch(() => null)
  if (!response.ok) {
    const detail = typeof data?.detail === 'string' ? data.detail : `Ошибка сервера (${response.status}).`
    const error = new Error(detail)
    error.status = response.status
    throw error
  }
  return data
}

export async function checkApiHealth(signal) {
  let response

  try {
    response = await fetch(`${API_URL}/health`, { signal })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error
    }

    throw new Error(`Не удалось связаться с сервером по адресу ${API_URL}. Проверьте, запущен ли backend.`)
  }

  if (!response.ok) {
    throw new Error(`Сервер ответил с ошибкой ${response.status}. Попробуйте обновить страницу позже.`)
  }

  const data = await response.json()

  if (data.status !== 'ok') {
    throw new Error('Сервер доступен, но не подтвердил готовность. Попробуйте обновить страницу.')
  }

  return data
}

export { API_URL }
