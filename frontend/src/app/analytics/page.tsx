"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { StatCard } from "@/components/ui/stat-card"
import { analyticsService } from "@/services/api"
import { motion } from "framer-motion"
import { Send, CalendarCheck, Trophy, TrendingUp, AlertCircle } from "lucide-react"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts"
import { useEffect, useState } from "react"

const matchColors = ["#00d68f", "#6c5ce7", "#ffaa00", "#ff3d71"]

export default function AnalyticsPage() {
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      analyticsService.overview(), analyticsService.matches(),
      analyticsService.sources(), analyticsService.funnel(),
    ]).then(([overview, matches, sources, funnel]) => {
      if (!cancelled) { setData({ overview, matches, sources, funnel }); setError(null) }
    }).catch((e: any) => { if (!cancelled) setError(e?.message || "Could not load analytics") })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const funnel = data?.funnel
  const funnelItems = funnel ? [
    ["Shortlisted", funnel.shortlisted], ["Applied", funnel.applied],
    ["Interview", funnel.interview], ["Offer", funnel.offered], ["Accepted", funnel.accepted],
  ] as [string, number][] : []
  const funnelMax = Math.max(1, ...funnelItems.map(([, count]) => count))
  const matches = data?.matches
  const matchPie = matches ? [
    { name: "Excellent", value: matches.excellent }, { name: "Good", value: matches.good },
    { name: "Fair", value: matches.fair }, { name: "Poor", value: matches.poor },
  ] : []
  const sources = (data?.sources || []).map((s: any) => ({ name: s.source, jobs: s.total_jobs, applications: s.application_count }))
  const interviews = funnel?.interview || 0
  const applied = funnel?.applied || 0

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <div className="flex-1 ml-[240px]">
        <Header title="Analytics" />
        <main className="p-6 max-w-[1400px] mx-auto space-y-6">
          {loading ? <p className="py-12 text-center text-sm text-text-muted">Loading analytics…</p> : error ? (
            <div role="alert" className="py-12 flex justify-center items-center gap-2 text-sm text-red"><AlertCircle className="w-4 h-4" />{error}</div>
          ) : (
            <>
              <motion.div className="grid grid-cols-2 lg:grid-cols-4 gap-4" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                <StatCard icon={Send} label="Applications" value={data.overview.total_applications} />
                <StatCard icon={CalendarCheck} label="Interviews" value={interviews} />
                <StatCard icon={Trophy} label="Offers" value={funnel.offered} />
                <StatCard icon={TrendingUp} label="Average Match" value={data.overview.avg_match_score == null ? "—" : `${Math.round(data.overview.avg_match_score * 100)}%`} />
              </motion.div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <motion.section className="bg-surface border border-border rounded-xl p-5" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                  <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Application Funnel</h3>
                  {funnelItems.length === 0 ? <p className="text-sm text-text-muted">No application activity yet.</p> : <div className="space-y-2">
                    {funnelItems.map(([stage, count], i) => <div key={stage} className="flex items-center gap-3">
                      <span className="text-xs text-text-secondary w-24">{stage}</span>
                      <div className="flex-1 h-7 bg-surface-2 rounded-md overflow-hidden relative">
                        <div className="h-full rounded-md" style={{ width: `${Math.max(2, count / funnelMax * 100)}%`, backgroundColor: ["#6c5ce7", "#0095ff", "#00d68f", "#ffaa00", "#00d68f"][i] }} />
                        <span className="absolute inset-0 flex items-center px-2 text-[11px] text-text-primary">{count}</span>
                      </div>
                    </div>)}
                  </div>}
                </motion.section>

                <motion.section className="bg-surface border border-border rounded-xl p-5" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                  <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Match Distribution</h3>
                  {matchPie.reduce((sum: number, item: any) => sum + item.value, 0) === 0 ? <p className="text-sm text-text-muted">No match scores available.</p> : <div className="flex items-center gap-6">
                    <div className="w-36 h-36"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={matchPie} dataKey="value" cx="50%" cy="50%" innerRadius={30} outerRadius={60} strokeWidth={0}>{matchPie.map((_: any, i: number) => <Cell key={i} fill={matchColors[i]} />)}</Pie></PieChart></ResponsiveContainer></div>
                    <div className="space-y-2 flex-1">{matchPie.map((item: any, i: number) => <div key={item.name} className="flex items-center justify-between text-xs"><span className="flex items-center gap-2 text-text-secondary"><i className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: matchColors[i] }} />{item.name}</span><span className="text-text-primary">{item.value}</span></div>)}</div>
                  </div>}
                  <div className="mt-3 pt-3 border-t border-border flex justify-between text-xs"><span className="text-text-muted">Average / median score</span><span>{matches.avg_score == null ? "—" : `${Math.round(matches.avg_score * 100)}%`} / {matches.median_score == null ? "—" : `${Math.round(matches.median_score * 100)}%`}</span></div>
                </motion.section>
              </div>

              <motion.section className="bg-surface border border-border rounded-xl p-5" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
                <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Jobs by Source</h3>
                {sources.length === 0 ? <p className="text-sm text-text-muted">No source data available.</p> : <div className="h-64"><ResponsiveContainer width="100%" height="100%"><BarChart data={sources}><XAxis dataKey="name" tick={{ fontSize: 11, fill: "#8888a0" }} /><YAxis tick={{ fontSize: 11, fill: "#8888a0" }} /><Tooltip contentStyle={{ background: "#1a1a25", border: "1px solid #2a2a3a", borderRadius: 8, fontSize: 12 }} /><Bar dataKey="jobs" fill="#6c5ce7" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer></div>}
                <p className="text-xs text-text-muted mt-2">Interview rate from applied jobs: {applied ? `${Math.round(interviews / applied * 100)}%` : "—"}</p>
              </motion.section>
            </>
          )}
        </main>
      </div>
    </div>
  )
}
