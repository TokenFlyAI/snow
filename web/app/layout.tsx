import type { Metadata, Viewport } from "next";
import { Header } from "@/components/Header";
import { Providers } from "@/components/Providers";
import { ServiceWorker } from "@/components/ServiceWorker";
import "./globals.css";

const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "/snow";

export const metadata: Metadata = {
  title: "Snow Forecast · tokenfly.ai",
  description: "Multi-model snow forecasts for Ikon and Epic resorts · 多模型融合的滑雪场降雪预报",
  manifest: `${base}/manifest.webmanifest`,
  icons: { icon: `${base}/icon.svg`, apple: `${base}/apple-touch-icon.png` },
  appleWebApp: { capable: true, title: "Snow", statusBarStyle: "default" },
};
export const viewport: Viewport = {
  width: "device-width", initialScale: 1, viewportFit: "cover",
  themeColor: [{ media: "(prefers-color-scheme: light)", color: "#f3f3f1" }, { media: "(prefers-color-scheme: dark)", color: "#111110" }],
};

// Set the theme before first paint so there is no light flash in dark mode.
const themeScript = `(function(){try{var s=JSON.parse(localStorage.getItem('snow.user.v1')||'{}');var t=s.theme;if(t!=='light'&&t!=='dark'){t=matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'}document.documentElement.dataset.theme=t}catch(e){}})()`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body>
        <Providers>
          <Header />
          <main className="mx-auto max-w-3xl px-4 pb-16 pt-4">{children}</main>
          <ServiceWorker />
        </Providers>
      </body>
    </html>
  );
}
