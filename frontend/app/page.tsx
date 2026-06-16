"use client";

import Link from "next/link";
import { ArrowRight, BookOpen, ClipboardCheck, GraduationCap, LayoutDashboard, Route } from "lucide-react";

const modules = [
  {
    icon: GraduationCap,
    title: "Gia sư theo tài liệu",
    description: "Sinh viên chọn tài liệu đang học, đặt câu hỏi và nhận phản hồi bám sát đúng tài liệu đó.",
  },
  {
    icon: Route,
    title: "Lộ trình học tập",
    description: "Hệ thống sắp xếp kế hoạch học, thời hạn dự kiến và theo dõi tiến độ hoàn thành từng tài liệu.",
  },
  {
    icon: ClipboardCheck,
    title: "Kiểm tra và đánh giá",
    description: "Sinh viên làm bài theo tài liệu, xem kết quả, lịch sử điểm và nhận phân tích học tập.",
  },
  {
    icon: LayoutDashboard,
    title: "Không gian cho giảng viên",
    description: "Giảng viên quản lý lớp, tài liệu, ngân hàng câu hỏi, đề thi và trợ lý Nova trong cùng hệ thống.",
  },
];

export default function HomePage() {
  return (
    <div className="page-shell">
      <div className="page-container space-y-6">
        <section className="hero-panel px-6 py-8 md:px-10 md:py-10">
          <div className="max-w-4xl space-y-5">
            <div className="command-badge">
              <BookOpen size={14} />
              Nova Campus
            </div>

            <div className="space-y-3">
              <h1 className="display-font text-4xl font-semibold leading-tight text-slate-950 md:text-6xl">
                Hệ thống học tập cá nhân hóa cho sinh viên và giảng viên
              </h1>
              <p className="max-w-3xl text-[15px] leading-8 text-slate-600 md:text-base">
                Nova Campus hỗ trợ quản lý tài liệu học tập, kiểm tra theo từng tài liệu, lập lộ trình học, đánh giá tiến độ
                và tương tác với các AI agent phục vụ học tập và giảng dạy.
              </p>
            </div>

            <div className="flex flex-col gap-3 sm:flex-row">
              <Link href="/auth" className="app-btn-primary px-6">
                Đăng nhập
                <ArrowRight size={18} />
              </Link>
              <Link href="/auth?mode=register" className="app-btn-dark px-6">
                Tạo tài khoản
              </Link>
            </div>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {modules.map((item) => (
            <article key={item.title} className="section-panel p-6">
              <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[rgba(0,113,227,0.1)] text-[var(--brand)]">
                <item.icon size={20} />
              </div>
              <h2 className="mt-5 text-lg font-semibold text-slate-950">{item.title}</h2>
              <p className="mt-3 text-sm leading-7 text-slate-600">{item.description}</p>
            </article>
          ))}
        </section>

        <section className="section-panel px-6 py-6 md:px-8">
          <h2 className="text-xl font-semibold text-slate-950">Các nhóm chức năng chính</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <div className="ghost-panel px-4 py-4 text-sm leading-7 text-slate-700">
              Sinh viên có thể học theo tài liệu, làm bài kiểm tra, xem lộ trình và hỏi Tutor Agent hoặc Evaluation Agent.
            </div>
            <div className="ghost-panel px-4 py-4 text-sm leading-7 text-slate-700">
              Giảng viên có thể tải tài liệu, quản lý lớp học, tạo đề, quản lý ngân hàng câu hỏi và dùng Nova Teacher Agent.
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
