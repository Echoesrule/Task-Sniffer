type JobLinkFields = { url?: string | null; source_url?: string | null; canonical_url?: string | null; url_status?: string | null }

function safeHttpUrl(value?: string | null): string | null {
  if (!value) return null
  try {
    const parsed = new URL(value)
    return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : null
  } catch { return null }
}

export function applicationHref(job: JobLinkFields): string | null {
  return job.url_status === "VALID" ? safeHttpUrl(job.url) : null
}

export function sourceHref(job: JobLinkFields): string | null {
  return job.url_status === "VALID" ? safeHttpUrl(job.source_url || job.canonical_url) : null
}
