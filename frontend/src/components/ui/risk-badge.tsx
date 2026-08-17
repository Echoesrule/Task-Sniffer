import { cn } from "@/lib/utils"
import { ShieldCheck, ShieldAlert, ShieldX } from "lucide-react"

interface RiskBadgeProps {
  level: "LOW" | "MEDIUM" | "HIGH"
  score?: number
  showScore?: boolean
}

export function RiskBadge({ level, score, showScore = true }: RiskBadgeProps) {
  const config = {
    LOW: { icon: ShieldCheck, text: "text-green", bg: "bg-green-muted", label: "Low Risk" },
    MEDIUM: { icon: ShieldAlert, text: "text-amber", bg: "bg-amber-muted", label: "Review" },
    HIGH: { icon: ShieldX, text: "text-red", bg: "bg-red-muted", label: "High Risk" },
  }
  const c = config[level]

  return (
    <div className={cn("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium", c.bg, c.text)}>
      <c.icon className="w-3.5 h-3.5" />
      {showScore && score !== undefined && (
        <span className="tabular-nums">{Math.round(score)}/100</span>
      )}
      <span>{c.label}</span>
    </div>
  )
}
