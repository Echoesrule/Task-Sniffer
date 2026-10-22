"use client"

import { Bell, Search, X, CircleUserRound } from "lucide-react"
import { useState, useRef, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { useRouter } from "next/navigation"

export function Header({ title }: { title: string }) {
  const [showNotifs, setShowNotifs] = useState(false)
  const [query, setQuery] = useState("")
  const router = useRouter()
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

  const submitSearch = (e: React.FormEvent) => {
    e.preventDefault()
    const value = query.trim()
    if (value) router.push(`/jobs?q=${encodeURIComponent(value)}`)
  }

  return (
    <header className="h-14 border-b border-border bg-surface/80 backdrop-blur-sm flex items-center justify-between px-6 sticky top-0 z-30">
      <div className="flex items-center gap-4">
        <h1 className="text-base font-semibold text-text-primary">{title}</h1>
      </div>

      <div className="flex items-center gap-3">
        <form onSubmit={submitSearch} className="hidden md:flex items-center gap-2 bg-surface-2 border border-border rounded-lg px-3 py-1.5 w-64">
          <Search className="w-4 h-4 text-text-muted" />
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            type="text"
            placeholder="Search jobs, companies, descriptions..."
            className="bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none w-full"
          />
        </form>

        <div className="relative" ref={notifRef}>
          <button
            onClick={() => setShowNotifs(!showNotifs)}
            className="relative p-2 rounded-lg hover:bg-surface-2 transition-colors"
          >
            <Bell className="w-4.5 h-4.5 text-text-secondary" />
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
                <p className="px-4 py-8 text-center text-xs text-text-muted">Notifications are not available yet.</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <div className="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center">
          <CircleUserRound className="w-4 h-4 text-accent" />
        </div>
      </div>
    </header>
  )
}
