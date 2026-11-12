"use client"

import { useEffect } from "react"
import { usePathname, useRouter } from "next/navigation"
import { useAuth } from "./auth-provider"

/** Render children only for an authenticated session, otherwise go to /login. */
export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { status } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (status === "unauthenticated") {
      const next = encodeURIComponent(pathname || "/dashboard")
      router.replace(`/login?next=${next}`)
    }
  }, [status, pathname, router])

  if (status === "authenticated") return <>{children}</>

  return (
    <div className="min-h-screen bg-background flex items-center justify-center">
      <p className="text-sm text-text-muted">
        {status === "loading" ? "Checking session…" : "Redirecting to sign in…"}
      </p>
    </div>
  )
}
