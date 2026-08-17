import type { Metadata } from "next"
import { Providers } from "./providers"
import "./globals.css"

export const metadata: Metadata = {
  title: "Task Sniffer",
  description: "AI-powered job intelligence platform",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-background text-text-primary antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  )
}
