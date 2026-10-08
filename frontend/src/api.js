const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')
const TOKEN_KEY = 'marketplace-access-token'

function getErrorMessage(error, fallback) {
  if (typeof error === 'string') {
    return error
  }

  if (Array.isArray(error)) {
    return error.map((item) => item.msg).filter(Boolean).join(' ')
  }

  if (typeof error?.message === 'string') {
    return error.message
  }

  return fallback
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {})
  const token = localStorage.getItem(TOKEN_KEY)

  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }

  if (options.body) {
    headers.set('Content-Type', 'application/json')
  }

  let response

  try {
    response = await fetch(`${API_URL}${path}`, { ...options, headers })
  } catch (error) {
    if (error.name === 'AbortError') {
      throw error
    }

    throw new Error(`Не удалось связаться с сервером по адресу ${API_URL}.`)
  }
  const data = await response.json().catch(() => null)

  if (!response.ok) {
    const message = getErrorMessage(data?.detail, `Сервер ответил с ошибкой ${response.status}.`)
    throw new Error(message)
  }

  return data
}

export function checkApiHealth(signal) {
  return fetch(`${API_URL}/health`, { signal }).then(async (response) => {
    if (!response.ok) {
      throw new Error(`Сервер ответил с ошибкой ${response.status}. Повторная попытка доступна позже.`)
    }

    const data = await response.json()

    if (data.status !== 'ok') {
      throw new Error('Сервер доступен, но не подтвердил готовность.')
    }

    return data
  }).catch((error) => {
    if (error.name === 'AbortError') {
      throw error
    }

    if (error.message.startsWith('Сервер ответил')) {
      throw error
    }

    throw new Error(`Backend недоступен по адресу ${API_URL}. Сервер backend должен быть запущен.`)
  })
}

export async function signIn(email, password) {
  const tokenResponse = await request('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
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

export { API_URL }
