const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

async function fetchAPI<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", Authorization: "Bearer test-token", ...options?.headers },
    ...options,
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
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
