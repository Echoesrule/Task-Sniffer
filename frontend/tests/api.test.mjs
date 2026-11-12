import test from "node:test"
import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import ts from "typescript"

process.env.NEXT_PUBLIC_API_URL = "http://api.test"

const storage = new Map()
const dispatchedEvents = []
globalThis.window = {
  dispatchEvent: event => {
    dispatchedEvents.push(event.type)
    return true
  },
}
globalThis.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: key => storage.delete(key),
}
globalThis.document = { cookie: "" }

const source = await readFile(new URL("../src/services/api.ts", import.meta.url), "utf8")
const { outputText } = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
})
const api = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString("base64")}`)

async function importTypeScript(relativePath) {
  const source = await readFile(new URL(relativePath, import.meta.url), "utf8")
  const compiled = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText
  return import(`data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`)
}

test("login uses the HttpOnly cookie session and never stores a token", async () => {
  storage.clear()
  let requestOptions
  globalThis.fetch = async (_url, options) => {
    requestOptions = options
    return Response.json({ access_token: "signed-token", email: "alice@example.com" })
  }

  await api.authService.login("alice@example.com", "secret")

  assert.equal(requestOptions.method, "POST")
  assert.equal(requestOptions.credentials, "include")
  assert.equal(requestOptions.headers.Authorization, undefined)
  assert.equal(localStorage.getItem("auth_token"), null)
})

test("unsafe requests send the double-submit CSRF token from the cookie", async () => {
  document.cookie = "csrf_token=csrf-value"
  let requestOptions
  globalThis.fetch = async (_url, options) => {
    requestOptions = options
    return Response.json({ jobs: [], total: 0 })
  }

  await api.jobsService.search("backend engineer", 2, 20)

  assert.equal(requestOptions.method, "POST")
  assert.equal(requestOptions.credentials, "include")
  assert.equal(requestOptions.headers["X-CSRF-Token"], "csrf-value")
  assert.equal(requestOptions.headers.Authorization, undefined)
})

test("safe GET requests do not send a CSRF header", async () => {
  document.cookie = "csrf_token=csrf-value"
  let requestOptions
  globalThis.fetch = async (_url, options) => {
    requestOptions = options
    return Response.json({ jobs: [], total: 0 })
  }

  await api.jobsService.list()

  assert.equal(requestOptions.method, "GET")
  assert.equal(requestOptions.credentials, "include")
  assert.equal(requestOptions.headers["X-CSRF-Token"], undefined)
})

test("logout is a CSRF-protected cookie request", async () => {
  document.cookie = "csrf_token=csrf-value"
  let requestOptions
  globalThis.fetch = async (_url, options) => {
    requestOptions = options
    return Response.json({ detail: "Signed out" })
  }

  await api.authService.logout()

  assert.equal(requestOptions.method, "POST")
  assert.equal(requestOptions.credentials, "include")
  assert.equal(requestOptions.headers["X-CSRF-Token"], "csrf-value")
})

test("registration posts a generic request and then signs in", async () => {
  document.cookie = "csrf_token=csrf-value"
  const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    if (url.endsWith("/auth/register")) {
      return Response.json({ detail: "Registration request accepted." }, { status: 202 })
    }
    return Response.json({ access_token: "signed-token", email: "alice@example.com" })
  }

  await api.authService.register("alice@example.com", "securepassword123")

  assert.equal(calls.length, 2)
  assert.equal(calls[0].url, "http://api.test/auth/register")
  assert.equal(calls[0].options.method, "POST")
  assert.equal(calls[1].url, "http://api.test/auth/login")
  assert.equal(calls[1].options.credentials, "include")
  assert.equal(localStorage.getItem("auth_token"), null)
})

test("CV upload uses multipart encoding with cookie credentials and CSRF", async () => {
  document.cookie = "csrf_token=csrf-value"
  let requestOptions
  globalThis.fetch = async (_url, options) => {
    requestOptions = options
    return Response.json({ filename: "cv.pdf", size: 3, content_type: "application/pdf", message: "ok" })
  }

  await api.candidateService.uploadCv(new File(["pdf"], "cv.pdf", { type: "application/pdf" }))

  assert.ok(requestOptions.body instanceof FormData)
  assert.equal(requestOptions.credentials, "include")
  assert.equal(requestOptions.headers.Authorization, undefined)
  assert.equal(requestOptions.headers["X-CSRF-Token"], "csrf-value")
  assert.equal(requestOptions.headers["Content-Type"], undefined)
})

test("a 401 refreshes the session once and retries the request", async () => {
  document.cookie = "csrf_token=csrf-value"
  dispatchedEvents.length = 0
  const calls = []
  let jobsCalls = 0
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    if (url.endsWith("/jobs")) {
      jobsCalls += 1
      if (jobsCalls === 1) return Response.json({ detail: "expired" }, { status: 401 })
      return Response.json({ jobs: [], total: 0 })
    }
    if (url.endsWith("/auth/refresh")) return Response.json({ detail: "ok" })
    throw new Error(`unexpected ${url}`)
  }

  const result = await api.jobsService.list()

  assert.deepEqual(result, { jobs: [], total: 0 })
  assert.deepEqual(
    calls.map(call => new URL(call.url).pathname),
    ["/jobs", "/auth/refresh", "/jobs"]
  )
  assert.equal(calls[1].options.method, "POST")
  assert.equal(calls[1].options.credentials, "include")
  assert.equal(calls[1].options.headers["X-CSRF-Token"], "csrf-value")
  assert.equal(dispatchedEvents.includes("auth:unauthorized"), false)
})

test("an unrecoverable 401 emits auth:unauthorized", async () => {
  document.cookie = "csrf_token=csrf-value"
  dispatchedEvents.length = 0
  globalThis.fetch = async url => {
    if (url.endsWith("/auth/refresh")) {
      return Response.json({ detail: "invalid refresh" }, { status: 401 })
    }
    return Response.json({ detail: "Unauthorized" }, { status: 401 })
  }

  await assert.rejects(api.jobsService.list(), err => err.status === 401)
  assert.deepEqual(dispatchedEvents, ["auth:unauthorized"])
})

test("a failed login never triggers the refresh loop", async () => {
  const calls = []
  globalThis.fetch = async url => {
    calls.push(url)
    return Response.json({ detail: "Invalid credentials" }, { status: 401 })
  }

  await assert.rejects(api.authService.login("alice@example.com", "wrong"))

  assert.deepEqual(calls, ["http://api.test/auth/login"])
})

test("concurrent 401s share a single refresh request", async () => {
  document.cookie = "csrf_token=csrf-value"
  let jobsCalls = 0
  let refreshCalls = 0
  globalThis.fetch = async url => {
    if (url.endsWith("/auth/refresh")) {
      refreshCalls += 1
      await new Promise(resolve => setTimeout(resolve, 5))
      return Response.json({ detail: "ok" })
    }
    jobsCalls += 1
    if (jobsCalls <= 2) return Response.json({ detail: "expired" }, { status: 401 })
    return Response.json({ jobs: [], total: 0 })
  }

  const [first, second] = await Promise.all([
    api.jobsService.list(),
    api.jobsService.list(),
  ])

  assert.deepEqual(first, { jobs: [], total: 0 })
  assert.deepEqual(second, { jobs: [], total: 0 })
  assert.equal(refreshCalls, 1)
})

test("Apply uses only a validated HTTP application URL", async () => {
  const links = await importTypeScript("../src/lib/job-links.ts")
  const job = {
    url: "https://apply.example/jobs/42",
    source_url: "https://board.example/jobs/42",
    url_status: "VALID",
  }
  assert.equal(links.applicationHref(job), "https://apply.example/jobs/42")
  assert.equal(links.sourceHref(job), "https://board.example/jobs/42")
  assert.equal(links.applicationHref({ ...job, url_status: "NEEDS_REVIEW" }), null)
  assert.equal(links.applicationHref({ ...job, url: "javascript:alert(1)" }), null)
})
