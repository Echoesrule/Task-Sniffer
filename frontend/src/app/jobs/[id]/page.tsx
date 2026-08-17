"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { MatchScore } from "@/components/ui/match-score"
import { RiskBadge } from "@/components/ui/risk-badge"
import { mockJobs } from "@/data/mock"
import { useParams } from "next/navigation"
import { motion } from "framer-motion"
import {
  MapPin, Building2, Clock, Globe, DollarSign, Briefcase, ExternalLink,
  Check, AlertTriangle, X as XIcon, ChevronLeft, BookmarkPlus, Send
} from "lucide-react"
import { timeAgo } from "@/lib/utils"
import Link from "next/link"

export default function JobDetailPage() {
  const params = useParams()
  const job = mockJobs.find(j => j.id === params.id)

  if (!job) {
    return (
      <div className="min-h-screen bg-background flex">
        <Sidebar />
        <div className="flex-1 ml-[240px]">
          <Header title="Job Not Found" />
          <div className="p-6 text-center text-text-secondary">Job not found</div>
        </div>
      </div>
    )
  }

  const breakdown = job.match_breakdown ?? {}
  const breakdownEntries = [
    { label: "Skills Match", value: breakdown.skills },
    { label: "Experience Match", value: breakdown.experience },
    { label: "Role Match", value: breakdown.role },
    { label: "Location Match", value: breakdown.location },
    { label: "Salary Match", value: breakdown.salary },
    { label: "Freshness", value: breakdown.freshness },
  ].filter(e => e.value !== undefined)

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <div className="flex-1 ml-[240px]">
        <Header title="Job Detail" />
        <main className="p-6 max-w-[1000px] mx-auto space-y-6">
          <Link href="/jobs" className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-text-primary transition-colors">
            <ChevronLeft className="w-3 h-3" /> Back to jobs
          </Link>

          {/* Header */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            className="bg-surface border border-border rounded-xl p-6">
            <div className="flex items-start gap-5">
              <MatchScore score={job.match_score ?? 0} size="lg" />
              <div className="flex-1">
                <h1 className="text-xl font-bold text-text-primary">{job.title}</h1>
                <div className="flex items-center gap-2 mt-1 text-sm text-text-secondary">
                  <Building2 className="w-4 h-4" />
                  <span>{job.company}</span>
                </div>
                <div className="flex items-center gap-4 mt-3 flex-wrap">
                  <RiskBadge level={job.risk_level ?? "LOW"} score={job.risk_score} />
                  {job.salary && (
                    <span className="text-sm text-text-secondary flex items-center gap-1">
                      <DollarSign className="w-3.5 h-3.5" /> {job.salary}
                    </span>
                  )}
                </div>
                <div className="flex gap-3 mt-4">
                  <a href={job.url} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 bg-accent hover:bg-accent-hover text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors">
                    <Send className="w-4 h-4" /> Apply
                  </a>
                  <button className="inline-flex items-center gap-2 bg-surface-2 border border-border text-text-secondary hover:text-text-primary text-sm font-medium px-4 py-2 rounded-lg transition-colors">
                    <BookmarkPlus className="w-4 h-4" /> Save
                  </button>
                </div>
              </div>
            </div>
          </motion.div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: Overview + Description */}
            <div className="lg:col-span-2 space-y-6">
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
                className="bg-surface border border-border rounded-xl p-5">
                <h2 className="text-sm font-semibold text-text-primary mb-3 uppercase tracking-wider">Overview</h2>
                <div className="grid grid-cols-2 gap-3">
                  <InfoRow icon={MapPin} label="Location" value={job.location} />
                  <InfoRow icon={Globe} label="Remote" value={job.remote ? `${job.remote_type ?? "full"} remote` : "On-site"} />
                  <InfoRow icon={Briefcase} label="Experience" value={job.experience} />
                  <InfoRow icon={Clock} label="Posted" value={job.posted_at ? timeAgo(job.posted_at) : "Unknown"} />
                  <InfoRow icon={Building2} label="Source" value={job.source} />
                  <InfoRow icon={DollarSign} label="Employment" value={job.employment_type ?? "Full-time"} />
                </div>
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
                className="bg-surface border border-border rounded-xl p-5">
                <h2 className="text-sm font-semibold text-text-primary mb-3 uppercase tracking-wider">Description</h2>
                <p className="text-sm text-text-secondary leading-relaxed">{job.description}</p>
              </motion.div>
            </div>

            {/* Right: Match + Risk */}
            <div className="space-y-6">
              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
                className="bg-surface border border-border rounded-xl p-5">
                <h2 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Why This Matches</h2>
                <div className="space-y-2.5">
                  {breakdownEntries.map(e => (
                    <div key={e.label} className="flex items-center justify-between">
                      <span className="text-xs text-text-secondary">{e.label}</span>
                      <div className="flex items-center gap-2">
                        <div className="w-20 h-1.5 bg-surface-3 rounded-full overflow-hidden">
                          <div className="h-full rounded-full transition-all duration-700"
                            style={{
                              width: `${Math.round((e.value ?? 0) * 100)}%`,
                              backgroundColor: (e.value ?? 0) >= 0.8 ? "var(--color-green)" :
                                (e.value ?? 0) >= 0.6 ? "var(--color-amber)" : "var(--color-red)"
                            }}
                          />
                        </div>
                        <span className="text-xs font-medium text-text-primary tabular-nums w-8 text-right">
                          {Math.round((e.value ?? 0) * 100)}%
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 }}
                className="bg-surface border border-border rounded-xl p-5">
                <h2 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Skills</h2>
                <div className="flex flex-wrap gap-1.5">
                  {job.skills.map(skill => (
                    <span key={skill} className="text-xs px-2.5 py-1 rounded-lg bg-surface-3 text-text-secondary border border-border">
                      {skill}
                    </span>
                  ))}
                </div>
              </motion.div>

              <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }}
                className="bg-surface border border-border rounded-xl p-5">
                <h2 className="text-sm font-semibold text-text-primary mb-3 uppercase tracking-wider">Risk Analysis</h2>
                <div className="text-center mb-3">
                  <p className={`text-3xl font-bold tabular-nums ${
                    (job.risk_score ?? 0) < 30 ? "text-green" : (job.risk_score ?? 0) < 60 ? "text-amber" : "text-red"
                  }`}>
                    {job.risk_score}<span className="text-sm font-normal text-text-muted">/100</span>
                  </p>
                  <RiskBadge level={job.risk_level ?? "LOW"} score={job.risk_score} />
                </div>
                {job.risk_flags && job.risk_flags.length > 0 ? (
                  <div className="space-y-2 mt-3">
                    {job.risk_flags.map((flag, i) => (
                      <div key={i} className="flex items-start gap-2 text-xs">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber shrink-0 mt-0.5" />
                        <span className="text-text-secondary">{flag.reason}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="space-y-1.5 mt-2">
                    <VerifiedItem text="Company domain verified" />
                    <VerifiedItem text="Application domain consistent" />
                    <VerifiedItem text="No suspicious patterns detected" />
                  </div>
                )}
              </motion.div>

              <a href={job.url} target="_blank" rel="noopener noreferrer"
                className="flex items-center justify-center gap-2 bg-surface-2 border border-border text-text-secondary hover:text-text-primary text-sm font-medium px-4 py-2.5 rounded-lg transition-colors">
                <ExternalLink className="w-4 h-4" /> View original listing
              </a>
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}

function InfoRow({ icon: Icon, label, value }: { icon: any; label: string; value: string }) {
  return (
    <div className="flex items-center gap-2">
      <Icon className="w-3.5 h-3.5 text-text-muted shrink-0" />
      <span className="text-xs text-text-muted">{label}:</span>
      <span className="text-xs text-text-primary font-medium capitalize">{value}</span>
    </div>
  )
}

function VerifiedItem({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <Check className="w-3.5 h-3.5 text-green shrink-0" />
      <span className="text-text-secondary">{text}</span>
    </div>
  )
}
