"use client"

import Link from "next/link"
import type { Job } from "@/types"
import { MatchScore } from "@/components/ui/match-score"
import { RiskBadge } from "@/components/ui/risk-badge"
import { MapPin, Clock, Building2, ExternalLink } from "lucide-react"
import { timeAgo } from "@/lib/utils"

export function JobCard({ job }: { job: Job }) {
  return (
    <Link href={`/jobs/${job.id}`}>
      <div className="bg-surface border border-border rounded-xl p-4 hover:border-border-light hover:bg-surface-2 transition-all cursor-pointer group">
        <div className="flex items-start gap-4">
          <MatchScore score={job.match_score} size="md" />

          <div className="flex-1 min-w-0">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="text-sm font-semibold text-text-primary group-hover:text-accent transition-colors truncate">
                  {job.title}
                </h3>
                <div className="flex items-center gap-2 mt-1 text-xs text-text-secondary">
                  <Building2 className="w-3 h-3 shrink-0" />
                  <span>{job.company}</span>
                  <span className="text-text-muted">·</span>
                  <MapPin className="w-3 h-3 shrink-0" />
                  <span>{job.location}</span>
                  {job.remote && (
                    <>
                      <span className="text-text-muted">·</span>
                      <span className="text-green text-[11px] font-medium">Remote</span>
                    </>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                {job.salary && (
                  <span className="text-xs font-medium text-text-secondary bg-surface-2 px-2 py-1 rounded-md">
                    {job.salary}
                  </span>
                )}
                <RiskBadge level={job.risk_level ?? "LOW"} score={job.risk_score} />
              </div>
            </div>

            <div className="flex items-center gap-1.5 mt-2.5 flex-wrap">
              {job.skills.slice(0, 6).map(skill => (
                <span key={skill} className="text-[11px] px-2 py-0.5 rounded-md bg-surface-3 text-text-secondary border border-border">
                  {skill}
                </span>
              ))}
              {job.skills.length > 6 && (
                <span className="text-[11px] text-text-muted">+{job.skills.length - 6}</span>
              )}
            </div>

            <div className="flex items-center justify-between mt-2.5">
              <div className="flex items-center gap-1.5 text-[11px] text-text-muted">
                <Clock className="w-3 h-3" />
                <span>{job.posted_at ? timeAgo(job.posted_at) : "Unknown"}</span>
                <span className="text-text-muted">·</span>
                <span className="capitalize">{job.source}</span>
              </div>
              <ExternalLink className="w-3.5 h-3.5 text-text-muted group-hover:text-accent transition-colors" />
            </div>
          </div>
        </div>
      </div>
    </Link>
  )
}
