"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { applicationsService } from "@/services/api"
import { motion } from "framer-motion"
import { Building2, Clock, GripVertical, AlertCircle, RefreshCw } from "lucide-react"
import { timeAgo } from "@/lib/utils"
import Link from "next/link"
import { useCallback, useEffect, useState } from "react"

const columns = [
  { id: "shortlisted", label: "Shortlisted", color: "bg-accent" },
  { id: "applied", label: "Applied", color: "bg-blue" },
  { id: "interview", label: "Interview", color: "bg-green" },
  { id: "offered", label: "Offer", color: "bg-amber" },
  { id: "accepted", label: "Accepted", color: "bg-green" },
  { id: "rejected", label: "Rejected", color: "bg-red" },
  { id: "withdrawn", label: "Withdrawn", color: "bg-surface-3" },
]

export default function ApplicationsPage() {
  const [apps, setApps] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [draggedId, setDraggedId] = useState<string | null>(null)
  const [dragOverCol, setDragOverCol] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const allApps: any[] = []
      for (let page = 1; ; page += 1) {
        const batch = await applicationsService.list({ page, page_size: 100 })
        allApps.push(...batch)
        if (batch.length < 100) break
      }
      setApps(allApps)
      setError(null)
    } catch (e: any) {
      setError(e?.message || "Could not load applications")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  const moveApplication = async (appId: string, status: string) => {
    const previous = apps
    setApps(current => current.map(app => app.id === appId ? { ...app, status } : app))
    setSavingId(appId)
    try {
      const updated = await applicationsService.update(appId, { status })
      setApps(current => current.map(app => app.id === appId ? { ...app, ...updated } : app))
    } catch (e: any) {
      setApps(previous)
      setError(e?.message || "Could not update application status")
    } finally {
      setSavingId(null)
      setDraggedId(null)
      setDragOverCol(null)
    }
  }

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <div className="flex-1 ml-[240px]">
        <Header title="Applications" />
        <main className="p-6">
          <div className="flex items-center gap-4 mb-6">
            <p className="text-sm text-text-secondary"><span className="text-text-primary font-semibold">{apps.length}</span> tracked applications</p>
            <p className="text-xs text-text-muted">Drag cards between columns to update status</p>
            <button onClick={() => void load()} className="ml-auto text-xs text-accent flex items-center gap-1"><RefreshCw className="w-3 h-3" /> Refresh</button>
          </div>
          {error && <div role="alert" className="mb-4 flex items-center gap-2 text-sm text-red"><AlertCircle className="w-4 h-4" />{error}</div>}
          {loading ? <p className="py-12 text-center text-sm text-text-muted">Loading applications…</p> : apps.length === 0 && !error ? (
            <div className="py-16 text-center text-sm text-text-muted">No applications yet. Track a job to see it here.</div>
          ) : (
            <div className="flex gap-4 overflow-x-auto pb-4">
              {columns.map(col => {
                const colApps = apps.filter(app => app.status === col.id)
                const isOver = dragOverCol === col.id
                return (
                  <div key={col.id} className="min-w-[280px] max-w-[300px] flex-1">
                    <div className="flex items-center gap-2 mb-3">
                      <div className={`w-2 h-2 rounded-full ${col.color}`} />
                      <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">{col.label}</h3>
                      <span className="text-[11px] text-text-muted bg-surface-2 px-1.5 py-0.5 rounded-full">{colApps.length}</span>
                    </div>
                    <div className={`space-y-2 min-h-[100px] rounded-lg p-1 ${isOver ? "bg-accent/10 ring-2 ring-accent/30" : ""}`}
                      onDragOver={e => { e.preventDefault(); setDragOverCol(col.id) }}
                      onDragLeave={() => setDragOverCol(null)}
                      onDrop={e => { e.preventDefault(); const id = e.dataTransfer.getData("text/plain"); const current = apps.find(app => app.id === id); if (id && current?.status !== col.id) void moveApplication(id, col.id) }}>
                      {colApps.map((app, i) => (
                        <motion.div key={app.id} initial={{ opacity: 0, y: 5 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2, delay: i * 0.03 }}
                          draggable={savingId !== app.id} onDragStart={e => { setDraggedId(app.id); (e as unknown as React.DragEvent<HTMLDivElement>).dataTransfer.setData("text/plain", app.id) }}
                          onDragEnd={() => { setDraggedId(null); setDragOverCol(null) }}
                          className={`${draggedId === app.id ? "opacity-40" : ""} ${savingId === app.id ? "opacity-60" : ""}`}>
                          <div className="bg-surface border border-border rounded-lg p-3 hover:border-border-light group cursor-grab">
                            <div className="flex items-center gap-2"><GripVertical className="w-3 h-3 text-text-muted shrink-0" />
                              <div className="flex-1 min-w-0">
                                <h4 className="text-sm font-medium text-text-primary truncate">{app.job_title || "Job"}</h4>
                                <div className="flex items-center gap-1.5 mt-1.5 text-[11px] text-text-muted"><Building2 className="w-3 h-3" /><span>{app.company || "Company"}</span></div>
                                <div className="flex items-center justify-between mt-2">
                                  <span className="flex items-center gap-1 text-[11px] text-text-muted"><Clock className="w-3 h-3" />{app.created_at ? timeAgo(app.created_at) : ""}</span>
                                  <Link href={`/jobs/${app.job_id}`} className="text-[11px] text-accent">View</Link>
                                </div>
                              </div>
                            </div>
                          </div>
                        </motion.div>
                      ))}
                      {colApps.length === 0 && <div className="bg-surface border border-dashed border-border rounded-lg p-4 text-center text-[11px] text-text-muted">{isOver ? "Drop here" : "No applications"}</div>}
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </main>
      </div>
    </div>
  )
}
