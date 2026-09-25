import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Local development: forward API calls to the backend (nginx does this in Docker).
    proxy: { "/api": "http://localhost:8000" },
  },
});
