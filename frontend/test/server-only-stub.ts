// Test-only stub for the "server-only" package.
//
// The real package's default export unconditionally throws (it relies on the
// "react-server" bundler condition, set by Next.js's RSC build, to swap in a
// no-op module instead). Vitest doesn't set that condition, so tests that
// import server-only modules (lib/env.ts, lib/api-client.ts) would otherwise
// fail even though they're legitimately running in a server-like context.
export {};
