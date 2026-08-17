import { cn } from "@/lib/utils"

function Shimmer({ className }: { className?: string }) {
  return <div className={cn("animate-pulse bg-surface-2 rounded", className)} />
}

export function StatCardSkeleton() {
  return (
    <div className="bg-surface border border-border rounded-xl p-4">
      <div className="flex items-center gap-2.5">
        <Shimmer className="w-9 h-9 rounded-lg" />
        <div className="space-y-1.5">
          <Shimmer className="w-20 h-3" />
          <Shimmer className="w-12 h-6" />
        </div>
      </div>
    </div>
  )
}

export function JobCardSkeleton() {
  return (
    <div className="bg-surface border border-border rounded-xl p-4">
      <div className="flex items-start gap-4">
        <Shimmer className="w-12 h-12 rounded-full shrink-0" />
        <div className="flex-1 space-y-2.5">
          <Shimmer className="w-3/4 h-4" />
          <Shimmer className="w-1/2 h-3" />
          <div className="flex gap-1.5">
            <Shimmer className="w-14 h-5 rounded-md" />
            <Shimmer className="w-16 h-5 rounded-md" />
            <Shimmer className="w-12 h-5 rounded-md" />
          </div>
        </div>
      </div>
    </div>
  )
}

export function ChartSkeleton() {
  return (
    <div className="bg-surface border border-border rounded-xl p-6">
      <Shimmer className="w-32 h-4 mb-4" />
      <Shimmer className="w-full h-48 rounded-lg" />
    </div>
  )
}
