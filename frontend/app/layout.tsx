import type { Metadata } from "next";
import { IBM_Plex_Mono, Plus_Jakarta_Sans } from "next/font/google";
import "./globals.css";
import Navbar from "@/components/Navbar";
import NovaTeacherAgent from "@/components/NovaTeacherAgent";
import AppAlertHost from "@/components/AppAlertHost";
import { Toaster } from "react-hot-toast";

const plusJakartaSans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-plus-jakarta-sans",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-ibm-plex-mono",
});

export const metadata: Metadata = {
  title: "Nova Campus",
  description: "Nền tảng học tập cá nhân hóa với đa tác tử AI.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className={`${plusJakartaSans.variable} ${ibmPlexMono.variable} min-h-screen antialiased`}>
        <div className="app-stage">
          <Navbar />
          <main className="flex min-h-screen w-full flex-col">{children}</main>
        </div>

        <NovaTeacherAgent />
        <AppAlertHost />

        <Toaster
          position="top-right"
          reverseOrder={false}
          gutter={14}
          toastOptions={{
            duration: 3200,
            style: {
              background: "linear-gradient(180deg, rgba(255,255,255,0.96), rgba(252,252,253,0.94))",
              color: "#0f172a",
              fontSize: "13px",
              lineHeight: "1.55",
              fontWeight: "600",
              borderRadius: "18px",
              border: "1px solid rgba(226, 232, 240, 0.95)",
              padding: "13px 15px",
              boxShadow: "0 16px 42px rgba(15, 23, 42, 0.08)",
              backdropFilter: "blur(18px)",
            },
            success: {
              iconTheme: {
                primary: "#0f766e",
                secondary: "#f0fdfa",
              },
              style: {
                border: "1px solid rgba(204, 251, 241, 0.95)",
                boxShadow: "0 16px 40px rgba(20, 184, 166, 0.1)",
              },
            },
            error: {
              duration: 3800,
              iconTheme: {
                primary: "#dc2626",
                secondary: "#fff5f5",
              },
              style: {
                border: "1px solid rgba(254, 226, 226, 0.95)",
                boxShadow: "0 16px 40px rgba(248, 113, 113, 0.1)",
              },
            },
            loading: {
              iconTheme: {
                primary: "#2563eb",
                secondary: "#f8fbff",
              },
              style: {
                border: "1px solid rgba(219, 234, 254, 0.95)",
                boxShadow: "0 16px 40px rgba(96, 165, 250, 0.1)",
              },
            },
          }}
        />
      </body>
    </html>
  );
}
