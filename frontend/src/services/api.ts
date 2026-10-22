const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export function getAuthToken(): string | null {
  if (typeof window === "undefined") return null
  try {
    return localStorage.getItem("auth_token") || localStorage.getItem("access_token") || null
  } catch {
    return null
  }
}

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const isFormData = typeof FormData !== "undefined" && options?.body instanceof FormData
  const headers: Record<string, string> = isFormData ? {} : { "Content-Type": "application/json" }
  const token = getAuthToken()
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }
  const mergedHeaders = { ...headers, ...(options?.headers as Record<string, string> | undefined) }
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers: mergedHeaders,
    })
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
    const result = await fetchAPI<{ access_token: string; email: string }>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) })
    if (typeof window !== "undefined") localStorage.setItem("auth_token", result.access_token)
    return result
  },
  register: async (email: string, password: string) => {
    const result = await fetchAPI<{ access_token: string; email: string }>("/auth/register", { method: "POST", body: JSON.stringify({ email, password }) })
    if (typeof window !== "undefined") localStorage.setItem("auth_token", result.access_token)
    return result
  },
  me: () => fetchAPI<{ email: string; user_id: string }>("/auth/me"),
  logout: () => {
    if (typeof window !== "undefined") {
      localStorage.removeItem("auth_token")
      localStorage.removeItem("access_token")
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
    const headers: Record<string, string> = {}
    const token = getAuthToken()
    if (token) headers.Authorization = `Bearer ${token}`
    const res = await fetch(`${API_BASE}/candidate/cv/file`, { headers })
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
