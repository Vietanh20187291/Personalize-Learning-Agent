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
  User,
} from "lucide-react";
import axios from "axios";
import { toast } from "react-hot-toast";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";

function AuthContent() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
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

        const res = await axios.post(`${apiBaseUrl}/api/auth/login`, loginData, {
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
        });

        localStorage.setItem("token", res.data.access_token);
        localStorage.setItem("role", res.data.role);
        localStorage.setItem("fullname", res.data.fullname);
        localStorage.setItem("userId", res.data.userId);
        if (res.data.studentId) {
          localStorage.setItem("studentId", res.data.studentId);
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
    } catch (error: any) {
      const errorMsg = error.response?.data?.detail || "Đã có lỗi xảy ra. Vui lòng thử lại.";
      toast.error(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="text-center">
        <div className="inline-flex p-4 rounded-3xl bg-gradient-to-br from-amber-500 via-amber-600 to-yellow-600 text-white shadow-xl shadow-amber-200 mb-6 transform hover:rotate-6 transition-transform cursor-pointer">
          <BrainCircuit size={32} />
        </div>
        <h2 className="display-font text-4xl font-black text-slate-900 uppercase tracking-tighter leading-none mb-3">
          {isLogin ? "Đăng nhập" : "Đăng ký"}
        </h2>
        <p className="text-slate-500 text-[10px] font-black uppercase tracking-[0.3em]">
          AI Learning Workspace
        </p>
      </div>

      <form className="space-y-5" onSubmit={handleSubmit}>
        {!isLogin && (
          <>
            <div className="space-y-1.5">
              <label className="text-[10px] font-black text-slate-500 uppercase ml-1 tracking-widest">Họ và tên</label>
              <div className="relative">
                <User className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                <input
                  type="text"
                  required
                  placeholder="Họ và tên của bạn"
                  className="app-input pl-12 pr-4 py-4 rounded-2xl"
                  onChange={(e) => setFormData({ ...formData, fullname: e.target.value })}
                />
              </div>
            </div>

            <div className="space-y-1.5 animate-in fade-in slide-in-from-top-2">
              <label className="text-[10px] font-black text-slate-500 uppercase ml-1 tracking-widest">Mã số sinh viên (MSSV)</label>
              <div className="relative">
                <IdCard className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
                <input
                  type="text"
                  required
                  placeholder="VD: 20210123"
                  className="app-input pl-12 pr-4 py-4 rounded-2xl uppercase"
                  onChange={(e) => setFormData({ ...formData, student_id: e.target.value })}
                />
              </div>
            </div>
          </>
        )}

        <div className="space-y-1.5">
          <label className="text-[10px] font-black text-slate-500 uppercase ml-1 tracking-widest">Email đăng nhập</label>
          <div className="relative">
            <Mail className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              type="text"
              required
              placeholder={isLogin ? "Email" : "example@learning.com"}
              className="app-input pl-12 pr-4 py-4 rounded-2xl"
              onChange={(e) => setFormData({ ...formData, email: e.target.value })}
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <label className="text-[10px] font-black text-slate-500 uppercase ml-1 tracking-widest">Mật khẩu bảo mật</label>
          <div className="relative">
            <Lock className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" size={18} />
            <input
              type={showPassword ? "text" : "password"}
              required
              minLength={!isLogin ? 6 : undefined}
              placeholder=""
              className="app-input pl-12 pr-12 py-4 rounded-2xl"
              onChange={(e) => setFormData({ ...formData, password: e.target.value })}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 hover:text-amber-700 transition-colors"
            >
              {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
            </button>
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-slate-900 text-white py-5 rounded-[1.5rem] font-black uppercase tracking-[0.2em] text-xs flex items-center justify-center gap-3 hover:bg-amber-700 transition-all active:scale-[0.98] shadow-2xl shadow-slate-200 disabled:opacity-70 mt-4"
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

      <div className="text-center pt-2">
        <button
          type="button"
          onClick={() => {
            setIsLogin(!isLogin);
            setShowPassword(false);
            router.push("/auth");
          }}
          className="text-[10px] font-black text-slate-500 uppercase tracking-widest hover:text-amber-700 transition-colors"
        >
          {isLogin ? "Chưa có tài khoản? Đăng ký ngay" : "Đã có tài khoản? Đăng nhập tại đây"}
        </button>
      </div>
    </>
  );
}

export default function AuthPage() {
  return (
    <div className="min-h-screen app-bg flex items-center justify-center p-6 font-sans relative overflow-hidden">
      <Link
        href="/"
        className="absolute top-8 left-8 flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.2em] text-slate-500 hover:text-amber-700 transition-all group"
      >
        <ChevronLeft size={16} className="group-hover:-translate-x-1 transition-transform" />
        Trang chủ
      </Link>

      <div className="absolute top-0 right-0 -mr-20 -mt-20 w-[500px] h-[500px] bg-amber-100 rounded-full blur-[120px] opacity-50" />
      <div className="absolute bottom-0 left-0 -ml-20 -mb-20 w-[500px] h-[500px] bg-orange-100 rounded-full blur-[120px] opacity-40" />

      <div className="max-w-[540px] w-full hero-panel p-6 sm:p-8 md:p-10 space-y-8 relative z-10 animate-in fade-in zoom-in duration-500">
        <Suspense
          fallback={
            <div className="flex flex-col items-center justify-center h-40 space-y-4">
              <Loader2 className="animate-spin text-amber-700" size={32} />
              <p className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Đang tải...</p>
            </div>
          }
        >
          <AuthContent />
        </Suspense>
      </div>
    </div>
  );
}
