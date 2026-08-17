"use client"

import { motion, AnimatePresence } from "framer-motion"
import { CheckCircle, XCircle, Info, X } from "lucide-react"
import { useState, useEffect, createContext, useContext, useCallback } from "react"

type ToastType = "success" | "error" | "info"
interface Toast { id: number; message: string; type: ToastType }

const ToastContext = createContext<{
  toast: (message: string, type?: ToastType) => void
}>({ toast: () => {} })

export function useToast() {
  return useContext(ToastContext)
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const [counter, setCounter] = useState(0)

  const toast = useCallback((message: string, type: ToastType = "success") => {
    const id = counter + 1
    setCounter(id)
    setToasts(prev => [...prev, { id, message, type }])
  }, [counter])

  const remove = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-6 right-6 z-50 space-y-2">
        <AnimatePresence>
          {toasts.map(t => (
            <ToastItem key={t.id} toast={t} onRemove={() => remove(t.id)} />
          ))}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: () => void }) {
  useEffect(() => {
    const t = setTimeout(onRemove, 3000)
    return () => clearTimeout(t)
  }, [onRemove])

  const icons = { success: CheckCircle, error: XCircle, info: Info }
  const colors = { success: "text-green", error: "text-red", info: "text-blue" }
  const Icon = icons[toast.type]

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 10, scale: 0.95 }}
      className="flex items-center gap-3 bg-surface border border-border rounded-lg px-4 py-3 shadow-lg min-w-[280px]"
    >
      <Icon className={`w-4 h-4 shrink-0 ${colors[toast.type]}`} />
      <span className="text-sm text-text-primary flex-1">{toast.message}</span>
      <button onClick={onRemove} className="text-text-muted hover:text-text-primary">
        <X className="w-3.5 h-3.5" />
      </button>
    </motion.div>
  )
}
