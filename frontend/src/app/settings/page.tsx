"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { motion } from "framer-motion"
import { User, Briefcase, Radar, Shield, Save, Trash2, Download, X, Plus } from "lucide-react"
import { useState, useEffect } from "react"
import { useToast } from "@/components/ui/toast"
import { candidateService } from "@/services/api"

export default function SettingsPage() {
  const [autoScan, setAutoScan] = useState(true)
  const [notifications, setNotifications] = useState(true)
  const [autoApply, setAutoApply] = useState(false)
  const [minMatch, setMinMatch] = useState(80)
  const [maxRisk, setMaxRisk] = useState(25)
  const { toast } = useToast()

  const [profile, setProfile] = useState({
    name: "Retro",
    email: "retro@example.com",
    preferred_roles: ["Python Backend", "Full Stack"],
    skills: [] as string[],
    preferred_locations: ["Nairobi", "Remote"],
    experience_level: "mid",
    salary_min: 200000,
    salary_max: 400000,
    remote_ok: true,
  })
  const [roleInput, setRoleInput] = useState("")
  const [skillInput, setSkillInput] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    candidateService.getProfile().then((p: any) => {
      setProfile({
        name: p.name || "Retro",
        email: p.email || "retro@example.com",
        preferred_roles: p.preferred_roles || [],
        skills: p.skills || [],
        preferred_locations: p.preferred_locations || ["Nairobi", "Remote"],
        experience_level: p.experience_level || "mid",
        salary_min: p.salary_min ?? 200000,
        salary_max: p.salary_max ?? 400000,
        remote_ok: p.remote_ok ?? true,
      })
    }).catch(() => {})
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
              <Field label="Location" value={profile.preferred_locations[0] || "Nairobi"} onChange={(v: string) => setProfile({ ...profile, preferred_locations: [v, ...profile.preferred_locations.slice(1)] })} />
              <Field label="Experience Level" value={profile.experience_level} onChange={(v: string) => setProfile({ ...profile, experience_level: v })} />
            </div>

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

          {/* Hunter Settings */}
          <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
            className="bg-surface border border-border rounded-xl p-6">
            <div className="flex items-center gap-2 mb-4">
              <Radar className="w-4 h-4 text-accent" />
              <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider">Hunter Settings</h2>
            </div>
            <div className="space-y-4">
              <ToggleRow label="Auto scanning" description="Automatically scan sources for new jobs" enabled={autoScan} onChange={setAutoScan} />
              <ToggleRow label="Notifications" description="Get notified about new matches and status changes" enabled={notifications} onChange={setNotifications} />
              <div className="flex items-center justify-between py-3 border-b border-border">
                <div>
                  <p className="text-sm text-text-primary font-medium">Minimum match score</p>
                  <p className="text-xs text-text-muted">Only notify for jobs above this threshold</p>
                </div>
                <div className="flex items-center gap-3">
                  <input type="range" min={0} max={100} value={minMatch} onChange={e => setMinMatch(Number(e.target.value))}
                    className="w-24 accent-accent" />
                  <span className="text-sm font-medium text-text-primary tabular-nums w-10 text-right">{minMatch}%</span>
                </div>
              </div>
              <div className="flex items-center justify-between py-3 border-b border-border">
                <div>
                  <p className="text-sm text-text-primary font-medium">Maximum risk score</p>
                  <p className="text-xs text-text-muted">Block jobs above this risk level</p>
                </div>
                <div className="flex items-center gap-3">
                  <input type="range" min={0} max={100} value={maxRisk} onChange={e => setMaxRisk(Number(e.target.value))}
                    className="w-24 accent-accent" />
                  <span className="text-sm font-medium text-text-primary tabular-nums w-10 text-right">{maxRisk}</span>
                </div>
              </div>
              <ToggleRow label="Auto-apply" description="Applications will require approval before submission" enabled={autoApply} onChange={setAutoApply} warn />
            </div>
          </motion.section>

          {/* Privacy */}
          <motion.section initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
            className="bg-surface border border-border rounded-xl p-6">
            <div className="flex items-center gap-2 mb-4">
              <Shield className="w-4 h-4 text-accent" />
              <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider">Privacy</h2>
            </div>
            <div className="space-y-3">
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-text-secondary">CV storage</span>
                <span className="text-xs text-green font-medium">Encrypted at rest</span>
              </div>
              <div className="flex items-center justify-between py-2">
                <span className="text-sm text-text-secondary">AI processing</span>
                <span className="text-xs text-text-muted">Local only</span>
              </div>
              <div className="flex items-center justify-between py-2 border-b border-border">
                <span className="text-sm text-text-secondary">Application history</span>
                <span className="text-xs text-text-muted">Retained</span>
              </div>
            </div>
            <div className="flex items-center gap-3 mt-4">
              <button onClick={() => toast("Data exported successfully")} className="flex items-center gap-1.5 bg-surface-2 border border-border text-text-secondary hover:text-text-primary text-xs font-medium px-3 py-2 rounded-lg transition-colors">
                <Download className="w-3.5 h-3.5" /> Export data
              </button>
              <button onClick={() => toast("Account data deleted", "error")} className="flex items-center gap-1.5 bg-red-muted text-red hover:bg-red/20 text-xs font-medium px-3 py-2 rounded-lg transition-colors">
                <Trash2 className="w-3.5 h-3.5" /> Delete account data
              </button>
            </div>
          </motion.section>

          <button onClick={saveProfile} disabled={saving} className="flex items-center gap-2 bg-accent hover:bg-accent-hover disabled:opacity-50 text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors">
            <Save className="w-4 h-4" /> {saving ? "Saving..." : "Save settings"}
          </button>
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

function ToggleRow({ label, description, enabled, onChange, warn }: {
  label: string; description: string; enabled: boolean; onChange: (v: boolean) => void; warn?: boolean
}) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-border">
      <div>
        <p className={`text-sm font-medium ${warn ? "text-amber" : "text-text-primary"}`}>{label}</p>
        <p className="text-xs text-text-muted">{description}</p>
      </div>
      <button onClick={() => onChange(!enabled)}
        className={`w-10 h-6 rounded-full transition-colors relative ${enabled ? "bg-accent" : "bg-surface-3"}`}>
        <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${enabled ? "left-5" : "left-1"}`} />
      </button>
    </div>
  )
}
