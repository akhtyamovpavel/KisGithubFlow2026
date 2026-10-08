const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const TOKEN_KEY = 'marketplace-token'

function getErrorMessage(error, fallback) {
  if (typeof error === 'string') return error
  if (Array.isArray(error)) return error.map((item) => item.msg).filter(Boolean).join(' ')
  if (typeof error?.message === 'string') return error.message
  return fallback
}

export async function apiRequest(path, { token = localStorage.getItem(TOKEN_KEY), ...options } = {}) {
  const headers = new Headers(options.headers || {})
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
    const error = new Error(getErrorMessage(data?.detail, `Ошибка сервера (${response.status}).`))
    error.status = response.status
    throw error
  }
  return data
}

async function request(path, options = {}) {
  return apiRequest(path, options)
}

export async function checkApiHealth(signal) {
  const data = await apiRequest('/health', { signal, token: null })
  if (data.status !== 'ok') {
    throw new Error('Сервер доступен, но не подтвердил готовность. Попробуйте обновить страницу.')
  }
  return data
}

export async function signIn(email, password) {
  const tokenResponse = await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
    token: null,
  })
  localStorage.setItem(TOKEN_KEY, tokenResponse.access_token)

  try {
    const user = await request('/auth/me')
    const sessionUser = {
      id: user.id,
      email: user.email,
      name: user.display_name,
      role: user.role,
    }
    localStorage.setItem('marketplace-user', JSON.stringify(sessionUser))
    window.dispatchEvent(new Event('marketplace:user-change'))
    return sessionUser
  } catch (error) {
    localStorage.removeItem(TOKEN_KEY)
    throw error
  }
}

export async function registerUser({ email, displayName, password }) {
  await request('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, display_name: displayName, password }),
    token: null,
  })
  return signIn(email, password)
}

export function loadCategories(signal) {
  return request('/categories', { signal })
}

export function createListing(payload) {
  return request('/listings', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function loadMyListings(signal) {
  return request('/listings/mine', { signal })
}

export function loadPublicListings(signal) {
  return request('/listings', { signal, token: null })
}

export { API_URL }
