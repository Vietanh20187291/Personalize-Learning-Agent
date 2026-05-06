"use client";

import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  BrainCircuit,
  ChartNoAxesCombined,
  Layers3,
  Sparkles,
  Target,
  Users,
} from "lucide-react";

const featureCards = [
  {
    icon: BrainCircuit,
    title: "Tác nhân theo ngữ cảnh thật",
    description: "Agent phản hồi theo tài liệu, buổi học, lịch sử điểm và trạng thái học thay vì một hộp chat chung chung.",
  },
  {
    icon: BookOpen,
    title: "Ngân hàng câu hỏi gắn với tài liệu",
    description: "Mỗi câu hỏi có thể truy vết nguồn tài liệu và được sinh thêm theo từng bộ đề, từng chương, từng lớp.",
  },
  {
    icon: ChartNoAxesCombined,
    title: "Đánh giá tiến độ liền mạch",
    description: "Điểm, nỗ lực và mức độ hoàn thành được ghép lại để hiển thị một nhịp học sát với tình hình thật.",
  },
];

const studioBlocks = [
  { label: "Học viên", value: "Orbit, lộ trình, quiz và thư viện tài liệu hiện diện trong một dòng trải nghiệm liên tục." },
  { label: "Giảng viên", value: "Quản lý lớp, tài liệu, đề thi và kho câu hỏi từ cùng một mặt bằng điều phối." },
  { label: "Admin", value: "Cấp tài khoản và giữ được bộ khung vận hành gọn sạch, rõ quyền và dễ mở rộng." },
];

export default function HomePage() {
  return (
    <div className="page-shell">
      <div className="page-container space-y-8">
        <section className="hero-panel overflow-hidden px-6 py-8 md:px-9 md:py-10">
          <div className="grid gap-8 xl:grid-cols-[1.15fr_0.85fr]">
            <div className="space-y-8">
              <div className="command-badge">
                <Sparkles size={14} />
                Nova Campus
              </div>

              <div className="space-y-5">
                <h1 className="display-font max-w-4xl text-5xl font-semibold leading-[0.94] text-slate-950 md:text-7xl">
                  Một không gian học tập sáng, sạch và có cảm giác như một sản phẩm cao cấp.
                </h1>
                <p className="max-w-2xl text-base leading-8 text-slate-600 md:text-lg">
                  Nền tảng gom agent, tài liệu, quiz và phân tích thành một không gian học tập thống nhất. Người học thao tác trên
                  một giao diện nhẹ, rõ, có nhịp điệu như một ứng dụng sản phẩm thay vì một dashboard giáo dục cũ.
                </p>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row">
                <Link href="/auth" className="app-btn-primary px-6">
                  Đăng nhập
                  <ArrowRight size={18} />
                </Link>
                <Link href="/auth?mode=register" className="app-btn-dark px-6">
                  Tạo tài khoản mới
                </Link>
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                {studioBlocks.map((item) => (
                  <div key={item.label} className="metric-panel px-5 py-5">
                    <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">{item.label}</p>
                    <p className="mt-3 text-sm leading-7 text-slate-700">{item.value}</p>
                  </div>
                ))}
              </div>
            </div>

            <div className="section-panel relative overflow-hidden p-6 md:p-7">
              <div className="absolute inset-x-0 top-0 h-28 bg-[radial-gradient(circle_at_top,rgba(0,113,227,0.18),transparent_72%)]" />
              <div className="relative space-y-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">Bản xem trước</p>
                    <h2 className="mt-2 text-2xl font-semibold text-slate-950">Giao diện theo nhịp sử dụng</h2>
                  </div>
                  <div className="rounded-full bg-[rgba(0,113,227,0.08)] px-3 py-1 text-[11px] font-semibold text-[var(--brand)]">
                    Cảm hứng Apple
                  </div>
                </div>

                <div className="grid gap-3">
                  <div className="ghost-panel p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Navbar</p>
                        <p className="mt-2 text-sm font-semibold text-slate-900">Floating, bo tròn, trong suốt và tập trung điều hướng.</p>
                      </div>
                      <div className="flex gap-2">
                        <span className="h-3 w-3 rounded-full bg-slate-200" />
                        <span className="h-3 w-3 rounded-full bg-slate-300" />
                        <span className="h-3 w-3 rounded-full bg-[var(--brand)]/70" />
                      </div>
                    </div>
                  </div>

                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="metric-panel p-4">
                      <Layers3 className="h-5 w-5 text-[var(--brand)]" />
                      <p className="mt-4 text-sm font-semibold text-slate-950">Card và container được phân lớp rõ ràng.</p>
                    </div>
                    <div className="metric-panel p-4">
                      <Target className="h-5 w-5 text-[var(--brand)]" />
                      <p className="mt-4 text-sm font-semibold text-slate-950">Hành động chính được đưa lên bằng button dạng capsule.</p>
                    </div>
                  </div>

                  <div className="soft-grid ghost-panel p-5">
                    <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
                      <div>
                        <p className="text-[11px] uppercase tracking-[0.18em] text-slate-400">Bề mặt tương tác</p>
                        <p className="mt-2 text-sm leading-7 text-slate-700">
                          Dropdown, menu và notification panel hiện như những sheet nhỏ, mềm, sáng và tách khỏi nền thay vì khối hộp cứng.
                        </p>
                      </div>
                      <div className="rounded-[1.5rem] bg-white/86 px-4 py-4 shadow-[0_18px_34px_rgba(15,23,42,0.08)]">
                        <p className="text-[11px] font-semibold text-slate-500">Nhịp phản hồi</p>
                        <p className="mt-1 text-3xl font-semibold text-slate-950">Mượt và gọn</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.15fr_0.85fr]">
          <div className="grid gap-4 md:grid-cols-3">
            {featureCards.map((item) => (
              <article key={item.title} className="section-panel p-6">
                <div className="flex h-11 w-11 items-center justify-center rounded-full bg-[rgba(0,113,227,0.1)] text-[var(--brand)]">
                  <item.icon size={20} />
                </div>
                <h2 className="mt-5 text-xl font-semibold text-slate-950">{item.title}</h2>
                <p className="mt-3 text-sm leading-7 text-slate-600">{item.description}</p>
              </article>
            ))}
          </div>

          <div className="hero-panel p-6 md:p-7">
            <div className="flex items-center gap-3">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[linear-gradient(180deg,#0f172a,#2563eb)] text-white">
                <Users size={20} />
              </div>
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-slate-400">Cảm giác sử dụng</p>
                <h2 className="mt-1 text-2xl font-semibold text-slate-950">Từ dashboard sang sản phẩm</h2>
              </div>
            </div>

            <div className="mt-6 space-y-3">
              {[
                "Khoảng trắng rộng hơn, nhìn thoáng và dễ tập trung.",
                "Màu trắng, xám xanh và blue accent thay cho cảm giác template chung.",
                "Navbar không còn là thanh điều hướng thẳng; nó là một floating control bar.",
                "Card, panel, dropdown và action được bố trí mềm, phân cấp rõ và nhất quán.",
              ].map((item) => (
                <div key={item} className="ghost-panel px-4 py-4 text-sm leading-7 text-slate-700">
                  {item}
                </div>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
