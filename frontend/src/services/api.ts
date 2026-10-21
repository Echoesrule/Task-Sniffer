const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

function getAuthToken(): string | null {
  if (typeof window === "undefined") return null
  try {
    return localStorage.getItem("auth_token") || localStorage.getItem("access_token") || null
  } catch {
    return null
  }
}

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  }
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
  search: (query: string) => fetchAPI<{ jobs: any[]; total: number }>("/jobs/search", { method: "POST", body: JSON.stringify({ query }) }),
  stats: () => fetchAPI<any>("/jobs/stats"),
  analyze: (id: string) => fetchAPI<any>(`/jobs/${id}/analyze`, { method: "POST" }),
}

export const candidateService = {
  getProfile: () => fetchAPI<any>("/candidate/profile"),
  updateProfile: (data: any) => fetchAPI<any>("/candidate/profile", { method: "POST", body: JSON.stringify(data) }),
}

export const applicationsService = {
  list: (status?: string) => fetchAPI<any[]>(`/applications${status ? `?status=${status}` : ""}`),
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
