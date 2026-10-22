"use client"

import { cn } from "@/lib/utils"

interface MatchScoreProps {
  score: number | null | undefined
  size?: "sm" | "md" | "lg"
  showLabel?: boolean
}

export function MatchScore({ score, size = "md", showLabel = true }: MatchScoreProps) {
  if (score == null) {
    return (
      <div className="flex flex-col items-center gap-0.5" aria-label="Match score not available">
        <span className={cn("font-bold tabular-nums text-text-muted", size === "lg" ? "text-xl" : "text-sm")}>—</span>
        {showLabel && size !== "sm" && <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider">Not scored</span>}
      </div>
    )
  }
  const pct = Math.round(score * 100)
  const color = pct >= 80 ? "text-green" : pct >= 60 ? "text-amber" : "text-red"
  const ringColor = pct >= 80 ? "stroke-green" : pct >= 60 ? "stroke-amber" : "stroke-red"
  const bgRing = "stroke-border"

  const dims = { sm: 36, md: 48, lg: 72 }
  const fonts = { sm: "text-xs", md: "text-sm", lg: "text-xl" }
  const d = dims[size]
  const r = (d - 6) / 2
  const circ = 2 * Math.PI * r
  const offset = circ - (circ * pct) / 100

  return (
    <div className="flex flex-col items-center gap-0.5">
      <div className="relative" style={{ width: d, height: d }}>
        <svg width={d} height={d} className="-rotate-90">
          <circle cx={d/2} cy={d/2} r={r} fill="none" strokeWidth={size === "lg" ? 4 : 3} className={bgRing} />
          <circle cx={d/2} cy={d/2} r={r} fill="none" strokeWidth={size === "lg" ? 4 : 3}
            className={ringColor} strokeDasharray={circ} strokeDashoffset={offset}
            strokeLinecap="round" style={{ transition: "stroke-dashoffset 1s ease-out" }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={cn("font-bold tabular-nums", color, fonts[size])}>{pct}</span>
        </div>
      </div>
      {showLabel && size !== "sm" && (
        <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider">Match</span>
      )}
    </div>
  )
}
