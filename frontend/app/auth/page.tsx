"use client";

import React, { Suspense, useEffect, useState } from "react";
import {
  ArrowRight,
  BrainCircuit,
  ChevronLeft,
  Eye,
  EyeOff,
  IdCard,
  Loader2,
  Lock,
  Mail,
  Sparkles,
  User,
} from "lucide-react";
import axios from "axios";
import { toast } from "react-hot-toast";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

function AuthContent() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";
  const [isLogin, setIsLogin] = useState(true);
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    setIsLogin(searchParams.get("mode") !== "register");
  }, [searchParams]);

  const [formData, setFormData] = useState({
    email: "",
    password: "",
    fullname: "",
    role: "student",
    student_id: "",
  });

  type AuthResponseData = {
    access_token: string;
    role: string;
    fullname: string;
    userId: string | number;
    studentId?: string | null;
  };

  type AuthResponse = {
    data: AuthResponseData;
  };

  const getApiBaseCandidates = () => {
    const candidates = [
      apiBaseUrl,
      "http://localhost:8010",
      "http://127.0.0.1:8000",
      "http://localhost:8010",
      "http://127.0.0.1:8010",
    ].map((item) => item.trim().replace(/\/$/, ""));

    return Array.from(new Set(candidates));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!isLogin && formData.password.length < 6) {
      toast.error("Mật khẩu phải có ít nhất 6 ký tự!");
      return;
    }

    setLoading(true);
    try {
      if (isLogin) {
        const loginData = new URLSearchParams();
        loginData.append("username", formData.email);
        loginData.append("password", formData.password);

        const apiCandidates = getApiBaseCandidates();
        let res: AuthResponse | null = null;
        let lastError: unknown = null;

        for (const candidate of apiCandidates) {
          try {
            res = await axios.post<AuthResponseData>(`${candidate}/api/auth/login`, loginData, {
              headers: { "Content-Type": "application/x-www-form-urlencoded" },
              timeout: 10000,
            });
            break;
          } catch (err: unknown) {
            lastError = err;
            const status = axios.isAxiosError(err) ? err.response?.status : undefined;
            if (status === 400 || status === 401 || status === 403 || status === 422) {
              throw err;
            }
          }
        }

        if (!res) {
          throw lastError || new Error("Không thể kết nối API đăng nhập");
        }

        localStorage.setItem("token", res.data.access_token);
        localStorage.setItem("role", res.data.role);
        localStorage.setItem("fullname", res.data.fullname);
        localStorage.setItem("userId", String(res.data.userId));
        if (res.data.studentId) {
          localStorage.setItem("studentId", String(res.data.studentId));
        }

        toast.success(`Chào mừng ${res.data.fullname} quay trở lại!`);

        setTimeout(() => {
          if (res.data.role === "admin") {
            window.location.href = "/admin/teachers";
          } else if (res.data.role === "teacher") {
            window.location.href = "/teacher";
          } else {
            window.location.href = "/adaptive";
          }
        }, 800);
      } else {
        await axios.post(`${apiBaseUrl}/api/auth/register`, formData);
        toast.success("Đăng ký thành công! Mời bạn đăng nhập.");
        setIsLogin(true);
        router.push("/auth");
      }
    } catch (error: unknown) {
      const errorMsg = axios.isAxiosError(error)
        ? error.response?.data?.detail || "Đã có lỗi xảy ra. Vui lòng thử lại."
        : "Đã có lỗi xảy ra. Vui lòng thử lại.";
      toast.error(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[1.02fr_0.98fr]">
      <section className="section-panel p-7">
        <div className="inline-flex items-center gap-2 rounded-full border border-[rgba(24,24,27,0.08)] bg-zinc-50 px-3 py-1 text-[11px] font-extrabold uppercase tracking-[0.2em] text-red-700">
          <Sparkles size={14} />
          Nova Campus
        </div>
        <div className="mt-8 space-y-4">
          <div className="flex h-14 w-14 items-center justify-center rounded-[1.4rem] bg-[linear-gradient(135deg,#8c3b2e,#0e7490)] text-white shadow-[0_18px_36px_rgba(14,116,144,0.25)]">
            <BrainCircuit size={26} />
          </div>
          <h1 className="display-font text-4xl font-black leading-[1.02] text-zinc-950">
            {isLogin ? "Quay lại bàn điều phối học tập" : "Khởi tạo không gian học tập mới"}
          </h1>
          <p className="text-sm leading-relaxed text-zinc-600">
            Hệ thống này tập trung vào lộ trình học, ngân hàng câu hỏi và phân tích tiến độ từ dữ liệu thật
            của lớp học.
          </p>
        </div>

        <div className="mt-8 grid gap-3 sm:grid-cols-3 lg:grid-cols-1">
          {[
            "Điều phối tài liệu và kiểm tra theo lớp học",
            "Theo dõi tiến độ, điểm số và nội dung cần ôn",
            "Tương tác với agent trên đúng ngữ cảnh tài liệu",
          ].map((item) => (
            <div
              key={item}
              className="metric-panel px-4 py-4 text-sm font-medium text-zinc-700"
            >
              {item}
            </div>
          ))}
        </div>
      </section>

      <section className="hero-panel p-6 sm:p-8">
        <div className="mb-8">
          <p className="text-[11px] font-extrabold uppercase tracking-[0.22em] text-zinc-500">
            {isLogin ? "Đăng nhập" : "Đăng ký"}
          </p>
          <h2 className="display-font mt-2 text-3xl font-black text-zinc-950">
            {isLogin ? "Mở phiên làm việc" : "Tạo tài khoản"}
          </h2>
          <p className="mt-2 text-sm text-zinc-600">
            {isLogin
              ? "Sử dụng email và mật khẩu đã được cấp để vào workspace của bạn."
              : "Tạo tài khoản học tập mới để tham gia lộ trình và thư viện tài liệu."}
          </p>
        </div>

        <form className="space-y-5" onSubmit={handleSubmit}>
          {!isLogin ? (
            <>
              <div className="space-y-2">
                <label className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-zinc-500">
                  Họ và tên
                </label>
                <div className="relative">
                  <User className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400" size={18} />
                  <input
                    type="text"
                    required
                    placeholder="Họ và tên của bạn"
                    className="app-input pl-12"
                    onChange={(e) => setFormData({ ...formData, fullname: e.target.value })}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-zinc-500">
                  Mã số sinh viên
                </label>
                <div className="relative">
                  <IdCard className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400" size={18} />
                  <input
                    type="text"
                    required
                    placeholder="VD: 20210123"
                    className="app-input pl-12 uppercase"
                    onChange={(e) => setFormData({ ...formData, student_id: e.target.value })}
                  />
                </div>
              </div>
            </>
          ) : null}

          <div className="space-y-2">
            <label className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-zinc-500">
              Email đăng nhập
            </label>
            <div className="relative">
              <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400" size={18} />
              <input
                type="text"
                required
                placeholder={isLogin ? "Email" : "example@learning.com"}
                className="app-input pl-12"
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
              />
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-[11px] font-extrabold uppercase tracking-[0.16em] text-zinc-500">
              Mật khẩu
            </label>
            <div className="relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-zinc-400" size={18} />
              <input
                type={showPassword ? "text" : "password"}
                required
                minLength={!isLogin ? 6 : undefined}
                className="app-input pl-12 pr-12"
                onChange={(e) => setFormData({ ...formData, password: e.target.value })}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-4 top-1/2 -translate-y-1/2 text-zinc-400 transition-colors hover:text-zinc-950"
              >
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="app-btn-primary mt-4 flex w-full items-center justify-center gap-3 py-4 text-xs"
          >
            {loading ? (
              <Loader2 className="animate-spin" size={20} />
            ) : (
              <>
                {isLogin ? "Đăng nhập hệ thống" : "Tạo tài khoản học tập"}
                <ArrowRight size={18} />
              </>
            )}
          </button>
        </form>

        <div className="mt-5 text-center">
          <button
            type="button"
            onClick={() => {
              setIsLogin(!isLogin);
              setShowPassword(false);
              router.push("/auth");
            }}
            className="text-[10px] font-semibold tracking-[0.04em] text-[#8c3b2e] transition-colors hover:text-[#5f2117]"
          >
            {isLogin ? "Chưa có tài khoản? Đăng ký ngay" : "Đã có tài khoản? Đăng nhập tại đây"}
          </button>
        </div>
      </section>
    </div>
  );
}

export default function AuthPage() {
  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-6 py-10">
      <Link
        href="/"
        className="absolute left-6 top-6 flex items-center gap-2 rounded-full border border-[rgba(24,24,27,0.08)] bg-white/90 px-3 py-2 text-[11px] font-extrabold uppercase tracking-[0.18em] text-zinc-600 transition-all hover:text-[var(--brand)]"
      >
        <ChevronLeft size={16} />
        Trang chủ
      </Link>

      <div className="absolute inset-x-0 top-0 h-[38vh] bg-[radial-gradient(circle_at_top,rgba(140,59,46,0.18),transparent_58%)]" />
      <div className="absolute bottom-0 left-0 h-[28rem] w-[28rem] rounded-full bg-[rgba(14,116,144,0.08)] blur-[120px]" />
      <div className="absolute right-0 top-10 h-[24rem] w-[24rem] rounded-full bg-[rgba(255,255,255,0.34)] blur-[120px]" />

      <div className="page-container relative z-10 max-w-6xl">
        <Suspense
          fallback={
            <div className="hero-panel flex h-56 items-center justify-center">
              <Loader2 className="animate-spin text-zinc-950" size={30} />
            </div>
          }
        >
          <AuthContent />
        </Suspense>
      </div>
    </div>
  );
}
