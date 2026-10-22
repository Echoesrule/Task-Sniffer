import test from "node:test"
import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import ts from "typescript"

process.env.NEXT_PUBLIC_API_URL = "http://api.test"

const storage = new Map()
globalThis.window = {}
globalThis.localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key, value) => storage.set(key, value),
  removeItem: key => storage.delete(key),
}

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

test("login persists the returned bearer token for protected API calls", async () => {
  globalThis.fetch = async (_url, options) => {
    assert.equal(options.method, "POST")
    return Response.json({ access_token: "signed-token", email: "alice@example.com" })
  }
  await api.authService.login("alice@example.com", "secret")
  assert.equal(localStorage.getItem("auth_token"), "signed-token")
})

test("job search sends query and pagination to the server API", async () => {
  let requestBody
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "http://api.test/jobs/search")
    assert.equal(options.headers.Authorization, "Bearer signed-token")
    requestBody = JSON.parse(options.body)
    return Response.json({ jobs: [], total: 0 })
  }
  await api.jobsService.search("backend engineer", 2, 20)
  assert.deepEqual(requestBody, { query: "backend engineer", page: 2, page_size: 20 })
})

test("CV upload uses multipart encoding and includes authentication", async () => {
  let requestOptions
  globalThis.fetch = async (_url, options) => {
    requestOptions = options
    return Response.json({ filename: "cv.pdf", size: 3, content_type: "application/pdf", message: "ok" })
  }
  await api.candidateService.uploadCv(new File(["pdf"], "cv.pdf", { type: "application/pdf" }))
  assert.ok(requestOptions.body instanceof FormData)
  assert.equal(requestOptions.headers.Authorization, "Bearer signed-token")
  assert.equal(requestOptions.headers["Content-Type"], undefined)
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
