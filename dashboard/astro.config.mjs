import { defineConfig } from 'astro/config';
import tailwindcss from '@tailwindcss/vite';

export default defineConfig({
  site: 'https://hsliuustc0106.github.io',
  base: '/vllm-omni-kanban/dashboard/',
  trailingSlash: 'always',
  output: 'static',
  build: {
    assets: 'assets',
  },
  vite: {
    plugins: [tailwindcss()],
  },
});
