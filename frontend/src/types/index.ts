export interface Job {
  id: string
  title: string
  company: string
  location: string
  country: string
  remote: boolean
  remote_type?: string
  salary?: string
  salary_min?: number
  salary_max?: number
  salary_currency?: string
  description: string
  url: string
  source_url?: string
  canonical_url?: string
  source: string
  skills: string[]
  experience: string
  employment_type?: string
  posted_at?: string
  fetched_at?: string
  match_score?: number | null
  match_breakdown?: MatchBreakdown
  risk_score?: number
  risk_level?: "LOW" | "MEDIUM" | "HIGH"
  risk_flags?: RiskFlag[]
  status: string
  created_at?: string
  url_status?: string
}

export interface MatchBreakdown {
  skills?: number
  experience?: number
  role?: number
  location?: number
  salary?: number
  projects?: number
  freshness?: number
  source_quality?: number
}

export interface RiskFlag {
  check: string
  severity: number
  reason: string
}

export interface Candidate {
  id?: string
  name: string
  email: string
  location: string
  skills: string[]
  experience_level: string
  experience_years?: number
  preferred_locations: string[]
  preferred_roles?: string[]
  salary_min?: number
  salary_max?: number
  salary_currency?: string
  remote_ok: boolean
  bio?: string
}

export interface Application {
  id: string
  job_id: string
  job?: Job
  status: string
  notes: string
  match_score?: number
  risk_score?: number
  created_at?: string
  updated_at?: string
}

export interface ApplicationStats {
  total: number
  by_status: Record<string, number>
  avg_match_score: number | null
  avg_risk_score: number
  acceptance_rate: number
}

export interface SourceStats {
  source: string
  total_jobs: number
  avg_match_score: number | null
  avg_risk_score: number
  application_count: number
}

export interface MatchDistribution {
  excellent: number
  good: number
  fair: number
  poor: number
  avg_score: number | null
  median_score: number | null
}

export interface AnalyticsOverview {
  total_jobs: number
  total_applications: number
  total_shortlisted: number
  total_rejected: number
  avg_match_score: number | null
  avg_risk_score: number
  top_sources: SourceStats[]
}

export interface JobStats {
  total_jobs: number
  by_source: Record<string, number>
  by_country: Record<string, number>
  by_remote: Record<string, number>
  avg_risk_score: number
  avg_match_score: number | null
}

export interface ActivityEvent {
  id: string
  type: "scan" | "match" | "risk" | "apply" | "status"
  message: string
  timestamp: string
}

export interface Notification {
  id: string
  type: "match" | "risk" | "status" | "system"
  title: string
  message: string
  read: boolean
  timestamp: string
}
