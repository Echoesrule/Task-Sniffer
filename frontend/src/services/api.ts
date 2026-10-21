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
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: mergedHeaders,
  })
  if (!res.ok) {
    if (res.status === 401 || res.status === 403) {
      const err = new Error(`Unauthorized: ${res.status}`)
      ;(err as any).status = res.status
      throw err
    }
    const err = new Error(`API error: ${res.status}`)
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
