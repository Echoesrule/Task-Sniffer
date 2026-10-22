"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { JobCard } from "@/components/jobs/job-card"
import { JobCardSkeleton } from "@/components/ui/skeletons"
import { jobsService } from "@/services/api"
import type { Job } from "@/types"
import { motion } from "framer-motion"
import { Search, SlidersHorizontal, X, AlertCircle } from "lucide-react"
import { useState, useEffect } from "react"

const baseFilters = [
  { label: "Source", options: ["All"] },
  { label: "Remote", options: ["All", "Remote", "On-site"] },
  { label: "Experience", options: ["All", "Junior", "Mid", "Senior"] },
  { label: "Risk", options: ["All", "Low", "Medium", "High"] },
]

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState("")
  const [activeFilters, setActiveFilters] = useState<Record<string, string>>({})
  const [sortBy, setSortBy] = useState("match")
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const pageSize = 20

  useEffect(() => {
    const query = new URLSearchParams(window.location.search).get("q")
    if (query) setSearch(query)
  }, [])

  useEffect(() => {
    let cancelled = false
    const timer = window.setTimeout(() => {
      setLoading(true)
      const request = search.trim()
        ? jobsService.search(search.trim(), page, pageSize)
        : jobsService.list({ page: String(page), page_size: String(pageSize) })
      request
      .then(res => {
        if (cancelled) return
        setJobs(res.jobs as Job[])
        setTotal(res.total ?? 0)
        setError(null)
      })
      .catch(err => {
        if (cancelled) return
        setError(err?.message ?? "Failed to load jobs")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    }, search.trim() ? 250 : 0)
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [page, search])

  const sourceOptions = ["All", ...Array.from(new Set(jobs.map(j => j.source).filter(Boolean))).sort()]
  const filters = baseFilters.map(f => (f.label === "Source" ? { ...f, options: sourceOptions } : f))

  let filtered = [...jobs]

  if (activeFilters.Source && activeFilters.Source !== "All") {
    filtered = filtered.filter(j => j.source.toLowerCase() === activeFilters.Source.toLowerCase())
  }
  if (activeFilters.Remote === "Remote") filtered = filtered.filter(j => j.remote)
  if (activeFilters.Remote === "On-site") filtered = filtered.filter(j => !j.remote)
  if (activeFilters.Experience && activeFilters.Experience !== "All") {
    filtered = filtered.filter(j => j.experience?.toLowerCase() === activeFilters.Experience.toLowerCase())
  }
  if (activeFilters.Risk === "Low") filtered = filtered.filter(j => (j.risk_level ?? "LOW") === "LOW")
  if (activeFilters.Risk === "Medium") filtered = filtered.filter(j => (j.risk_level ?? "LOW") === "MEDIUM")
  if (activeFilters.Risk === "High") filtered = filtered.filter(j => (j.risk_level ?? "LOW") === "HIGH")

  if (sortBy === "match") filtered.sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0))
  else if (sortBy === "risk") filtered.sort((a, b) => (a.risk_score ?? 100) - (b.risk_score ?? 100))
  else if (sortBy === "recent") filtered.sort((a, b) => new Date(b.posted_at ?? 0).getTime() - new Date(a.posted_at ?? 0).getTime())

  const activeCount = Object.values(activeFilters).filter(v => v && v !== "All").length

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <div className="flex-1 ml-[240px]">
        <Header title="Jobs" />
        <main className="p-6 max-w-[1400px] mx-auto space-y-5">
          <div className="flex items-center gap-3">
            <div className="flex-1 flex items-center gap-2 bg-surface border border-border rounded-lg px-3 py-2">
              <Search className="w-4 h-4 text-text-muted shrink-0" />
              <input
                type="text" value={search} onChange={e => { setSearch(e.target.value); setPage(1) }}
                placeholder="Search jobs by title, company, or description..."
                className="bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none w-full"
              />
              {search && (
                <button onClick={() => setSearch("")} className="text-text-muted hover:text-text-primary">
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
            <select value={sortBy} onChange={e => setSortBy(e.target.value)}
              className="bg-surface border border-border rounded-lg px-3 py-2 text-sm text-text-secondary outline-none cursor-pointer">
              <option value="match">Best Match</option>
              <option value="risk">Lowest Risk</option>
              <option value="recent">Most Recent</option>
            </select>
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <SlidersHorizontal className="w-4 h-4 text-text-muted" />
            {filters.map(f => (
              <select key={f.label} value={activeFilters[f.label] || "All"}
                onChange={e => setActiveFilters(prev => ({ ...prev, [f.label]: e.target.value }))}
                className="bg-surface border border-border rounded-lg px-2.5 py-1.5 text-xs text-text-secondary outline-none cursor-pointer">
                {f.options.map(o => <option key={o} value={o}>{f.label === "Risk" && o !== "All" ? `${o} Risk` : o}</option>)}
              </select>
            ))}
            {activeCount > 0 && (
              <button onClick={() => setActiveFilters({})}
                className="text-xs text-accent hover:text-accent-hover flex items-center gap-1">
                <X className="w-3 h-3" /> Clear filters
              </button>
            )}
            <span className="text-xs text-text-muted ml-auto">{filtered.length} jobs</span>
          </div>

          <div className="space-y-3">
            {loading ? (
              Array.from({ length: 6 }).map((_, i) => <JobCardSkeleton key={i} />)
            ) : error ? (
              <div className="text-center py-16">
                <AlertCircle className="w-10 h-10 text-red mx-auto mb-3" />
                <p className="text-text-secondary font-medium">Couldn&apos;t load jobs</p>
                <p className="text-text-muted text-sm mt-1">{error}</p>
              </div>
            ) : filtered.length > 0 ? (
              <>
                {filtered.map((job, i) => (
                  <motion.div key={job.id}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.2, delay: i * 0.03 }}
                  >
                    <JobCard job={job} />
                  </motion.div>
                ))}
                <div className="flex items-center justify-between pt-4">
                  <span className="text-xs text-text-muted">
                    Page {page} {total > 0 && `of ${Math.max(1, Math.ceil(total / pageSize))}`} ({total} total)
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPage(p => Math.max(1, p - 1))}
                      disabled={page <= 1 || loading}
                      className="px-3 py-1.5 text-xs bg-surface border border-border rounded-lg text-text-secondary disabled:opacity-50 disabled:cursor-not-allowed hover:text-text-primary"
                    >
                      Previous
                    </button>
                    <button
                      onClick={() => setPage(p => p + 1)}
                      disabled={loading || page >= Math.ceil(total / pageSize)}
                      className="px-3 py-1.5 text-xs bg-surface border border-border rounded-lg text-text-secondary disabled:opacity-50 disabled:cursor-not-allowed hover:text-text-primary"
                    >
                      Next
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="text-center py-16">
                <Search className="w-10 h-10 text-text-muted mx-auto mb-3" />
                <p className="text-text-secondary font-medium">No jobs match your filters</p>
                <p className="text-text-muted text-sm mt-1">Try adjusting your search criteria</p>
              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}
