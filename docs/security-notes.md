
### Phase 2 — Remaining Security Risks

**Status:** Redirect SSRF fixes implemented; DNS hardening remains incomplete.

1. **DNS fail-open behavior**
   - Current behavior treats DNS resolution failures or timeouts as safe and allows the request to proceed.
   - Required: Fail closed when destination safety cannot be verified. Return `NEEDS_REVIEW` or a controlled fetch failure instead of issuing the request.

2. **DNS rebinding / TOCTOU**
   - Current behavior validates resolved IP addresses, but the HTTP client may resolve the hostname again when connecting.
   - Risk: DNS could change between validation and connection, potentially allowing access to private or internal IP addresses.
   - Required: Pin the validated destination IP while preserving TLS hostname verification and the correct HTTP `Host` header, or use a properly configured outbound egress proxy.

3. **Production deployment restriction**
   - Do not consider SSRF protection fully production-ready until DNS failure handling and DNS rebinding are addressed or explicitly risk-accepted.
   - Verify every outbound fetch path, including redirects and URLs extracted from canonical tags, JSON-LD, and application links, uses the same security policy.

4. **Verification**
   - Add deterministic tests for DNS timeouts, resolution failures, public-to-private DNS changes, and redirect chains.
   - Run the complete regression suite after any changes.
   - Reassess these items during Phase 5 security and release-readiness verification.

**Next step:** Proceed with Phase 3 URL extraction in development while retaining these items as open security risks.