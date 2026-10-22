"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { authService } from "@/services/api"
import { Radar, AlertCircle } from "lucide-react"

export default function LoginPage() {
  const router = useRouter()
  const [mode, setMode] = useState<"login" | "register">("login")
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      if (mode === "login") await authService.login(email, password)
      else await authService.register(email, password)
      router.replace("/dashboard")
    } catch (err: any) { setError(err?.message || "Could not authenticate") }
    finally { setBusy(false) }
  }

  return <main className="min-h-screen bg-background flex items-center justify-center p-6">
    <section className="w-full max-w-md bg-surface border border-border rounded-xl p-8">
      <div className="flex items-center gap-3 mb-7"><Radar className="w-7 h-7 text-accent" /><h1 className="text-lg font-semibold">Task Sniffer</h1></div>
      <h2 className="text-xl font-semibold mb-1">{mode === "login" ? "Sign in" : "Create your account"}</h2>
      <p className="text-sm text-text-muted mb-6">Sign in to manage your profile and application tracker.</p>
      {error && <p role="alert" className="flex items-center gap-2 text-sm text-red mb-4"><AlertCircle className="w-4 h-4" />{error}</p>}
      <form onSubmit={submit} className="space-y-4">
        <label className="block text-xs text-text-secondary">Email<input required type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} className="w-full mt-1 bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-primary" /></label>
        <label className="block text-xs text-text-secondary">Password<input required minLength={mode === "register" ? 6 : undefined} type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} value={password} onChange={e => setPassword(e.target.value)} className="w-full mt-1 bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-primary" /></label>
        <button disabled={busy} className="w-full bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-medium rounded-lg px-4 py-2.5">{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
      </form>
      <button onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(null) }} className="w-full text-sm text-accent mt-5">{mode === "login" ? "Need an account? Register" : "Already registered? Sign in"}</button>
      <Link href="/jobs" className="block text-center text-xs text-text-muted mt-5">Continue browsing public jobs</Link>
    </section>
  </main>
}
