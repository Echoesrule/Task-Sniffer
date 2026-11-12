"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react"
import { authService } from "@/services/api"

export type AuthUser = { user_id: string; email: string; role: string }
export type AuthStatus = "loading" | "authenticated" | "unauthenticated"

type AuthContextValue = {
  user: AuthUser | null
  status: AuthStatus
  refresh: () => Promise<AuthUser | null>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [status, setStatus] = useState<AuthStatus>("loading")

  const refresh = useCallback(async () => {
    try {
      const me = await authService.me()
      setUser(me)
      setStatus("authenticated")
      return me
    } catch {
      setUser(null)
      setStatus("unauthenticated")
      return null
    }
  }, [])

  // Restore the cookie session once on load. The API layer transparently
  // refreshes an expired access token when the refresh cookie is still valid.
  useEffect(() => {
    void refresh()
  }, [refresh])

  // A protected request that cannot be recovered marks the session as gone.
  useEffect(() => {
    const onUnauthorized = () => {
      setUser(null)
      setStatus("unauthenticated")
    }
    window.addEventListener("auth:unauthorized", onUnauthorized)
    return () => window.removeEventListener("auth:unauthorized", onUnauthorized)
  }, [])

  const logout = useCallback(async () => {
    await authService.logout()
    setUser(null)
    setStatus("unauthenticated")
  }, [])

  const value = useMemo(
    () => ({ user, status, refresh, logout }),
    [user, status, refresh, logout]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext)
  if (!context) throw new Error("useAuth must be used within an AuthProvider")
  return context
}
