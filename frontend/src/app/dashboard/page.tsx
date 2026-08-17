"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { StatCard } from "@/components/ui/stat-card"
import { MatchScore } from "@/components/ui/match-score"
import { RiskBadge } from "@/components/ui/risk-badge"
import { StatCardSkeleton } from "@/components/ui/skeletons"
import { mockJobs, mockAnalytics, mockActivity } from "@/data/mock"
import { timeAgo } from "@/lib/utils"
import { motion } from "framer-motion"
import {
  Briefcase, Target, Send, CalendarCheck,
  MapPin, Building2, Clock, Zap, ChevronRight,
  Check, AlertTriangle, Search
} from "lucide-react"
import Link from "next/link"
import { useState, useEffect } from "react"

export default function DashboardPage() {
  const [loaded, setLoaded] = useState(false)
  useEffect(() => { const t = setTimeout(() => setLoaded(true), 400); return () => clearTimeout(t) }, [])

  const topMatches = [...mockJobs].sort((a, b) => (b.match_score ?? 0) - (a.match_score ?? 0)).slice(0, 4)
  const greeting = new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening"

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <div className="flex-1 ml-[240px]">
        <Header title="Overview" />
        <main className="p-6 max-w-[1400px] mx-auto space-y-8">
          {/* Greeting */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}>
            <p className="text-2xl font-bold text-text-primary">{greeting}, Retro</p>
            <p className="text-sm text-text-secondary mt-1">
              <Zap className="w-4 h-4 inline text-accent mr-1" />
              12 strong opportunities found today. The Hunter is active.
            </p>
          </motion.div>

          {/* Stats */}
          <motion.div className="grid grid-cols-2 lg:grid-cols-4 gap-4"
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.1 }}>
            {loaded ? (
              <>
                <StatCard icon={Briefcase} label="Jobs Found" value={mockAnalytics.total_jobs} change={12} sublabel="from 5 sources" />
                <StatCard icon={Target} label="Strong Matches" value={42} change={8} sublabel="score ≥ 0.75" />
                <StatCard icon={Send} label="Applications" value={mockAnalytics.total_applications} change={3} sublabel="3 pending" />
                <StatCard icon={CalendarCheck} label="Interviews" value={3} sublabel="1 scheduled" />
              </>
            ) : (
              Array.from({ length: 4 }).map((_, i) => <StatCardSkeleton key={i} />)
            )}
          </motion.div>

          {/* Top Matches */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.2 }}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-text-primary">Top Matches</h2>
              <Link href="/jobs" className="text-xs text-accent hover:text-accent-hover flex items-center gap-1 transition-colors">
                View all jobs <ChevronRight className="w-3 h-3" />
              </Link>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {topMatches.map((job, i) => (
                <motion.div key={job.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.3 + i * 0.05 }}
                >
                  <Link href={`/jobs/${job.id}`}>
                    <div className="bg-surface border border-border rounded-xl p-5 hover:border-border-light hover:bg-surface-2 transition-all cursor-pointer group">
                      <div className="flex items-start gap-4">
                        <MatchScore score={job.match_score ?? 0} size="lg" />
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
                                <span>{job.location}</span>
                              </div>
                            </div>
                            <RiskBadge level={job.risk_level ?? "LOW"} score={job.risk_score} />
                          </div>

                          <div className="flex items-center gap-1.5 mt-3 flex-wrap">
                            {job.skills.slice(0, 5).map(skill => (
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
            </div>
          </motion.div>

          {/* Activity Feed */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, delay: 0.4 }}>
            <h2 className="text-lg font-semibold text-text-primary mb-4">Recent Activity</h2>
            <div className="bg-surface border border-border rounded-xl divide-y divide-border">
              {mockActivity.map(event => {
                const iconMap = { scan: Search, match: Target, risk: AlertTriangle, apply: Send, status: Check }
                const colorMap = { scan: "text-blue", match: "text-green", risk: "text-red", apply: "text-accent", status: "text-green" }
                const Icon = iconMap[event.type]
                const color = colorMap[event.type]
                return (
                  <div key={event.id} className="flex items-center gap-3 px-4 py-3">
                    <Icon className={`w-4 h-4 shrink-0 ${color}`} />
                    <span className="text-sm text-text-primary flex-1">{event.message}</span>
                    <span className="text-[11px] text-text-muted shrink-0">{timeAgo(event.timestamp)}</span>
                  </div>
                )
              })}
            </div>
          </motion.div>
        </main>
      </div>
    </div>
  )
}
