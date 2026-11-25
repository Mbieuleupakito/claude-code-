/** Site compilé en pages statiques (servies par l'API Python) ; en développement, /api est relayé vers le serveur Python. */
const dev = process.env.NODE_ENV !== "production";

const config = {
  reactStrictMode: true,
  trailingSlash: true,
  images: { unoptimized: true },
  ...(dev
    ? { async rewrites() { return [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }]; } }
    : { output: "export" }),
};

export default config;
