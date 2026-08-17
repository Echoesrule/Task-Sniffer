import { cn } from "@/lib/utils"
import { LucideIcon, TrendingUp, TrendingDown } from "lucide-react"

interface StatCardProps {
  icon: LucideIcon
  label: string
  value: string | number
  change?: number
  sublabel?: string
}

export function StatCard({ icon: Icon, label, value, change, sublabel }: StatCardProps) {
  return (
    <div className="bg-surface border border-border rounded-xl p-4 hover:border-border-light transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-lg bg-accent-muted flex items-center justify-center shrink-0">
            <Icon className="w-4.5 h-4.5 text-accent" />
          </div>
          <div>
            <p className="text-xs text-text-muted font-medium uppercase tracking-wider">{label}</p>
            <p className="text-xl font-bold text-text-primary tabular-nums mt-0.5">{value}</p>
          </div>
        </div>
        {change !== undefined && (
          <div className={cn("flex items-center gap-0.5 text-xs font-medium", change >= 0 ? "text-green" : "text-red")}>
            {change >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            <span>{change >= 0 ? "+" : ""}{change}%</span>
          </div>
        )}
      </div>
      {sublabel && <p className="text-[11px] text-text-muted mt-2">{sublabel}</p>}
    </div>
  )
}
