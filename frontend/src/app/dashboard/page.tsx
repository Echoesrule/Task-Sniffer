"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { StatCard } from "@/components/ui/stat-card"
import { MatchScore } from "@/components/ui/match-score"
import { RiskBadge } from "@/components/ui/risk-badge"
import { StatCardSkeleton } from "@/components/ui/skeletons"
import { jobsService, applicationsService } from "@/services/api"
import { timeAgo } from "@/lib/utils"
import { motion } from "framer-motion"
import {
  Briefcase, Target, Send, CalendarCheck,
  MapPin, Building2, Clock, Zap, ChevronRight,
  Search
} from "lucide-react"
import Link from "next/link"
import { useState, useEffect } from "react"

const STALE_THRESHOLD_HOURS = 24

export default function DashboardPage() {
  const [stats, setStats] = useState<any>(null)
  const [recentJobs, setRecentJobs] = useState<any[]>([])
  const [applicationStats, setApplicationStats] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.allSettled([
      jobsService.stats(),
      jobsService.list({ page_size: "5" }),
      applicationsService.stats(),
    ])
      .then(([statsResult, listResult, appResult]) => {
        if (cancelled) return
        if (statsResult.status === "rejected") throw statsResult.reason
        setStats(statsResult.value)
        setRecentJobs(listResult.status === "fulfilled" ? listResult.value.jobs || [] : [])
        setApplicationStats(appResult.status === "fulfilled" ? appResult.value : null)
        setError(null)
      })
      .catch(err => {
        if (cancelled) return
        setError(err?.message ?? "Failed to load dashboard data")
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  const greeting = new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening"

  const latest = stats?.latest_created_at
  const isStale = latest ? (Date.now() - new Date(latest).getTime() > STALE_THRESHOLD_HOURS * 3600 * 1000) : false
  const lastUpdated = latest ? timeAgo(latest) : null

  const strongMatches = stats?.strong_matches ?? 0

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <div className="flex-1 ml-[240px]">
        <Header title="Overview" />
        <main className="p-6 max-w-[1400px] mx-auto space-y-8">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            <p className="text-2xl font-bold text-text-primary">{greeting}</p>
            <p className="text-sm text-text-secondary mt-1">
              <Zap className="w-4 h-4 inline text-accent mr-1" />
              {stats ? `${stats.total_jobs} jobs tracked` : "Loading..."}
              {lastUpdated && (
                <span className="ml-2 text-text-muted">
                  • Last updated {lastUpdated}
                  {isStale && " (stale)"}
                </span>
              )}
            </p>
          </motion.div>

          <motion.div className="grid grid-cols-2 lg:grid-cols-4 gap-4"
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1 }}>
            {loading ? (
              Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)
            ) : error ? (
              <div className="col-span-4 text-center text-red text-sm py-4">
                {error}
              </div>
            ) : (
              <>
                <StatCard icon={Briefcase} label="Jobs Found" value={stats?.total_jobs ?? 0} sublabel="from sources" />
                <StatCard icon={Target} label="Strong Matches" value={strongMatches} sublabel="score ≥ 0.75" />
                <StatCard icon={Send} label="Applications" value={applicationStats?.total ?? "—"} sublabel={applicationStats ? "tracked" : "Sign in to view"} />
                <StatCard icon={CalendarCheck} label="Interviews" value={applicationStats?.by_status?.interview ?? "—"} sublabel={applicationStats ? "tracked" : "Sign in to view"} />
              </>
            )}
          </motion.div>

          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.2 }}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-text-primary">Recent Jobs</h2>
              <Link href="/jobs" className="text-xs text-accent hover:text-accent-hover flex items-center gap-1 transition-colors">
                View all jobs <ChevronRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {recentJobs.map((job: any, i: number) => (
                <motion.div key={job.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.3 + i * 0.05 }}
                >
                  <Link href={`/jobs/${job.id}`}>
                    <div className="bg-surface border border-border rounded-xl p-5 hover:border-border-light hover:bg-surface-2 transition-all cursor-pointer group">
                      <div className="flex items-start gap-4">
                        <MatchScore score={job.match_score} size="lg" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-2">
                            <div>
                              <h3 className="text-sm font-semibold text-text-primary group-hover:text-accent transition-colors">
                                {job.title}
                              </h3>
                              <div className="flex items-center gap-2 mt-1 text-xs text-text-secondary">
                                <Building2 className="w-3 h-3" />
                                <span>{job.company}</span>
                                <span className="text-text-muted">·</span>
                                <MapPin className="w-3 h-3" />
                                <span>{job.location || "N/A"}</span>
                              </div>
                            </div>
                            <RiskBadge level={job.risk_level ?? "LOW"} score={job.risk_score} />
                          </div>
                          <div className="flex items-center gap-1.5 mt-3 flex-wrap">
                            {(job.skills || []).slice(0, 5).map((skill: string) => (
                              <span key={skill} className="text-[11px] px-2 py-0.5 rounded-md bg-surface-3 text-text-secondary border border-border">
                                {skill}
                              </span>
                            ))}
                          </div>
                          <div className="flex items-center gap-1.5 mt-2.5 text-[11px] text-text-muted">
                            <Clock className="w-3 h-3" />
                            <span>{job.posted_at ? timeAgo(job.posted_at) : ""}</span>
                            {job.salary && (
                              <>
                                <span className="text-text-muted">·</span>
                                <span className="text-text-secondary">{job.salary}</span>
                              </>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </Link>
                </motion.div>
              ))}
              {recentJobs.length === 0 && !loading && !error && (
                <div className="col-span-2 text-center text-text-muted text-sm py-8 flex items-center justify-center gap-2">
                  <Search className="w-4 h-4" />
                  No jobs found
                </div>
              )}
            </div>
          </motion.div>
        </main>
      </div>
    </div>
  )
}
