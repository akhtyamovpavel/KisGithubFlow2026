import { useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import {
  API_URL,
  apiRequest,
  checkApiHealth,
  createListing,
  loadCategories,
  loadMyListings,
  registerUser,
  signIn,
} from './api.js'

const LISTING_STATUS_LABELS = {
  draft: 'Черновик',
  pending: 'На модерации',
  published: 'Опубликовано',
  rejected: 'Отклонено',
}

function readUser() {
  try {
    return JSON.parse(localStorage.getItem('marketplace-user'))
  } catch {
    return null
  }
}

function ApiStatus() {
  const [state, setState] = useState({ status: 'loading', message: '' })
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()

    setState({ status: 'loading', message: '' })
    checkApiHealth(controller.signal)
      .then(() => setState({ status: 'ready', message: 'Сервис доступен' }))
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setState({ status: 'error', message: error.message })
        }
      })

    return () => controller.abort()
  }, [attempt])

  if (state.status === 'loading') {
    return <div className="api-status api-status--loading" role="status">Проверяем связь с сервером</div>
  }

  if (state.status === 'error') {
    return (
      <div className="api-status api-status--error" role="alert">
        <span>{state.message}</span>
        <button className="text-button" type="button" onClick={() => setAttempt((value) => value + 1)}>
          Повторить
        </button>
      </div>
    )
  }

  return <div className="api-status api-status--ready" role="status">{state.message}</div>
}

function Header({ user }) {
  return (
    <header className="site-header">
      <Link className="brand" to="/" aria-label="Рядом, на главную">
        <span className="brand-mark" aria-hidden="true">р</span>
        <span>рядом</span>
      </Link>
      <nav className="main-nav" aria-label="Основная навигация">
        <NavLink end to="/">Каталог</NavLink>
        {user ? (
          <>
            <NavLink to="/listings/new">Разместить</NavLink>
            <NavLink to="/my-listings">Мои объявления</NavLink>
            {user.role === 'moderator' && <NavLink to="/moderation">Модерация</NavLink>}
            <span className="user-label">{user.name || 'Мой профиль'}</span>
          </>
        ) : (
          <>
            <NavLink to="/login">Войти</NavLink>
            <NavLink className="nav-cta" to="/register">Создать аккаунт</NavLink>
          </>
        )}
      </nav>
    </header>
  )
}

function PageFrame({ eyebrow, title, description, children }) {
  return (
    <main className="page-shell">
      <div className="page-heading">
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {children}
    </main>
  )
}

function CatalogPage() {
  return (
    <PageFrame
      eyebrow="МАРКЕТПЛЕЙС ОБЪЯВЛЕНИЙ"
      title={<>Хорошие вещи<br />находятся рядом</>}
      description="Находим полезное в своём районе: от любимой книги до нового велосипеда."
    >
      <section className="catalog-panel" aria-label="Каталог объявлений">
        <div className="catalog-toolbar">
          <span className="result-count">Скоро здесь появятся объявления</span>
          <span className="location-pill"><span aria-hidden="true">⌖</span> Город не выбран</span>
        </div>
        <div className="empty-state">
          <div className="empty-illustration" aria-hidden="true">
            <span className="sun"></span>
            <span className="package package-back"></span>
            <span className="package package-front"></span>
            <span className="plant">✳</span>
          </div>
          <h2>Каталог готовится к открытию</h2>
          <p>Пока подключаем каталог. Уже можно подготовить объявление о своей вещи.</p>
          <Link className="button button-primary" to="/listings/new">Разместить объявление</Link>
        </div>
      </section>
    </PageFrame>
  )
}

function AuthPage({ mode, onAuthenticated }) {
  const navigate = useNavigate()
  const isLogin = mode === 'login'
  const title = isLogin ? 'С возвращением' : 'Создаём аккаунт'
  const description = isLogin ? 'Управление объявлениями доступно после входа.' : 'Пара минут - и можно делиться находками с соседями.'
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)

    const formData = new FormData(event.currentTarget)
    const email = formData.get('email')
    const password = formData.get('password')

    try {
      let user
      if (isLogin) {
        user = await signIn(email, password)
      } else {
        user = await registerUser({
          email,
          displayName: formData.get('name'),
          password,
        })
      }

      onAuthenticated(user)
      navigate('/listings/new')
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PageFrame eyebrow={isLogin ? 'ВХОД' : 'РЕГИСТРАЦИЯ'} title={title} description={description}>
      <form className="form-card" onSubmit={handleSubmit}>
        {error && <div className="form-error" role="alert">{error}</div>}
        {!isLogin && (
          <label className="field">
            <span>Как к вам обращаться</span>
            <input autoComplete="name" name="name" placeholder="Например, Аня" required />
          </label>
        )}
        <label className="field">
          <span>Электронная почта</span>
            <input autoComplete="email" name="email" placeholder="name@example.com" required type="email" />
        </label>
        <label className="field">
          <span>Пароль</span>
          <input autoComplete={isLogin ? 'current-password' : 'new-password'} minLength={isLogin ? undefined : 12} name="password" placeholder="Не менее 12 символов" required type="password" />
        </label>
        <button className="button button-primary form-submit" disabled={submitting} type="submit">{submitting ? 'Подождите' : isLogin ? 'Войти' : 'Зарегистрироваться'}</button>
        <p className="form-switch">
          {isLogin ? 'Первый раз?' : 'Уже есть аккаунт?'}{' '}
          <Link to={isLogin ? '/register' : '/login'}>{isLogin ? 'Создать аккаунт' : 'Войти'}</Link>
        </p>
      </form>
    </PageFrame>
  )
}

function ModerationPhoto({ submissionId, photo, token, compact = false }) {
  const [source, setSource] = useState('')
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    let objectUrl
    fetch(`${API_URL}/moderation/queue/${submissionId}/photos/${photo.id}`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error('Не удалось загрузить фотографию')
        return response.blob()
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        setSource(objectUrl)
      })
      .catch((error) => {
        if (error.name !== 'AbortError') setFailed(true)
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [photo.id, submissionId, token])

  return <figure className={`moderation-photo${compact ? ' moderation-photo--compact' : ''}`}>
    {source ? <img alt={photo.original_filename} src={source} /> : <div className="moderation-photo-placeholder" aria-label={failed ? 'Фотография недоступна' : 'Загружаем фотографию'}>{failed ? 'Фото недоступно' : 'Загрузка…'}</div>}
    {!compact && <figcaption>{photo.original_filename}</figcaption>}
  </figure>
}

function ModerationQueuePage({ user }) {
  const [items, setItems] = useState([])
  const [selected, setSelected] = useState(null)
  const [state, setState] = useState('loading')
  const [error, setError] = useState('')
  const token = localStorage.getItem('marketplace-token')

  useEffect(() => {
    if (!user || user.role !== 'moderator') {
      setState('forbidden')
      return
    }
    const controller = new AbortController()
    apiRequest('/moderation/queue', { token, signal: controller.signal })
      .then((data) => { setItems(data); setState('ready') })
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') {
          setError(requestError.status === 401 ? 'Войдите снова, чтобы продолжить.' : requestError.message)
          setState('error')
        }
      })
    return () => controller.abort()
  }, [user, token])

  async function openSubmission(id) {
    setError('')
    try {
      setSelected(await apiRequest(`/moderation/queue/${id}`, { token }))
    } catch (requestError) {
      setError(requestError.message)
      if (requestError.status === 404) {
        setItems((current) => current.filter((item) => item.id !== id))
        setSelected(null)
      }
    }
  }

  if (state === 'forbidden') {
    return <PageFrame eyebrow="МОДЕРАЦИЯ" title="Доступ ограничен" description="Очередь доступна только пользователям с ролью модератора.">
      <Link className="button button-primary" to="/login">Войти под аккаунтом модератора</Link>
    </PageFrame>
  }

  return <PageFrame eyebrow="РАБОЧЕЕ МЕСТО МОДЕРАТОРА" title="Очередь объявлений" description="Объявления расположены от самых ранних заявок к новым.">
    {state === 'loading' && <p className="queue-message" role="status">Загружаем очередь…</p>}
    {state === 'error' && <div className="queue-message queue-message--error" role="alert">{error}</div>}
    {state === 'ready' && <div className="moderation-layout">
      <section className="queue-list" aria-label="Ожидают проверки">
        <div className="queue-toolbar"><strong>{items.length}</strong><span>ожидают проверки</span></div>
        {items.length === 0 ? <div className="queue-empty"><h2>Очередь пуста</h2><p>Новые объявления появятся здесь после отправки на проверку.</p></div> : items.map((item) => <article className={`queue-item${selected?.id === item.id ? ' queue-item--selected' : ''}`} key={item.id}>
          <div className="queue-item-heading"><h2>{item.title}</h2><time dateTime={item.submitted_at}>{new Date(item.submitted_at).toLocaleString('ru-RU')}</time></div>
          <p className="queue-meta">{item.author.display_name} · {item.category_name}</p>
          <div className="queue-photos" aria-label={`Фотографий: ${item.photos.length}`}>
            {item.photos.length ? item.photos.slice(0, 4).map((photo) => <ModerationPhoto compact key={photo.id} photo={photo} submissionId={item.id} token={token} />) : <span className="photo-chip photo-chip--empty">Без фотографий</span>}
            {item.photos.length > 4 && <span className="photo-chip">+{item.photos.length - 4}</span>}
          </div>
          <button className="text-button queue-open" onClick={() => openSubmission(item.id)} type="button">Открыть карточку →</button>
        </article>)}
      </section>
      <section className="submission-panel" aria-label="Карточка объявления" aria-live="polite">
        {selected ? <>
          <div className="submission-topline"><span>Версия {selected.version}</span><time dateTime={selected.submitted_at}>{new Date(selected.submitted_at).toLocaleString('ru-RU')}</time></div>
          <h2>{selected.title}</h2>
          <p className="submission-price">{new Intl.NumberFormat('ru-RU', { style: 'currency', currency: 'RUB', maximumFractionDigits: 0 }).format(selected.price)}</p>
          <p className="submission-category">{selected.category_name}</p>
          <p className="submission-description">{selected.description}</p>
          <div className="submission-author"><strong>{selected.author.display_name}</strong><a href={`mailto:${selected.author.email}`}>{selected.author.email}</a></div>
          <h3>Фотографии ({selected.photos.length})</h3>
          <div className="submission-photos">{selected.photos.length ? selected.photos.map((photo) => <ModerationPhoto key={photo.id} photo={photo} submissionId={selected.id} token={token} />) : <p className="queue-muted">Фотографии не приложены.</p>}</div>
        </> : <div className="detail-placeholder"><span aria-hidden="true">↖</span><h2>Выберите объявление</h2><p>Полная карточка и фотографии появятся здесь.</p></div>}
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>
    </div>}
  </PageFrame>
}

function CreateListingPage({ user }) {
  const [categories, setCategories] = useState([])
  const [categoryState, setCategoryState] = useState('loading')
  const [categoryError, setCategoryError] = useState('')
  const [categoryAttempt, setCategoryAttempt] = useState(0)
  const [formError, setFormError] = useState('')
  const [createdListing, setCreatedListing] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (!user) {
      setCategoryState('ready')
      return undefined
    }

    const controller = new AbortController()
    setCategoryState('loading')
    loadCategories(controller.signal)
      .then((items) => {
        setCategories(items)
        setCategoryState('ready')
        setCategoryError('')
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setCategoryState('error')
          setCategoryError(error.message)
        }
      })

    return () => controller.abort()
  }, [user, categoryAttempt])

  async function handleSubmit(event) {
    event.preventDefault()
    const form = event.currentTarget
    setFormError('')
    setCreatedListing(null)
    setSubmitting(true)

    const formData = new FormData(event.currentTarget)
    const payload = {
      title: formData.get('title').trim(),
      description: formData.get('description').trim(),
      price: formData.get('price'),
      category_id: Number(formData.get('category_id')),
    }

    try {
      const listing = await createListing(payload)
      setCreatedListing(listing)
      form.reset()
    } catch (error) {
      setFormError(error.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (!user) {
    return (
      <PageFrame eyebrow="НОВОЕ ОБЪЯВЛЕНИЕ" title="Создание объявления доступно после входа" description="Объявления сохраняются в личном кабинете.">
        <Link className="button button-primary" to="/login">Войти</Link>
      </PageFrame>
    )
  }

  return (
    <PageFrame eyebrow="НОВОЕ ОБЪЯВЛЕНИЕ" title="Дадим вещи вторую жизнь" description="Опишите вещь и подготовьте объявление к публикации.">
      <form className="form-card listing-form" onSubmit={handleSubmit}>
        {categoryState === 'loading' && <div className="form-status" role="status">Загружаем категории</div>}
        {categoryState === 'error' && <div className="form-error" role="alert">Не удалось загрузить категории: {categoryError}</div>}
        {categoryState === 'error' && <button className="text-button category-retry" onClick={() => setCategoryAttempt((value) => value + 1)} type="button">Загрузить категории ещё раз</button>}
        {categoryState === 'ready' && categories.length === 0 && <div className="form-error" role="alert">Активные категории пока не найдены. Сохранение объявления временно недоступно.</div>}
        {formError && <div className="form-error" role="alert">{formError}</div>}
        {createdListing && (
          <div className="form-success" role="status">
            <strong>Черновик сохранён</strong>
            <span>Статус: {createdListing.status === 'pending' ? 'на модерации' : 'черновик'}</span>
          </div>
        )}
        <label className="field">
          <span>Название</span>
          <input maxLength={200} name="title" placeholder="Например, городской велосипед" required />
        </label>
        <label className="field">
          <span>Категория</span>
          <select defaultValue="" name="category_id" required>
            <option disabled value="">Категория не выбрана</option>
            {categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Описание</span>
          <textarea maxLength={5000} name="description" placeholder="Состояние, особенности и где забрать" rows="4" required />
        </label>
        <label className="field">
          <span>Цена, ₽</span>
          <input min="0" name="price" placeholder="0" required step="0.01" type="number" />
        </label>
        <button className="button button-primary form-submit" disabled={categoryState !== 'ready' || categories.length === 0 || submitting} type="submit">{submitting ? 'Сохраняем' : 'Сохранить черновик'}</button>
        <button className="button button-secondary form-submit" disabled title="Подача станет доступна после подключения проверок и загрузки фотографий." type="button">Подать на модерацию</button>
        <p className="form-note">Подача станет доступна после подключения правил проверки и фотографий.</p>
      </form>
    </PageFrame>
  )
}

function MyListingsPage({ user }) {
  const [listings, setListings] = useState([])
  const [state, setState] = useState('loading')
  const [error, setError] = useState('')

  useEffect(() => {
    if (!user) {
      setState('ready')
      return undefined
    }

    const controller = new AbortController()
    loadMyListings(controller.signal)
      .then((items) => {
        setListings(items)
        setState('ready')
      })
      .catch((requestError) => {
        if (requestError.name !== 'AbortError') {
          setError(requestError.message)
          setState('error')
        }
      })

    return () => controller.abort()
  }, [user])

  return (
    <PageFrame eyebrow="ЛИЧНЫЙ КАБИНЕТ" title="Мои объявления" description="Здесь будут храниться черновики и опубликованные объявления.">
      {error && <div className="form-error" role="alert">{error}</div>}
      {state === 'loading' && user && <div className="form-status" role="status">Загружаем объявления</div>}
      {state === 'ready' && listings.length > 0 && (
        <section aria-label="Список объявлений" className="listing-list">
          {listings.map((listing) => (
            <article className="listing-card" key={listing.id}>
              <div><h2>{listing.title}</h2><p>{listing.description}</p></div>
            <span className="status-pill">{LISTING_STATUS_LABELS[listing.status] || listing.status}</span>
            </article>
          ))}
        </section>
      )}
      {(state === 'ready' && listings.length === 0) || !user ? (
        <section className="empty-card">
          <span className="empty-icon" aria-hidden="true">＋</span>
          <h2>{user ? 'Пока нет объявлений' : 'Для просмотра нужен вход'}</h2>
          <p>{user ? 'Начнём с первой вещи: объявление подготовится за пару минут.' : 'После входа появятся черновики и публикации.'}</p>
          <Link className="button button-primary" to={user ? '/listings/new' : '/login'}>{user ? 'Создать объявление' : 'Войти'}</Link>
        </section>
      ) : null}
    </PageFrame>
  )
}

function NotFoundPage() {
  return (
    <PageFrame eyebrow="СТРАНИЦА НЕ НАЙДЕНА" title="Похоже, мы заблудились" description="Такой страницы нет, но хорошие находки всё ещё рядом.">
      <Link className="button button-primary" to="/">Вернуться в каталог</Link>
    </PageFrame>
  )
}

export default function App() {
  const [user, setUser] = useState(readUser)

  useEffect(() => {
    function syncUser() {
      setUser(readUser())
    }

    window.addEventListener('storage', syncUser)
    window.addEventListener('marketplace:user-change', syncUser)
    return () => {
      window.removeEventListener('storage', syncUser)
      window.removeEventListener('marketplace:user-change', syncUser)
    }
  }, [])

  return (
    <div className="app-shell">
      <Header user={user} />
      <ApiStatus />
      <Routes>
        <Route element={<CatalogPage />} path="/" />
        <Route element={<AuthPage mode="login" onAuthenticated={setUser} />} path="/login" />
        <Route element={<AuthPage mode="register" onAuthenticated={setUser} />} path="/register" />
        <Route element={<CreateListingPage user={user} />} path="/listings/new" />
        <Route element={<MyListingsPage user={user} />} path="/my-listings" />
        <Route element={<ModerationQueuePage user={user} />} path="/moderation" />
        <Route element={<NotFoundPage />} path="*" />
      </Routes>
      <footer className="site-footer">
        <span>рядом © 2026</span>
        <span>Маленькие находки меняют день</span>
        <span className="api-address">API: {API_URL}</span>
      </footer>
    </div>
  )
}
