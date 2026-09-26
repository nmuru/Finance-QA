import type { NextConfig } from "next";

// const Production_mode = false;

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: "https://financial-dossier.onrender.com",
  },
};

export default nextConfig;
