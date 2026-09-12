import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '0.0.0.0',
    port: 3000,
  },
  build: {
    rollupOptions: {
      output: {
        // AG_AUDIT_REMEDIATION_A2: separate the heaviest third-party charting
        // libraries from application code and from the React runtime, so a
        // change to app code does not force clients to re-download vendor
        // code. Pure build config -- no application source changed. Chunk
        // size is a performance characteristic, not an R4 readiness gate.
        manualChunks: {
          // NOTE: recharts remains ~730kB and the app chunk ~912kB after this
          // split, so the >500kB Rollup warning still fires. That is a load-time
          // performance characteristic, NOT a readiness gate -- do not document
          // this as "all chunks under 500kB". ('d3' is not split out: it is
          // reached only transitively via recharts and produced an empty chunk.)
          'vendor-recharts': ['recharts'],
        },
      },
    },
  },
});
