import type { Job, Application, AnalyticsOverview, MatchDistribution, ActivityEvent, Notification } from "@/types"

export const mockJobs: Job[] = [
  {
    id: "1", title: "Senior Python Backend Developer", company: "Safaricom", location: "Nairobi", country: "KE",
    remote: true, remote_type: "full", salary: "KSh 300K-500K/mo", salary_currency: "KES",
    description: "Building scalable microservices for M-Pesa integration platform using Python, FastAPI, and PostgreSQL.",
    url: "https://safaricom.co.ke/careers/1", source: "brightermonday", skills: ["python", "fastapi", "postgresql", "docker", "redis", "kubernetes"],
    experience: "senior", employment_type: "full_time", posted_at: new Date(Date.now() - 3 * 3600000).toISOString(),
    match_score: 0.94, risk_score: 5, risk_level: "LOW", risk_flags: [], status: "discovered",
    match_breakdown: { skills: 0.96, experience: 0.92, role: 0.95, location: 1.0, salary: 0.88, projects: 0.90, freshness: 0.95, source_quality: 0.95 },
  },
  {
    id: "2", title: "Full Stack Engineer", company: "Twiga Foods", location: "Nairobi", country: "KE",
    remote: true, remote_type: "hybrid", salary: "KSh 200K-350K/mo", salary_currency: "KES",
    description: "Develop and maintain our B2B marketplace platform serving thousands of vendors across Kenya.",
    url: "https://twiga.com/careers/2", source: "myjobs", skills: ["react", "node.js", "typescript", "postgresql", "aws"],
    experience: "mid", employment_type: "full_time", posted_at: new Date(Date.now() - 8 * 3600000).toISOString(),
    match_score: 0.78, risk_score: 10, risk_level: "LOW", risk_flags: [], status: "discovered",
    match_breakdown: { skills: 0.72, experience: 0.85, role: 0.80, location: 1.0, salary: 0.75, projects: 0.70, freshness: 0.85, source_quality: 0.80 },
  },
  {
    id: "3", title: "DevOps Engineer", company: "Cellulant", location: "Nairobi", country: "KE",
    remote: false, salary: "KSh 250K-400K/mo", salary_currency: "KES",
    description: "Manage cloud infrastructure and CI/CD pipelines for payment processing systems.",
    url: "https://cellulant.com/careers/3", source: "brightermonday", skills: ["docker", "kubernetes", "aws", "terraform", "python", "jenkins"],
    experience: "mid", employment_type: "full_time", posted_at: new Date(Date.now() - 24 * 3600000).toISOString(),
    match_score: 0.62, risk_score: 8, risk_level: "LOW", risk_flags: [], status: "shortlisted",
    match_breakdown: { skills: 0.55, experience: 0.70, role: 0.60, location: 1.0, salary: 0.65, projects: 0.50, freshness: 0.60, source_quality: 0.80 },
  },
  {
    id: "4", title: "Python Data Engineer", company: "Sendy", location: "Nairobi", country: "KE",
    remote: true, remote_type: "full", salary: "KSh 280K-450K/mo", salary_currency: "KES",
    description: "Build data pipelines and analytics infrastructure for logistics optimization.",
    url: "https://sendy.io/careers/4", source: "jobicy", skills: ["python", "apache airflow", "postgresql", "docker", "aws", "spark"],
    experience: "mid", employment_type: "full_time", posted_at: new Date(Date.now() - 5 * 3600000).toISOString(),
    match_score: 0.85, risk_score: 12, risk_level: "LOW", risk_flags: [], status: "discovered",
    match_breakdown: { skills: 0.82, experience: 0.88, role: 0.85, location: 1.0, salary: 0.80, projects: 0.78, freshness: 0.90, source_quality: 0.75 },
  },
  {
    id: "5", title: "Software Engineer, Payments", company: "Flutterwave", location: "Nairobi / Remote", country: "KE",
    remote: true, remote_type: "full", salary: "$4K-6K/mo", salary_currency: "USD",
    description: "Work on the payment infrastructure powering businesses across Africa.",
    url: "https://flutterwave.com/careers/5", source: "greenhouse", skills: ["python", "java", "postgresql", "redis", "docker", "microservices"],
    experience: "mid", employment_type: "full_time", posted_at: new Date(Date.now() - 12 * 3600000).toISOString(),
    match_score: 0.82, risk_score: 7, risk_level: "LOW", risk_flags: [], status: "applied",
    match_breakdown: { skills: 0.80, experience: 0.85, role: 0.82, location: 0.90, salary: 0.85, projects: 0.75, freshness: 0.80, source_quality: 0.90 },
  },
  {
    id: "6", title: "Backend Developer", company: "Kopo Kopo", location: "Nairobi", country: "KE",
    remote: true, remote_type: "hybrid", salary: "KSh 180K-280K/mo", salary_currency: "KES",
    description: "Develop payment APIs and merchant management systems.",
    url: "https://kopokopo.com/careers/6", source: "myjobs", skills: ["python", "django", "postgresql", "redis", "celery"],
    experience: "mid", employment_type: "full_time", posted_at: new Date(Date.now() - 48 * 3600000).toISOString(),
    match_score: 0.76, risk_score: 15, risk_level: "LOW", risk_flags: [], status: "discovered",
    match_breakdown: { skills: 0.80, experience: 0.75, role: 0.78, location: 1.0, salary: 0.65, projects: 0.72, freshness: 0.40, source_quality: 0.80 },
  },
  {
    id: "7", title: "Platform Engineer", company: "Andela", location: "Remote", country: "GLOBAL",
    remote: true, remote_type: "full", salary: "$5K-8K/mo", salary_currency: "USD",
    description: "Build and maintain developer platform tools for distributed engineering teams.",
    url: "https://andela.com/careers/7", source: "greenhouse", skills: ["python", "go", "kubernetes", "terraform", "aws", "docker"],
    experience: "senior", employment_type: "full_time", posted_at: new Date(Date.now() - 6 * 3600000).toISOString(),
    match_score: 0.88, risk_score: 5, risk_level: "LOW", risk_flags: [], status: "shortlisted",
    match_breakdown: { skills: 0.85, experience: 0.90, role: 0.88, location: 1.0, salary: 0.90, projects: 0.82, freshness: 0.88, source_quality: 0.90 },
  },
  {
    id: "8", title: "ML Engineer - Fraud Detection", company: "M-Kopa", location: "Nairobi", country: "KE",
    remote: false, salary: "KSh 350K-550K/mo", salary_currency: "KES",
    description: "Build ML models for credit scoring and fraud detection in asset financing.",
    url: "https://m-kopa.com/careers/8", source: "brightermonday", skills: ["python", "scikit-learn", "tensorflow", "postgresql", "docker", "mlflow"],
    experience: "senior", employment_type: "full_time", posted_at: new Date(Date.now() - 18 * 3600000).toISOString(),
    match_score: 0.70, risk_score: 8, risk_level: "LOW", risk_flags: [], status: "discovered",
    match_breakdown: { skills: 0.65, experience: 0.75, role: 0.72, location: 1.0, salary: 0.70, projects: 0.60, freshness: 0.70, source_quality: 0.80 },
  },
  {
    id: "9", title: "Senior Software Engineer", company: "Paystack", location: "Lagos / Remote", country: "NG",
    remote: true, remote_type: "full", salary: "$4K-7K/mo", salary_currency: "USD",
    description: "Build payment APIs serving millions of transactions across Africa.",
    url: "https://paystack.com/careers/9", source: "greenhouse", skills: ["python", "ruby", "postgresql", "redis", "aws", "docker"],
    experience: "senior", employment_type: "full_time", posted_at: new Date(Date.now() - 36 * 3600000).toISOString(),
    match_score: 0.75, risk_score: 6, risk_level: "LOW", risk_flags: [], status: "discovered",
    match_breakdown: { skills: 0.72, experience: 0.80, role: 0.75, location: 0.70, salary: 0.82, projects: 0.68, freshness: 0.50, source_quality: 0.90 },
  },
  {
    id: "10", title: "Junior Python Developer", company: "Kilimall", location: "Nairobi", country: "KE",
    remote: false, salary: "KSh 80K-120K/mo", salary_currency: "KES",
    description: "Entry-level Python development for e-commerce backend systems.",
    url: "https://kilimall.com/careers/10", source: "myjobs", skills: ["python", "django", "mysql", "html", "css"],
    experience: "junior", employment_type: "full_time", posted_at: new Date(Date.now() - 72 * 3600000).toISOString(),
    match_score: 0.55, risk_score: 20, risk_level: "MEDIUM", risk_flags: [{ check: "salary_range", severity: 1, reason: "Salary below market average for skills" }], status: "discovered",
    match_breakdown: { skills: 0.60, experience: 0.40, role: 0.55, location: 1.0, salary: 0.35, projects: 0.50, freshness: 0.30, source_quality: 0.80 },
  },
  {
    id: "11", title: "Data Platform Engineer", company: "Africa's Talking", location: "Nairobi", country: "KE",
    remote: true, remote_type: "full", salary: "KSh 300K-500K/mo", salary_currency: "KES",
    description: "Build and scale real-time data processing pipelines for Africa's largest API platform.",
    url: "https://africastalking.com/careers/11", source: "greenhouse", skills: ["python", "apache kafka", "postgresql", "docker", "kubernetes", "redis"],
    experience: "mid", employment_type: "full_time", posted_at: new Date(Date.now() - 4 * 3600000).toISOString(),
    match_score: 0.91, risk_score: 4, risk_level: "LOW", risk_flags: [], status: "shortlisted",
    match_breakdown: { skills: 0.92, experience: 0.90, role: 0.90, location: 1.0, salary: 0.88, projects: 0.85, freshness: 0.92, source_quality: 0.90 },
  },
  {
    id: "12", title: "Backend Engineer (Remote)", company: "GitStart", location: "Remote", country: "GLOBAL",
    remote: true, remote_type: "full", salary: "$3K-5K/mo", salary_currency: "USD",
    description: "Contribute to open-source projects and build developer tools.",
    url: "https://gitstart.com/careers/12", source: "jobicy", skills: ["python", "typescript", "react", "postgresql", "git"],
    experience: "mid", employment_type: "full_time", posted_at: new Date(Date.now() - 10 * 3600000).toISOString(),
    match_score: 0.83, risk_score: 18, risk_level: "MEDIUM",
    risk_flags: [{ check: "company_verification", severity: 2, reason: "Company identity could not be fully verified" }],
    status: "discovered",
    match_breakdown: { skills: 0.80, experience: 0.85, role: 0.82, location: 1.0, salary: 0.78, projects: 0.80, freshness: 0.82, source_quality: 0.70 },
  },
]

export const mockApplications: Application[] = [
  { id: "a1", job_id: "5", status: "applied", notes: "Applied via referral", match_score: 0.82, risk_score: 0.07, created_at: "2026-08-15T10:00:00Z", updated_at: "2026-08-15T10:00:00Z", job: mockJobs[4] },
  { id: "a2", job_id: "3", status: "shortlisted", notes: "High match, interesting tech stack", match_score: 0.62, risk_score: 0.08, created_at: "2026-08-16T14:00:00Z", updated_at: "2026-08-16T14:00:00Z", job: mockJobs[2] },
  { id: "a3", job_id: "7", status: "interview", notes: "Phone screen scheduled for Aug 20", match_score: 0.88, risk_score: 0.05, created_at: "2026-08-12T09:00:00Z", updated_at: "2026-08-17T08:00:00Z", job: mockJobs[6] },
  { id: "a4", job_id: "11", status: "shortlisted", notes: "", match_score: 0.91, risk_score: 0.04, created_at: "2026-08-17T06:00:00Z", updated_at: "2026-08-17T06:00:00Z", job: mockJobs[10] },
  { id: "a5", job_id: "1", status: "shortlisted", notes: "Top match — Safaricom M-Pesa team", match_score: 0.94, risk_score: 0.05, created_at: "2026-08-17T07:00:00Z", updated_at: "2026-08-17T07:00:00Z", job: mockJobs[0] },
]

export const mockAnalytics: AnalyticsOverview = {
  total_jobs: 247, total_applications: 12, total_shortlisted: 8, total_rejected: 1,
  avg_match_score: 0.76, avg_risk_score: 11.2, top_sources: [
    { source: "greenhouse", total_jobs: 89, avg_match_score: 0.78, avg_risk_score: 8.5, application_count: 5 },
    { source: "brightermonday", total_jobs: 72, avg_match_score: 0.74, avg_risk_score: 12.3, application_count: 4 },
    { source: "myjobs", total_jobs: 53, avg_match_score: 0.71, avg_risk_score: 14.1, application_count: 2 },
    { source: "jobicy", total_jobs: 33, avg_match_score: 0.80, avg_risk_score: 9.8, application_count: 1 },
  ],
}

export const mockMatchDistribution: MatchDistribution = {
  excellent: 18, good: 52, fair: 120, poor: 57, avg_score: 0.68, median_score: 0.72,
}

export const mockActivity: ActivityEvent[] = [
  { id: "e1", type: "scan", message: "Scanned BrighterMonday Kenya", timestamp: new Date(Date.now() - 120000).toISOString() },
  { id: "e2", type: "match", message: "12 new strong matches found", timestamp: new Date(Date.now() - 180000).toISOString() },
  { id: "e3", type: "risk", message: "6 high-risk jobs blocked", timestamp: new Date(Date.now() - 240000).toISOString() },
  { id: "e4", type: "status", message: "Interview invitation from Andela", timestamp: new Date(Date.now() - 300000).toISOString() },
  { id: "e5", type: "scan", message: "Scanned Greenhouse boards", timestamp: new Date(Date.now() - 360000).toISOString() },
  { id: "e6", type: "match", message: "Safaricom role: 94% match", timestamp: new Date(Date.now() - 420000).toISOString() },
]

export const mockNotifications: Notification[] = [
  { id: "n1", type: "match", title: "New 94% match", message: "Senior Python Backend Developer at Safaricom", read: false, timestamp: new Date(Date.now() - 60000).toISOString() },
  { id: "n2", type: "status", title: "Interview invitation", message: "Andela invited you to interview", read: false, timestamp: new Date(Date.now() - 1800000).toISOString() },
  { id: "n3", type: "risk", title: "Suspicious listing blocked", message: "Backend Engineer at GitStart — unverified company", read: true, timestamp: new Date(Date.now() - 3600000).toISOString() },
  { id: "n4", type: "system", title: "Hunter scan complete", message: "12 new matches found from 247 jobs", read: true, timestamp: new Date(Date.now() - 7200000).toISOString() },
]
