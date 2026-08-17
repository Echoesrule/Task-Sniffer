"use client"

import { Bell, Search, Menu, X, Briefcase, Target, AlertTriangle, Check } from "lucide-react"
import { useState, useRef, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"

const mockNotifications = [
  { id: 1, type: "match", title: "New high-match job", message: "Python Backend Engineer at Safaricom — 92% match", time: "2m ago" },
  { id: 2, type: "status", title: "Application update", message: "Andela screening — moved to interview", time: "15m ago" },
  { id: 3, type: "risk", title: "Risk alert", message: "Job at 'Quick Cash Ltd' flagged — 72% risk", time: "1h ago" },
  { id: 4, type: "match", title: "New high-match job", message: "Full Stack Dev at Cellulant — 85% match", time: "3h ago" },
]

export function Header({ title }: { title: string }) {
  const [showNotifs, setShowNotifs] = useState(false)
  const notifRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setShowNotifs(false)
      }
    }
    document.addEventListener("mousedown", handler)
    return () => document.removeEventListener("mousedown", handler)
  }, [])

  const iconMap = { match: Target, status: Check, risk: AlertTriangle }
  const colorMap = { match: "text-green", status: "text-blue", risk: "text-red" }

  return (
    <header className="h-14 border-b border-border bg-surface/80 backdrop-blur-sm flex items-center justify-between px-6 sticky top-0 z-30">
      <div className="flex items-center gap-4">
        <h1 className="text-base font-semibold text-text-primary">{title}</h1>
      </div>

      <div className="flex items-center gap-3">
        <div className="hidden md:flex items-center gap-2 bg-surface-2 border border-border rounded-lg px-3 py-1.5 w-64">
          <Search className="w-4 h-4 text-text-muted" />
          <input
            type="text"
            placeholder="Search jobs, skills, companies..."
            className="bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none w-full"
          />
          <kbd className="text-[10px] text-text-muted bg-surface-3 px-1.5 py-0.5 rounded border border-border">⌘K</kbd>
        </div>

        <div className="relative" ref={notifRef}>
          <button
            onClick={() => setShowNotifs(!showNotifs)}
            className="relative p-2 rounded-lg hover:bg-surface-2 transition-colors"
          >
            <Bell className="w-4.5 h-4.5 text-text-secondary" />
            <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-accent" />
          </button>

          <AnimatePresence>
            {showNotifs && (
              <motion.div
                initial={{ opacity: 0, y: -5, scale: 0.97 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -5, scale: 0.97 }}
                transition={{ duration: 0.15 }}
                className="absolute right-0 top-full mt-2 w-80 bg-surface border border-border rounded-xl shadow-xl overflow-hidden z-50"
              >
                <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                  <span className="text-sm font-semibold text-text-primary">Notifications</span>
                  <button onClick={() => setShowNotifs(false)} className="text-text-muted hover:text-text-primary">
                    <X className="w-4 h-4" />
                  </button>
                </div>
                <div className="max-h-80 overflow-y-auto">
                  {mockNotifications.map(n => {
                    const Icon = iconMap[n.type as keyof typeof iconMap]
                    const color = colorMap[n.type as keyof typeof colorMap]
                    return (
                      <div key={n.id} className="flex items-start gap-3 px-4 py-3 hover:bg-surface-2 transition-colors cursor-pointer border-b border-border last:border-0">
                        <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${color}`} />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium text-text-primary">{n.title}</p>
                          <p className="text-xs text-text-secondary mt-0.5 truncate">{n.message}</p>
                          <p className="text-[10px] text-text-muted mt-1">{n.time}</p>
                        </div>
                      </div>
                    )
                  })}
                </div>
                <div className="px-4 py-2 border-t border-border">
                  <button className="text-xs text-accent hover:text-accent-hover w-full text-center">View all notifications</button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center">
          <span className="text-xs font-medium text-accent">R</span>
        </div>
      </div>
    </header>
  )
}
