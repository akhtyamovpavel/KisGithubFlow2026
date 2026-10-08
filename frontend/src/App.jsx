import { useEffect, useState } from 'react'
import { Link, NavLink, Route, Routes } from 'react-router-dom'
import { API_URL, checkApiHealth } from './api.js'

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

function AuthPage({ mode }) {
  const isLogin = mode === 'login'
  const title = isLogin ? 'С возвращением' : 'Создаём аккаунт'
  const description = isLogin ? 'Войдите, чтобы управлять своими объявлениями.' : 'Пара минут - и можно делиться находками с соседями.'

  return (
    <PageFrame eyebrow={isLogin ? 'ВХОД' : 'РЕГИСТРАЦИЯ'} title={title} description={description}>
      <form className="form-card" onSubmit={(event) => event.preventDefault()}>
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
          <input autoComplete={isLogin ? 'current-password' : 'new-password'} name="password" placeholder="Не менее 8 символов" required type="password" />
        </label>
        <button className="button button-primary form-submit" type="submit">{isLogin ? 'Войти' : 'Зарегистрироваться'}</button>
        <p className="form-note">Авторизация появится вместе с подключением соответствующего API.</p>
        <p className="form-switch">
          {isLogin ? 'Впервые здесь?' : 'Уже есть аккаунт?'}{' '}
          <Link to={isLogin ? '/register' : '/login'}>{isLogin ? 'Создать аккаунт' : 'Войти'}</Link>
        </p>
      </form>
    </PageFrame>
  )
}

function CreateListingPage({ user }) {
  return (
    <PageFrame eyebrow="НОВОЕ ОБЪЯВЛЕНИЕ" title="Дадим вещи вторую жизнь" description="Опишите вещь и подготовьте объявление к публикации.">
      <form className="form-card listing-form" onSubmit={(event) => event.preventDefault()}>
        <label className="field">
          <span>Название</span>
          <input name="title" placeholder="Например, городской велосипед" required />
        </label>
        <label className="field">
          <span>Категория</span>
          <select defaultValue="" name="category" required>
          <option disabled value="">Укажите категорию</option>
            <option>Дом и быт</option>
            <option>Одежда</option>
            <option>Электроника</option>
            <option>Хобби и спорт</option>
          </select>
        </label>
        <label className="field">
          <span>Описание</span>
          <textarea name="description" placeholder="Состояние, особенности и где забрать" rows="4" required />
        </label>
        <label className="field">
          <span>Цена, ₽</span>
          <input min="0" name="price" placeholder="0" type="number" />
        </label>
        <button className="button button-primary form-submit" type="submit">Сохранить черновик</button>
        <p className="form-note">{user ? 'Объявление сохранится в профиле после подключения API.' : <>Для управления объявлением <Link to="/login">войдите</Link> или <Link to="/register">создайте аккаунт</Link>.</>}</p>
      </form>
    </PageFrame>
  )
}

function MyListingsPage({ user }) {
  return (
    <PageFrame eyebrow="ЛИЧНЫЙ КАБИНЕТ" title="Мои объявления" description="Здесь будут храниться черновики и опубликованные объявления.">
      <section className="empty-card">
        <span className="empty-icon" aria-hidden="true">＋</span>
        <h2>{user ? 'Пока нет объявлений' : 'Войдите, чтобы увидеть объявления'}</h2>
        <p>{user ? 'Начнём с первой вещи: объявление подготовится за пару минут.' : 'После входа появятся черновики и публикации.'}</p>
        <Link className="button button-primary" to={user ? '/listings/new' : '/login'}>{user ? 'Создать объявление' : 'Войти'}</Link>
      </section>
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
    return () => window.removeEventListener('storage', syncUser)
  }, [])

  return (
    <div className="app-shell">
      <Header user={user} />
      <ApiStatus />
      <Routes>
        <Route element={<CatalogPage />} path="/" />
        <Route element={<AuthPage mode="login" />} path="/login" />
        <Route element={<AuthPage mode="register" />} path="/register" />
        <Route element={<CreateListingPage user={user} />} path="/listings/new" />
        <Route element={<MyListingsPage user={user} />} path="/my-listings" />
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
