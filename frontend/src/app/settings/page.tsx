"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { motion } from "framer-motion"
import { User, Briefcase, Radar, Shield, Save, Trash2, Download } from "lucide-react"
import { useState } from "react"
import { useToast } from "@/components/ui/toast"

export default function SettingsPage() {
  const [autoScan, setAutoScan] = useState(true)
  const [notifications, setNotifications] = useState(true)
  const [autoApply, setAutoApply] = useState(false)
  const [minMatch, setMinMatch] = useState(80)
  const [maxRisk, setMaxRisk] = useState(25)
  const { toast } = useToast()

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
              <h2 className="text-sm font-semibold text-text-primary uppercase tracking-wider">Profile</h2>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Field label="Name" defaultValue="Retro" />
              <Field label="Email" defaultValue="retro@example.com" />
              <Field label="Phone" placeholder="+254 7XX XXX XXX" />
              <Field label="Location" defaultValue="Nairobi" />
              <Field label="Preferred Roles" defaultValue="Python Backend, Full Stack" />
              <Field label="Expected Salary" defaultValue="200K-400K KES" />
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

          <button onClick={() => toast("Settings saved")} className="flex items-center gap-2 bg-accent hover:bg-accent-hover text-white text-sm font-medium px-5 py-2.5 rounded-lg transition-colors">
            <Save className="w-4 h-4" /> Save settings
          </button>
        </main>
      </div>
    </div>
  )
}

function Field({ label, defaultValue, placeholder }: { label: string; defaultValue?: string; placeholder?: string }) {
  return (
    <div>
      <label className="text-xs text-text-muted font-medium">{label}</label>
      <input type="text" defaultValue={defaultValue} placeholder={placeholder}
        className="w-full mt-1 bg-surface-2 border border-border rounded-lg px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-accent/50 transition-colors" />
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
