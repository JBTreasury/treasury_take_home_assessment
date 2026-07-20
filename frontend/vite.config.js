import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        // 127.0.0.1, not "localhost": on Node 18+ "localhost" can resolve to
        // IPv6 ::1, but uvicorn binds IPv4 127.0.0.1 by default -- the mismatch
        // makes proxied /api calls fail with "Failed to fetch". Forcing IPv4 here
        // matches the backend's bind. (Or run uvicorn with --host ::1.)
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
