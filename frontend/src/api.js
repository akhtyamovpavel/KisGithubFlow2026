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
    error.data = data
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

export function loadSubmissionRules(signal) {
  return request('/listings/submission-rules', { signal, token: null })
}

export function createListing(payload) {
  return request('/listings', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function loadListing(listingId, signal) {
  return request(`/listings/${listingId}`, { signal })
}

export function updateListing(listingId, payload) {
  return request(`/listings/${listingId}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  })
}

export function validateListing(listingId) {
  return request(`/listings/${listingId}/validation`)
}

export function submitListing(listingId) {
  return request(`/listings/${listingId}/submit`, { method: 'POST' })
}

export function loadMyListings(signal) {
  return request('/listings/mine', { signal })
}

export function uploadListingPhoto(listingId, file) {
  const body = new FormData()
  body.append('image', file)
  return request(`/listings/${listingId}/photos`, { method: 'POST', body })
}

export function replaceListingPhoto(listingId, photoId, file) {
  const body = new FormData()
  body.append('image', file)
  return request(`/listings/${listingId}/photos/${photoId}`, { method: 'PUT', body })
}

export function deleteListingPhoto(listingId, photoId) {
  return request(`/listings/${listingId}/photos/${photoId}`, { method: 'DELETE' })
}

export async function loadListingPhoto(photoId, signal) {
  const token = localStorage.getItem(TOKEN_KEY)
  const response = await fetch(`${API_URL}/media/${photoId}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    signal,
  })
  if (!response.ok) throw new Error(`Не удалось загрузить фото (${response.status}).`)
  return response.blob()
}

export function loadPublicListings(signal, query = '', categoryId = '') {
  const search = new URLSearchParams()
  if (query) search.set('q', query)
  if (categoryId) search.set('category_id', categoryId)
  const suffix = search.size ? `?${search.toString()}` : ''
  return request(`/listings${suffix}`, { signal, token: null })
}

export function loadPublicListing(listingId, signal) {
  return request(`/listings/public/${listingId}`, { signal, token: null })
}

export { API_URL }
