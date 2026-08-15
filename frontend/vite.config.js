import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/events": "http://127.0.0.1:8000",
      "/replay": "http://127.0.0.1:8000",
      "/audit-trail": "http://127.0.0.1:8000",
      "/decisions": "http://127.0.0.1:8000",
    },
  },
});
