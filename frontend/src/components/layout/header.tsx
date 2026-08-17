"use client"

import { Bell, Search, Menu } from "lucide-react"
import { useState } from "react"

export function Header({ title }: { title: string }) {
  const [showNotifs, setShowNotifs] = useState(false)

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

        <button
          onClick={() => setShowNotifs(!showNotifs)}
          className="relative p-2 rounded-lg hover:bg-surface-2 transition-colors"
        >
          <Bell className="w-4.5 h-4.5 text-text-secondary" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-accent" />
        </button>

        <div className="w-8 h-8 rounded-full bg-accent/20 flex items-center justify-center">
          <span className="text-xs font-medium text-accent">R</span>
        </div>
      </div>
    </header>
  )
}
