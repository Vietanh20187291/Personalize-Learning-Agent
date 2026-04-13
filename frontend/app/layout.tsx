import type { Metadata } from "next";
import { Manrope, Space_Grotesk } from "next/font/google";
import "./globals.css";
import Navbar from "@/components/Navbar";
import NovaTeacherAgent from "@/components/NovaTeacherAgent";
import { Toaster } from "react-hot-toast"; 

const manrope = Manrope({ subsets: ["latin"], variable: "--font-manrope" });
const spaceGrotesk = Space_Grotesk({ subsets: ["latin"], variable: "--font-space-grotesk" });

export const metadata: Metadata = {
  title: "AI Agent Learning System",
  description: "Hệ thống học tập cá nhân hóa với Multi-Agent",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className={`${manrope.variable} ${spaceGrotesk.variable} min-h-screen text-slate-900 flex flex-col app-bg`}>
        {/* Thanh điều hướng thông minh */}
        <Navbar />
        
        {/* Thả tự do chiều rộng để các trang (Auth, Landing) có thể bung Full màn hình */}
        <main className="flex-1 w-full flex flex-col">
          {children}
        </main>

        <NovaTeacherAgent />

        {/* Thông báo Global */}
        <Toaster 
          position="top-center" 
          reverseOrder={false} 
          toastOptions={{
            duration: 3000,
            style: {
              background: '#0f172a',
              color: '#f8fafc',
              fontSize: '14px',
              fontWeight: 'bold',
              borderRadius: '14px',
              border: '1px solid #334155'
            }
          }}
        />
      </body>
    </html>
  );
}