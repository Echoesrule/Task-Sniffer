"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { StatCard } from "@/components/ui/stat-card"
import { mockAnalytics, mockMatchDistribution } from "@/data/mock"
import { motion } from "framer-motion"
import { Send, CalendarCheck, Trophy, TrendingUp, BarChart3 } from "lucide-react"
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, LineChart, Line, CartesianGrid } from "recharts"
import { useState } from "react"

const timeRanges = ["7d", "30d", "90d", "All"]

const funnelData = [
  { stage: "Discovered", count: 247, pct: 100 },
  { stage: "Shortlisted", count: 42, pct: 17 },
  { stage: "Applied", count: 12, pct: 4.9 },
  { stage: "Interview", count: 3, pct: 1.2 },
  { stage: "Offer", count: 0, pct: 0 },
]

const matchColors = ["#00d68f", "#6c5ce7", "#ffaa00", "#ff3d71"]
const matchPie = [
  { name: "Excellent", value: mockMatchDistribution.excellent },
  { name: "Good", value: mockMatchDistribution.good },
  { name: "Fair", value: mockMatchDistribution.fair },
  { name: "Poor", value: mockMatchDistribution.poor },
]

const sourceData = mockAnalytics.top_sources.map(s => ({
  name: s.source.charAt(0).toUpperCase() + s.source.slice(1),
  jobs: s.total_jobs,
  match: Math.round(s.avg_match_score * 100),
  applications: s.application_count,
}))

const weeklyData = [
  { week: "Week 1", match: 0.52, applied: 2 },
  { week: "Week 2", match: 0.61, applied: 3 },
  { week: "Week 3", match: 0.68, applied: 4 },
  { week: "Week 4", match: 0.76, applied: 3 },
]

export default function AnalyticsPage() {
  const [range, setRange] = useState("30d")

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <div className="flex-1 ml-[240px]">
        <Header title="Analytics" />
        <main className="p-6 max-w-[1400px] mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <motion.div className="grid grid-cols-2 lg:grid-cols-4 gap-4 flex-1"
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
              <StatCard icon={Send} label="Applications" value={mockAnalytics.total_applications} />
              <StatCard icon={CalendarCheck} label="Interviews" value={3} />
              <StatCard icon={Trophy} label="Offers" value={0} sublabel="Keep going!" />
              <StatCard icon={TrendingUp} label="Interview Rate" value="25%" sublabel="3 of 12" />
            </motion.div>
            <div className="flex items-center gap-1 bg-surface border border-border rounded-lg p-1 ml-4 shrink-0">
              {timeRanges.map(r => (
                <button key={r} onClick={() => setRange(r)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                    range === r ? "bg-accent text-white" : "text-text-secondary hover:text-text-primary hover:bg-surface-2"
                  }`}>
                  {r}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Application Funnel */}
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
              className="bg-surface border border-border rounded-xl p-5">
              <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Application Funnel</h3>
              <div className="space-y-2">
                {funnelData.map((item, i) => (
                  <div key={item.stage} className="flex items-center gap-3">
                    <span className="text-xs text-text-secondary w-24 shrink-0">{item.stage}</span>
                    <div className="flex-1 h-7 bg-surface-2 rounded-md overflow-hidden relative">
                      <div
                        className="h-full rounded-md transition-all duration-700"
                        style={{
                          width: `${Math.max(item.pct, 2)}%`,
                          backgroundColor: i === 0 ? "var(--color-accent)" :
                            i === 1 ? "var(--color-blue)" :
                            i === 2 ? "var(--color-green)" :
                            i === 3 ? "var(--color-amber)" : "var(--color-text-muted)"
                        }}
                      />
                      <span className="absolute inset-0 flex items-center px-2 text-[11px] font-medium text-text-primary">
                        {item.count} <span className="text-text-muted ml-1">({item.pct}%)</span>
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>

            {/* Match Distribution */}
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
              className="bg-surface border border-border rounded-xl p-5">
              <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Match Distribution</h3>
              <div className="flex items-center gap-6">
                <div className="w-36 h-36">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={matchPie} dataKey="value" cx="50%" cy="50%" innerRadius={30} outerRadius={60} strokeWidth={0}>
                        {matchPie.map((_, i) => <Cell key={i} fill={matchColors[i]} />)}
                      </Pie>
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="space-y-2 flex-1">
                  {matchPie.map((item, i) => (
                    <div key={item.name} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: matchColors[i] }} />
                        <span className="text-xs text-text-secondary">{item.name}</span>
                      </div>
                      <span className="text-xs font-medium text-text-primary tabular-nums">{item.value}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-border flex items-center justify-between text-xs">
                <span className="text-text-muted">Average score</span>
                <span className="font-medium text-text-primary tabular-nums">{Math.round(mockMatchDistribution.avg_score * 100)}%</span>
              </div>
            </motion.div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Source Performance */}
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
              className="bg-surface border border-border rounded-xl p-5">
              <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Source Performance</h3>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={sourceData} layout="vertical" margin={{ left: 10 }}>
                    <XAxis type="number" tick={{ fontSize: 11, fill: "#8888a0" }} />
                    <YAxis type="category" dataKey="name" tick={{ fontSize: 11, fill: "#8888a0" }} width={80} />
                    <Tooltip contentStyle={{ background: "#1a1a25", border: "1px solid #2a2a3a", borderRadius: 8, fontSize: 12 }} />
                    <Bar dataKey="jobs" fill="#6c5ce7" radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </motion.div>

            {/* Match Score Trend */}
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
              className="bg-surface border border-border rounded-xl p-5">
              <h3 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Match Score Trend</h3>
              <div className="h-48">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={weeklyData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#2a2a3a" />
                    <XAxis dataKey="week" tick={{ fontSize: 11, fill: "#8888a0" }} />
                    <YAxis tick={{ fontSize: 11, fill: "#8888a0" }} domain={[0, 1]} tickFormatter={v => `${Math.round(v * 100)}%`} />
                    <Tooltip contentStyle={{ background: "#1a1a25", border: "1px solid #2a2a3a", borderRadius: 8, fontSize: 12 }}
                      formatter={(v: number) => [`${Math.round(v * 100)}%`, "Avg Match"]} />
                    <Line type="monotone" dataKey="match" stroke="#6c5ce7" strokeWidth={2} dot={{ r: 4, fill: "#6c5ce7" }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </motion.div>
          </div>
        </main>
      </div>
    </div>
  )
}
