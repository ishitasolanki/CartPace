/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // e2e/ is Playwright's, not Vitest's -- both tools default to a
    // *.spec.ts glob, so without this exclusion Vitest tries to run
    // Playwright tests in jsdom and fails on the missing `page` fixture.
    exclude: ["e2e/**", "node_modules/**"],
  },
})
