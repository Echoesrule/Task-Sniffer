"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { mockApplications } from "@/data/mock"
import { motion } from "framer-motion"
import { Building2, Clock, ChevronRight, GripVertical } from "lucide-react"
import { timeAgo } from "@/lib/utils"
import Link from "next/link"
import { useState, useRef } from "react"

const columns = [
  { id: "shortlisted", label: "Shortlisted", color: "bg-accent" },
  { id: "applied", label: "Applied", color: "bg-blue" },
  { id: "screening", label: "Screening", color: "bg-amber" },
  { id: "interview", label: "Interview", color: "bg-green" },
  { id: "offered", label: "Offer", color: "bg-green" },
  { id: "rejected", label: "Rejected", color: "bg-red" },
]

export default function ApplicationsPage() {
  const [apps, setApps] = useState(mockApplications)
  const [draggedId, setDraggedId] = useState<string | null>(null)
  const [dragOverCol, setDragOverCol] = useState<string | null>(null)

  const getColumnApps = (status: string) => apps.filter(a => a.status === status)

  const handleDragStart = (e: React.DragEvent, appId: string) => {
    setDraggedId(appId)
    e.dataTransfer.effectAllowed = "move"
    e.dataTransfer.setData("text/plain", appId)
  }

  const handleDragOver = (e: React.DragEvent, colId: string) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
    setDragOverCol(colId)
  }

  const handleDragLeave = () => {
    setDragOverCol(null)
  }

  const handleDrop = (e: React.DragEvent, colId: string) => {
    e.preventDefault()
    const appId = e.dataTransfer.getData("text/plain")
    if (appId) {
      setApps(prev => prev.map(a => a.id === appId ? { ...a, status: colId } : a))
    }
    setDraggedId(null)
    setDragOverCol(null)
  }

  const handleDragEnd = () => {
    setDraggedId(null)
    setDragOverCol(null)
  }

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <div className="flex-1 ml-[240px]">
        <Header title="Applications" />
        <main className="p-6">
          <div className="flex items-center gap-4 mb-6">
            <p className="text-sm text-text-secondary">
              <span className="text-text-primary font-semibold">{apps.length}</span> total applications
            </p>
            <p className="text-xs text-text-muted">Drag cards between columns to update status</p>
          </div>

          <div className="flex gap-4 overflow-x-auto pb-4">
            {columns.map(col => {
              const colApps = getColumnApps(col.id)
              const isOver = dragOverCol === col.id
              return (
                <div key={col.id} className="min-w-[280px] max-w-[300px] flex-1">
                  <div className="flex items-center gap-2 mb-3">
                    <div className={`w-2 h-2 rounded-full ${col.color}`} />
                    <h3 className="text-xs font-semibold text-text-secondary uppercase tracking-wider">{col.label}</h3>
                    <span className="text-[11px] text-text-muted bg-surface-2 px-1.5 py-0.5 rounded-full tabular-nums">
                      {colApps.length}
                    </span>
                  </div>

                  <div
                    className={`space-y-2 min-h-[100px] rounded-lg p-1 transition-colors ${
                      isOver ? "bg-accent/10 ring-2 ring-accent/30" : ""
                    }`}
                    onDragOver={(e) => handleDragOver(e, col.id)}
                    onDragLeave={handleDragLeave}
                    onDrop={(e) => handleDrop(e, col.id)}
                  >
                    {colApps.length > 0 ? colApps.map((app, i) => (
                      <motion.div key={app.id}
                        initial={{ opacity: 0, y: 5 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ duration: 0.2, delay: i * 0.05 }}
                        draggable
                        onDragStart={(e) => handleDragStart(e as unknown as React.DragEvent, app.id)}
                        onDragEnd={handleDragEnd}
                        className={`${draggedId === app.id ? "opacity-40 scale-95" : ""} transition-all`}
                      >
                        <div className="bg-surface border border-border rounded-lg p-3 hover:border-border-light transition-all cursor-grab active:cursor-grabbing group">
                          <div className="flex items-center gap-2">
                            <GripVertical className="w-3 h-3 text-text-muted opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
                            <div className="flex-1 min-w-0">
                              <div className="flex items-start justify-between gap-2">
                                <h4 className="text-sm font-medium text-text-primary truncate">
                                  {app.job?.title ?? "Job"}
                                </h4>
                                {app.match_score !== undefined && (
                                  <span className="text-xs font-bold tabular-nums text-green shrink-0">
                                    {Math.round(app.match_score * 100)}%
                                  </span>
                                )}
                              </div>
                              <div className="flex items-center gap-1.5 mt-1.5 text-[11px] text-text-muted">
                                <Building2 className="w-3 h-3" />
                                <span>{app.job?.company ?? "Company"}</span>
                              </div>
                              <div className="flex items-center justify-between mt-2">
                                <div className="flex items-center gap-1 text-[11px] text-text-muted">
                                  <Clock className="w-3 h-3" />
                                  <span>{app.created_at ? timeAgo(app.created_at) : ""}</span>
                                </div>
                                <Link href={`/jobs/${app.job_id}`} className="text-[11px] text-accent hover:text-accent-hover opacity-0 group-hover:opacity-100 transition-opacity">
                                  View
                                </Link>
                              </div>
                            </div>
                          </div>
                        </div>
                      </motion.div>
                    )) : (
                      <div className={`bg-surface border border-dashed rounded-lg p-4 text-center transition-colors ${
                        isOver ? "border-accent bg-accent/5" : "border-border"
                      }`}>
                        <p className="text-[11px] text-text-muted">
                          {isOver ? "Drop here" : "No applications"}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </main>
      </div>
    </div>
  )
}
