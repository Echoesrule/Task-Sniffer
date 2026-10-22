"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { motion } from "framer-motion"
import { User, Save, X, Plus, AlertCircle } from "lucide-react"
import { useState, useEffect } from "react"
import { useToast } from "@/components/ui/toast"
import { authService, candidateService } from "@/services/api"

type ProfileForm = {
  name: string; email: string; preferred_roles: string[]; skills: string[];
  preferred_locations: string[]; experience_level: string; salary_min: number;
  salary_max: number; remote_ok: boolean
}

export default function SettingsPage() {
  const { toast } = useToast()
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [profile, setProfile] = useState<ProfileForm>({
    name: "",
    email: "",
    preferred_roles: [],
    skills: [] as string[],
    preferred_locations: [],
    experience_level: "",
    salary_min: 0,
    salary_max: 0,
    remote_ok: false,
  })
  const [roleInput, setRoleInput] = useState("")
  const [skillInput, setSkillInput] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    Promise.all([authService.me(), candidateService.getProfile()]).then(([user, p]) => {
      if (!cancelled) setProfile({
        name: p.name || "", email: p.email || user.email,
        preferred_roles: p.preferred_roles || [], skills: p.skills || [],
        preferred_locations: p.preferred_locations || [], experience_level: p.experience_level || "",
        salary_min: p.salary_min ?? 0, salary_max: p.salary_max ?? 0, remote_ok: p.remote_ok ?? false,
      })
    }).catch(async (e: any) => {
      if (cancelled) return
      if (e?.status === 404) {
        try { const user = await authService.me(); if (!cancelled) setProfile(p => ({ ...p, email: user.email })) }
        catch (authError: any) { if (!cancelled) setLoadError(authError?.message || "Sign in to manage your profile") }
      } else setLoadError(e?.message || "Could not load profile")
    }).finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const addRole = () => {
    const r = roleInput.trim()
    if (!r) return
    if (!profile.preferred_roles.includes(r)) {
      setProfile({ ...profile, preferred_roles: [...profile.preferred_roles, r] })
    }
    setRoleInput("")
  }

  const removeRole = (r: string) => {
    setProfile({ ...profile, preferred_roles: profile.preferred_roles.filter(x => x !== r) })
  }

  const addSkill = () => {
    const s = skillInput.trim().toLowerCase()
    if (!s) return
    if (!profile.skills.includes(s)) {
      setProfile({ ...profile, skills: [...profile.skills, s] })
    }
    setSkillInput("")
  }

  const removeSkill = (s: string) => {
    setProfile({ ...profile, skills: profile.skills.filter(x => x !== s) })
  }

  const saveProfile = async () => {
    setSaving(true)
    try {
      await candidateService.updateProfile(profile)
      toast("Settings saved")
    } catch (e: any) {
      toast(e?.message || "Failed to save", "error")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <div className="flex-1 ml-[240px]">
        <Header title="Settings" />
        <main className="p-6 max-w-[800px] mx-auto space-y-6">
          {loadError && <div role="alert" className="flex items-center gap-2 text-sm text-red"><AlertCircle className="w-4 h-4" />{loadError}</div>}
          {loading ? <p className="text-sm text-text-muted">Loading profile…</p> : <>
          {/* Profile */}
          <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            className="bg-surface border border-border rounded-xl p-6">
            <div className="flex items-center gap-2 mb-4">
              <User className="w-4 h-4 text-accent" />
              <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider">Profile & Job Preferences</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
              <Field label="Name" value={profile.name} onChange={(v: string) => setProfile({ ...profile, name: v })} />
              <Field label="Email" value={profile.email} onChange={(v: string) => setProfile({ ...profile, email: v })} />
              <Field label="Location" value={profile.preferred_locations[0] || ""} onChange={(v: string) => setProfile({ ...profile, preferred_locations: [v, ...profile.preferred_locations.slice(1)] })} />
              <Field label="Experience Level" value={profile.experience_level} onChange={(v: string) => setProfile({ ...profile, experience_level: v })} />
              <NumberField label="Minimum salary expectation" value={profile.salary_min} onChange={(v: number) => setProfile({ ...profile, salary_min: v })} />
              <NumberField label="Maximum salary expectation" value={profile.salary_max} onChange={(v: number) => setProfile({ ...profile, salary_max: v })} />
            </div>
            <label className="flex items-center gap-2 text-sm text-text-secondary mb-5"><input type="checkbox" checked={profile.remote_ok} onChange={e => setProfile({ ...profile, remote_ok: e.target.checked })} className="accent-accent" /> Open to fully remote roles</label>

            <div className="mb-4">
              <label className="text-xs text-text-muted font-medium">Preferred Roles / Job Titles</label>
              <p className="text-xs text-text-muted mb-2">Add job titles you want to find (e.g., "software engineer", "web developer")</p>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={roleInput}
                  onChange={e => setRoleInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addRole())}
                  placeholder="e.g., software engineer"
                  className="flex-1 bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent/50"
                />
                <button onClick={addRole} className="px-3 py-2 bg-accent hover:bg-accent-hover text-white rounded-lg text-sm flex items-center gap-1">
                  <Plus className="w-3 h-3" /> Add
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {profile.preferred_roles.map(r => (
                  <span key={r} className="flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-accent/10 text-accent border border-accent/30">
                    {r}
                    <button onClick={() => removeRole(r)}><X className="w-3 h-3" /></button>
                  </span>
                ))}
              </div>
            </div>

            <div>
              <label className="text-xs text-text-muted font-medium">Skills / Keywords</label>
              <p className="text-xs text-text-muted mb-2">Add skills to improve matching (e.g., "python", "react", "javascript")</p>
              <div className="flex gap-2 mb-2">
                <input
                  type="text"
                  value={skillInput}
                  onChange={e => setSkillInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addSkill())}
                  placeholder="e.g., python"
                  className="flex-1 bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent/50"
                />
                <button onClick={addSkill} className="px-3 py-2 bg-accent hover:bg-accent-hover text-white rounded-lg text-sm flex items-center gap-1">
                  <Plus className="w-3 h-3" /> Add
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {profile.skills.map(s => (
                  <span key={s} className="flex items-center gap-1 text-xs px-2 py-1 rounded-md bg-surface-3 text-text-secondary border border-border">
                    {s}
                    <button onClick={() => removeSkill(s)}><X className="w-3 h-3" /></button>
                  </span>
                ))}
              </div>
            </div>
          </motion.section>

          <button onClick={saveProfile} disabled={saving} className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors">
            <Save className="w-4 h-4" /> {saving ? "Saving..." : "Save settings"}
          </button>
          </>}
        </main>
      </div>
    </div>
  )
}

function Field({ label, value, defaultValue, placeholder, onChange }: { label: string; value?: string; defaultValue?: string; placeholder?: string; onChange?: (v: string) => void }) {
  return (
    <div>
      <label className="text-xs text-text-muted font-medium">{label}</label>
      <input
        type="text"
        value={value !== undefined ? value : undefined}
        defaultValue={value === undefined ? defaultValue : undefined}
        placeholder={placeholder}
        onChange={e => onChange?.(e.target.value)}
        className="w-full mt-1 bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent/50 transition-colors"
      />
    </div>
  )
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return <div><label className="text-xs text-text-muted font-medium">{label}</label><input type="number" min="0" value={value || ""} onChange={e => onChange(Number(e.target.value))} className="w-full mt-1 bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-primary" /></div>
}
