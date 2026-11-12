const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null
  const match = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`))
  return match ? decodeURIComponent(match.split("=").slice(1).join("=")) : null
}

function isUnsafeMethod(method: string): boolean {
  return !["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase())
}

// These endpoints must never trigger the automatic refresh/retry loop: a 401
// there means bad credentials or an already-invalid session.
const NO_REFRESH_PATHS = new Set(["/auth/login", "/auth/register", "/auth/refresh"])

function buildHeaders(options: RequestInit | undefined, method: string): Record<string, string> {
  const isFormData = typeof FormData !== "undefined" && options?.body instanceof FormData
  const headers: Record<string, string> = isFormData ? {} : { "Content-Type": "application/json" }
  // Double-submit CSRF protection for cookie-authenticated state changes.
  if (isUnsafeMethod(method)) {
    const csrf = getCookie("csrf_token")
    if (csrf) headers["X-CSRF-Token"] = csrf
  }
  return { ...headers, ...(options?.headers as Record<string, string> | undefined) }
}

let refreshInFlight: Promise<boolean> | null = null

/** Exchange the HttpOnly refresh cookie for a fresh access token. */
async function refreshSession(): Promise<boolean> {
  if (refreshInFlight) return refreshInFlight
  refreshInFlight = (async () => {
    const headers: Record<string, string> = {}
    const csrf = getCookie("csrf_token")
    if (csrf) headers["X-CSRF-Token"] = csrf
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include",
        headers,
      })
      return res.ok
    } catch {
      return false
    } finally {
      refreshInFlight = null
    }
  })()
  return refreshInFlight
}

function notifyUnauthorized(): void {
  if (
    typeof window !== "undefined" &&
    typeof window.dispatchEvent === "function" &&
    typeof Event !== "undefined"
  ) {
    window.dispatchEvent(new Event("auth:unauthorized"))
  }
}

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const method = options?.method || "GET"
  const send = () =>
    fetch(`${API_BASE}${path}`, {
      ...options,
      method,
      credentials: "include",
      headers: buildHeaders(options, method),
    })

  let res: Response
  try {
    res = await send()
    if (res.status === 401 && !NO_REFRESH_PATHS.has(path)) {
      // An expired access cookie is recoverable while the refresh cookie lives.
      if (await refreshSession()) res = await send()
    }
  } catch (e: any) {
    const err = new Error("Network error")
    ;(err as any).status = 0
    throw err
  }
  if (!res.ok) {
    let detail: string | undefined
    try {
      const ct = res.headers.get("content-type") || ""
      if (ct.includes("application/json")) {
        const data = await res.json()
        detail = data?.detail || data?.message || data?.error
      }
    } catch {
      // ignore
    }
    if (res.status === 401) {
      if (!NO_REFRESH_PATHS.has(path)) notifyUnauthorized()
      const err = new Error(detail || "Unauthorized")
      ;(err as any).status = 401
      throw err
    }
    if (res.status === 403) {
      const err = new Error(detail || "Forbidden")
      ;(err as any).status = 403
      throw err
    }
    if (res.status === 404) {
      const err = new Error(detail || "Not found")
      ;(err as any).status = 404
      throw err
    }
    if (res.status === 429) {
      const err = new Error(detail || "Rate limited")
      ;(err as any).status = 429
      throw err
    }
    if (res.status >= 500) {
      const err = new Error(detail || "Server error")
      ;(err as any).status = res.status
      throw err
    }
    const err = new Error(detail || `Request failed (${res.status})`)
    ;(err as any).status = res.status
    throw err
  }
  return res.json()
}

export const jobsService = {
  list: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : ""
    return fetchAPI<{ jobs: any[]; total: number }>(`/jobs${qs}`)
  },
  get: (id: string) => fetchAPI<any>(`/jobs/${id}`),
  search: (query: string, page = 1, page_size = 20) => fetchAPI<{ jobs: any[]; total: number }>("/jobs/search", { method: "POST", body: JSON.stringify({ query, page, page_size }) }),
  stats: () => fetchAPI<any>("/jobs/stats"),
  analyze: (id: string) => fetchAPI<any>(`/jobs/${id}/analyze`, { method: "POST" }),
}

export const authService = {
  login: async (email: string, password: string) => {
    return fetchAPI<{ access_token: string; email: string; role: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) })
  },
  register: async (email: string, password: string) => {
    // Registration is deliberately enumeration-resistant and does not return a
    // token. Sign in immediately afterwards to establish the session.
    await fetchAPI<{ detail: string }>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) })
    return authService.login(email, password)
  },
  me: () => fetchAPI<{ email: string; user_id: string; role: string }>("/auth/me"),
  createTelegramLinkCode: () =>
    fetchAPI<{ code: string; expires_at: string }>("/auth/telegram/link-code", { method: "POST" }),
  isAuthenticated: async () => {
    try {
      await authService.me()
      return true
    } catch {
      return false
    }
  },
  logout: async () => {
    try {
      await fetchAPI<{ detail: string }>("/auth/logout", { method: "POST" })
    } catch {
      // The local session is still considered signed out if the API is down.
    }
  },
}

export const candidateService = {
  getProfile: () => fetchAPI<any>("/candidate/profile"),
  updateProfile: (data: any) => fetchAPI<any>("/candidate/profile", { method: "POST", body: JSON.stringify(data) }),
  getCv: () => fetchAPI<{ filename: string | null; size: number | null }>("/candidate/cv"),
  uploadCv: (file: File) => {
    const body = new FormData()
    body.append("file", file)
    return fetchAPI<any>("/candidate/cv", { method: "POST", body })
  },
  deleteCv: () => fetchAPI<{ message: string }>("/candidate/cv", { method: "DELETE" }),
  downloadCv: async () => {
    const res = await fetch(`${API_BASE}/candidate/cv/file`, { credentials: "include" })
    if (!res.ok) throw new Error(res.status === 404 ? "No CV uploaded" : "Could not download CV")
    return res.blob()
  },
}

export const applicationsService = {
  list: (params?: { status?: string; page?: number; page_size?: number }) => {
    const qs = new URLSearchParams()
    if (params?.status) qs.set("status", params.status)
    if (params?.page) qs.set("page", String(params.page))
    if (params?.page_size) qs.set("page_size", String(params.page_size))
    return fetchAPI<any[]>(`/applications${qs.size ? `?${qs}` : ""}`)
  },
  get: (id: string) => fetchAPI<any>(`/applications/${id}`),
  create: (data: any) => fetchAPI<any>("/applications", { method: "POST", body: JSON.stringify(data) }),
  update: (id: string, data: any) => fetchAPI<any>(`/applications/${id}`, { method: "PATCH", body: JSON.stringify(data) }),
  stats: () => fetchAPI<any>("/applications/stats"),
}

export const analyticsService = {
  overview: () => fetchAPI<any>("/analytics/overview"),
  matches: () => fetchAPI<any>("/analytics/matches"),
  sources: () => fetchAPI<any>("/analytics/sources"),
  funnel: () => fetchAPI<any>("/analytics/applications"),
}
