"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { cn } from "@/lib/utils"
import {
  LayoutDashboard, Search, Briefcase, FileText,
  BarChart3, Settings, ChevronLeft, ChevronRight,
  Radar
} from "lucide-react"
import { useState } from "react"
import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { authService, getAuthToken } from "@/services/api"

const navItems = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/jobs", label: "Jobs", icon: Search },
  { href: "/applications", label: "Applications", icon: Briefcase },
  { href: "/cv", label: "My CV", icon: FileText },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/settings", label: "Settings", icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()
  const router = useRouter()
  const [collapsed, setCollapsed] = useState(false)
  const [signedIn, setSignedIn] = useState(false)
  useEffect(() => { setSignedIn(Boolean(getAuthToken())) }, [])

  return (
    <aside className={cn(
      "fixed left-0 top-0 z-40 h-screen border-r border-border bg-surface flex flex-col transition-all duration-300",
      collapsed ? "w-[68px]" : "w-[240px]"
    )}>
      <div className="flex items-center gap-2.5 px-4 h-14 border-b border-border shrink-0">
        <div className="w-8 h-8 rounded-lg bg-accent/20 flex items-center justify-center shrink-0">
          <Radar className="w-4.5 h-4.5 text-accent" />
        </div>
        {!collapsed && (
          <span className="text-sm font-semibold tracking-wide text-text-primary">TASK SNIFFER</span>
        )}
      </div>

      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {navItems.map(item => {
          const active = pathname.startsWith(item.href)
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors",
                active
                  ? "bg-accent/15 text-accent font-medium"
                  : "text-text-secondary hover:text-text-primary hover:bg-surface-2"
              )}
            >
              <item.icon className="w-4.5 h-4.5 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          )
        })}
      </nav>

      <div className="border-t border-border p-3">
        <HunterStatus collapsed={collapsed} />
        {!collapsed && <button onClick={() => {
          if (signedIn) { authService.logout(); setSignedIn(false); router.push("/login") }
          else router.push("/login")
        }} className="mt-3 w-full text-left text-xs text-text-secondary hover:text-text-primary px-2">
          {signedIn ? "Sign out" : "Sign in"}
        </button>}
      </div>

      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-20 w-6 h-6 rounded-full bg-surface-2 border border-border flex items-center justify-center text-text-muted hover:text-text-primary transition-colors"
      >
        {collapsed ? <ChevronRight className="w-3 h-3" /> : <ChevronLeft className="w-3 h-3" />}
      </button>
    </aside>
  )
}

function HunterStatus({ collapsed }: { collapsed: boolean }) {
  return (
    <div className={cn("rounded-lg bg-surface-2 border border-border p-3", collapsed && "p-2")}>
      <div className="flex items-center gap-2">
        <div className="relative">
          <div className="w-2 h-2 rounded-full bg-green animate-pulse" />
        </div>
        {!collapsed && (
          <div>
            <p className="text-xs font-semibold text-green uppercase tracking-wider">Job discovery</p>
            <p className="text-[11px] text-text-muted mt-1">Job scans depend on the backend scheduler</p>
          </div>
        )}
      </div>
    </div>
  )
}
