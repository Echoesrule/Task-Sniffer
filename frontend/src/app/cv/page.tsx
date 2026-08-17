"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { motion } from "framer-motion"
import { FileText, Shield, Upload, Trash2, Eye, Replace, Check } from "lucide-react"
import { useToast } from "@/components/ui/toast"

const versions = [
  { name: "General CV", skills: 18, experiences: 3, projects: 5, recommended: true },
  { name: "Backend CV", skills: 12, experiences: 3, projects: 4, recommended: false },
  { name: "Python CV", skills: 8, experiences: 2, projects: 3, recommended: false },
  { name: "Data / Analytics CV", skills: 10, experiences: 2, projects: 3, recommended: false },
]

export default function CVPage() {
  const { toast } = useToast()

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <div className="flex-1 ml-[240px]">
        <Header title="My CV" />
        <main className="p-6 max-w-[900px] mx-auto space-y-6">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-2 bg-green-muted text-green text-xs font-medium px-3 py-2 rounded-lg w-fit">
            <Shield className="w-3.5 h-3.5" /> Your CV is private and encrypted at rest
          </motion.div>

          {/* Current CV */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
            className="bg-surface border border-border rounded-xl p-6">
            <h2 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Current CV</h2>
            <div className="flex items-center gap-4">
              <div className="w-14 h-14 rounded-xl bg-accent-muted flex items-center justify-center shrink-0">
                <FileText className="w-7 h-7 text-accent" />
              </div>
              <div className="flex-1">
                <p className="text-sm font-semibold text-text-primary">Retro_Backend_CV.pdf</p>
                <p className="text-xs text-text-muted mt-0.5">Updated Aug 17, 2026 · 185 KB</p>
                <div className="flex items-center gap-4 mt-2 text-xs text-text-secondary">
                  <span>18 Skills</span>
                  <span>3 Experience Entries</span>
                  <span>5 Projects</span>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2 mt-4">
              <button onClick={() => toast("CV preview opened")} className="flex items-center gap-1.5 bg-surface-2 border border-border text-text-secondary hover:text-text-primary text-xs font-medium px-3 py-1.5 rounded-lg transition-colors">
                <Eye className="w-3.5 h-3.5" /> Preview
              </button>
              <button onClick={() => toast("Select a new CV file to replace")} className="flex items-center gap-1.5 bg-surface-2 border border-border text-text-secondary hover:text-text-primary text-xs font-medium px-3 py-1.5 rounded-lg transition-colors">
                <Replace className="w-3.5 h-3.5" /> Replace
              </button>
              <button onClick={() => toast("CV deleted", "error")} className="flex items-center gap-1.5 bg-red-muted text-red hover:bg-red/20 text-xs font-medium px-3 py-1.5 rounded-lg transition-colors">
                <Trash2 className="w-3.5 h-3.5" /> Delete
              </button>
            </div>
          </motion.div>

          {/* Upload */}
          <motion.div
            initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 }}
            onClick={() => toast("File picker opened")}
            className="border-2 border-dashed border-border rounded-xl p-8 text-center hover:border-accent/50 transition-colors cursor-pointer">
            <Upload className="w-8 h-8 text-text-muted mx-auto mb-2" />
            <p className="text-sm text-text-secondary font-medium">Drop your CV here or click to upload</p>
            <p className="text-xs text-text-muted mt-1">PDF, DOC, DOCX · Max 10 MB</p>
          </motion.div>

          {/* CV Versions */}
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.2 }}
            className="bg-surface border border-border rounded-xl p-6">
            <h2 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">CV Versions</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {versions.map(v => (
                <div key={v.name}
                  onClick={() => toast(`Switched to ${v.name}`)}
                  className={`border rounded-lg p-4 transition-colors cursor-pointer ${v.recommended ? "border-accent/50 bg-accent-muted/30 hover:bg-accent-muted/50" : "border-border hover:border-border-light hover:bg-surface-2"}`}>
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-medium text-text-primary">{v.name}</h3>
                    {v.recommended && (
                      <span className="text-[10px] bg-accent/20 text-accent px-2 py-0.5 rounded-full font-medium">Recommended</span>
                    )}
                  </div>
                  <p className="text-xs text-text-muted mt-1">{v.skills} skills · {v.experiences} experiences · {v.projects} projects</p>
                </div>
              ))}
            </div>
          </motion.div>
        </main>
      </div>
    </div>
  )
}
