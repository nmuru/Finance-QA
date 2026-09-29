import type { NextConfig } from "next";

// const Production_mode = false;

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: "https://finance-qa-rtvz.onrender.com",
  },
};

export default nextConfig;
