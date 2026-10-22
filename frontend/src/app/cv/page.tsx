"use client"

import { Sidebar } from "@/components/layout/sidebar"
import { Header } from "@/components/layout/header"
import { candidateService } from "@/services/api"
import { motion } from "framer-motion"
import { FileText, Shield, Upload, Trash2, Download, AlertCircle, Loader2 } from "lucide-react"
import { useCallback, useEffect, useRef, useState } from "react"

type CvInfo = { filename: string | null; size: number | null }

export default function CVPage() {
  const inputRef = useRef<HTMLInputElement>(null)
  const [cv, setCv] = useState<CvInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try { setCv(await candidateService.getCv()); setError(null) }
    catch (e: any) { setError(e?.message || "Could not load CV details") }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { void load() }, [load])

  const upload = async (file?: File) => {
    if (!file) return
    setBusy(true)
    try { await candidateService.uploadCv(file); await load() }
    catch (e: any) { setError(e?.message || "CV upload failed") }
    finally { setBusy(false); if (inputRef.current) inputRef.current.value = "" }
  }

  const download = async () => {
    setBusy(true)
    try {
      const blob = await candidateService.downloadCv()
      const href = URL.createObjectURL(blob)
      const anchor = document.createElement("a")
      anchor.href = href
      anchor.download = cv?.filename || "cv"
      anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(href), 1000)
    } catch (e: any) { setError(e?.message || "CV download failed") }
    finally { setBusy(false) }
  }

  const remove = async () => {
    if (!window.confirm("Delete your uploaded CV?")) return
    setBusy(true)
    try { await candidateService.deleteCv(); setCv({ filename: null, size: null }); setError(null) }
    catch (e: any) { setError(e?.message || "CV deletion failed") }
    finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen bg-background flex">
      <Sidebar />
      <div className="flex-1 ml-[240px]">
        <Header title="My CV" />
        <main className="p-6 max-w-[900px] mx-auto space-y-6">
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
            className="flex items-center gap-2 bg-surface border border-border text-text-secondary text-xs px-3 py-2 rounded-lg w-fit">
            <Shield className="w-3.5 h-3.5 text-accent" /> New CV uploads require a configured ENCRYPTION_KEY and are encrypted before storage. Keep the key backed up; legacy CVs require administrator migration.
          </motion.div>

          {error && <div role="alert" className="flex items-center gap-2 text-sm text-red"><AlertCircle className="w-4 h-4" />{error}</div>}

          <section className="bg-surface border border-border rounded-xl p-6">
            <h2 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Current CV</h2>
            {loading ? <p className="flex items-center gap-2 text-sm text-text-muted"><Loader2 className="w-4 h-4 animate-spin" />Loading CV…</p> : cv?.filename ? (
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-xl bg-accent-muted flex items-center justify-center shrink-0"><FileText className="w-7 h-7 text-accent" /></div>
                <div className="flex-1 min-w-0"><p className="text-sm font-semibold text-text-primary truncate">{cv.filename}</p><p className="text-xs text-text-muted mt-1">{cv.size ? `${(cv.size / 1024).toFixed(1)} KB` : "Size unavailable"}</p></div>
                <div className="flex gap-2">
                  <button disabled={busy} onClick={() => void download()} className="flex items-center gap-1.5 bg-surface-2 border border-border text-text-secondary text-xs px-3 py-1.5 rounded-lg disabled:opacity-50"><Download className="w-3.5 h-3.5" /> Download</button>
                  <button disabled={busy} onClick={() => void remove()} className="flex items-center gap-1.5 bg-red-muted text-red text-xs px-3 py-1.5 rounded-lg disabled:opacity-50"><Trash2 className="w-3.5 h-3.5" /> Delete</button>
                </div>
              </div>
            ) : <p className="text-sm text-text-muted">No CV uploaded.</p>}
          </section>

          <input ref={inputRef} type="file" accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document" className="hidden" onChange={e => void upload(e.target.files?.[0])} />
          <button disabled={busy} onClick={() => inputRef.current?.click()}
            onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); void upload(e.dataTransfer.files?.[0]) }}
            className="w-full border-2 border-dashed border-border rounded-xl p-8 text-center hover:border-accent/50 transition-colors disabled:opacity-50">
            {busy ? <Loader2 className="w-8 h-8 text-accent mx-auto mb-2 animate-spin" /> : <Upload className="w-8 h-8 text-text-muted mx-auto mb-2" />}
            <span className="block text-sm text-text-secondary font-medium">{cv?.filename ? "Choose a replacement CV" : "Choose a CV to upload"}</span>
            <span className="block text-xs text-text-muted mt-1">PDF, DOC, DOCX · Max 10 MB</span>
          </button>
        </main>
      </div>
    </div>
  )
}
