"use client";

import { useEffect, useMemo, useRef, useState, type ComponentType } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import clsx from "clsx";
import {
  Bell,
  BookOpen,
  BrainCircuit,
  ChevronDown,
  FileText,
  GraduationCap,
  KeyRound,
  LayoutDashboard,
  LibraryBig,
  LineChart,
  LogOut,
  Menu,
  ShieldCheck,
  UserPlus,
  Users,
  X,
} from "lucide-react";
import { confirmAlert } from "@/services/alerts";

type NavItem = {
  name: string;
  href: string;
  icon: ComponentType<{ size?: number; className?: string }>;
};

type NotificationItem = {
  id: number;
  title: string;
  body: string;
  is_read: boolean;
};

type StoredUser = {
  role: string | null;
  name: string | null;
  id: string | null;
  userId: string | null;
};

function readStoredUser(): StoredUser {
  if (typeof window === "undefined") {
    return { role: null, name: null, id: null, userId: null };
  }

  const rawRole = localStorage.getItem("role");
  const role = rawRole ? rawRole.toLowerCase() : null;
  const name = localStorage.getItem("fullname");
  const studentId =
    localStorage.getItem("studentId") ||
    localStorage.getItem("mssv") ||
    localStorage.getItem("username");
  const userId = localStorage.getItem("userId");
  const idDisplay = role === "student" ? studentId : userId;

  return { role, name, id: idDisplay, userId };
}

export default function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  const notificationRef = useRef<HTMLDivElement | null>(null);
  const profileRef = useRef<HTMLDivElement | null>(null);
  const mobileMenuRef = useRef<HTMLDivElement | null>(null);

  const [user] = useState<StoredUser>(() => readStoredUser());
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    if (!user.userId) {
      return;
    }

    void (async () => {
      try {
        const res = await fetch(`${apiBaseUrl}/api/notifications/${user.userId}`);
        const data = await res.json();
        setNotifications(Array.isArray(data?.items) ? data.items : []);
        setUnreadCount(Number(data?.unread_count || 0));
      } catch {
        setNotifications([]);
        setUnreadCount(0);
      }
    })();
  }, [apiBaseUrl, pathname, user.userId]);

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (notificationRef.current && !notificationRef.current.contains(target)) {
        setNotificationsOpen(false);
      }
      if (profileRef.current && !profileRef.current.contains(target)) {
        setProfileOpen(false);
      }
      if (mobileMenuRef.current && !mobileMenuRef.current.contains(target)) {
        setMobileMenuOpen(false);
      }
    };

    window.addEventListener("pointerdown", handlePointerDown);
    return () => window.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  const handleMarkAllRead = async () => {
    if (!user.userId) return;
    try {
      await fetch(`${apiBaseUrl}/api/notifications/mark-all-read/${user.userId}`, { method: "POST" });
      setNotifications((prev) => prev.map((item) => ({ ...item, is_read: true })));
      setUnreadCount(0);
    } catch {}
  };

  const handleLogout = async () => {
    const confirmed = await confirmAlert({
      title: "Đăng xuất",
      message: "Bạn có chắc chắn muốn đăng xuất?",
      confirmText: "Đăng xuất",
      cancelText: "Ở lại",
      tone: "danger",
    });
    if (!confirmed) return;
    localStorage.clear();
    router.push("/auth");
  };

  const getHomeHref = () => {
    if (user.role === "admin") return "/admin/teachers";
    if (user.role === "teacher") return "/teacher";
    if (user.role === "student") return "/adaptive";
    return "/auth";
  };

  const navs = useMemo<NavItem[]>(() => {
    if (user.role === "admin") {
      return [
        { name: "Cấp tài khoản", href: "/admin/teachers", icon: UserPlus },
        { name: "Người dùng", href: "/admin/users", icon: Users },
      ];
    }

    if (user.role === "teacher") {
      return [
        { name: "Tổng quan", href: "/teacher", icon: LayoutDashboard },
        { name: "Môn học", href: "/teacher/subjects", icon: GraduationCap },
        { name: "Tài liệu", href: "/teacher/documents", icon: BookOpen },
        { name: "Ngân hàng câu hỏi", href: "/teacher/question-bank", icon: LibraryBig },
        { name: "Học viên", href: "/teacher/members", icon: Users },
        { name: "Đề thi", href: "/teacher/exam", icon: FileText },
      ];
    }

    if (user.role === "student") {
      return [
        { name: "Gia sư", href: "/adaptive", icon: GraduationCap },
        { name: "Lộ trình", href: "/planning", icon: BrainCircuit },
        { name: "Kiểm tra", href: "/assessment", icon: FileText },
        { name: "Đánh giá", href: "/evaluation", icon: LineChart },
        { name: "Thư viện", href: "/library", icon: BookOpen },
      ];
    }

    return [];
  }, [user.role]);

  const roleLabel =
    user.role === "admin" ? "Quản trị viên" : user.role === "teacher" ? "Giảng viên" : "Sinh viên";

  const isNavActive = (href: string) => {
    if (href === "/teacher" || href === "/adaptive") {
      return pathname === href;
    }
    return pathname === href || pathname.startsWith(`${href}/`);
  };

  if (pathname === "/" || pathname === "/auth") return null;
  if (!user.role) return null;

  return (
    <nav className="relative z-[9999] px-4 pt-4 sm:px-6 sm:pt-4 lg:px-8">
      <div ref={mobileMenuRef} className="mx-auto max-w-[94rem]">
        <div className="hero-panel px-4 py-3 sm:px-5">
          <div className="flex items-center justify-between gap-3">
            <Link
              href={getHomeHref()}
              className="flex min-w-0 items-center gap-3 rounded-full px-1 py-1 transition-transform hover:-translate-y-0.5"
            >
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[linear-gradient(180deg,#1d4ed8,#0f172a)] text-white shadow-[0_16px_28px_rgba(15,23,42,0.18)]">
                {user.role === "admin" ? <ShieldCheck size={20} /> : <BrainCircuit size={20} />}
              </div>
              <div className="min-w-0">
                <p className="truncate text-[10px] font-semibold uppercase tracking-[0.22em] text-slate-400">
                  Nova Campus
                </p>
                <p className="truncate text-sm font-semibold text-slate-950 sm:text-base">Không gian học tập</p>
              </div>
            </Link>

            <div className="hidden min-w-0 flex-1 justify-center lg:flex">
              <div className="flex items-center gap-1 rounded-full border border-white/70 bg-white/76 p-1.5 shadow-[0_14px_26px_rgba(15,23,42,0.06)] backdrop-blur-2xl">
                {navs.map((item) => {
                  const active = isNavActive(item.href);
                  return (
                    <Link
                      key={item.name}
                      href={item.href}
                      className={clsx(
                        "flex items-center gap-2 rounded-full px-4 py-2.5 text-sm font-medium transition-all",
                        active
                          ? "bg-[linear-gradient(180deg,#ffffff,#eef5ff)] text-slate-950 shadow-[0_10px_20px_rgba(0,113,227,0.16)] ring-1 ring-[rgba(0,113,227,0.12)]"
                          : "text-slate-500 hover:bg-white hover:text-slate-950",
                      )}
                    >
                      <item.icon size={16} className={active ? "text-[var(--brand)]" : "text-slate-400"} />
                      <span>{item.name}</span>
                    </Link>
                  );
                })}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <div ref={notificationRef} className="relative">
                <button
                  onClick={() => {
                    setNotificationsOpen((open) => !open);
                    setProfileOpen(false);
                  }}
                  className="relative flex h-11 w-11 items-center justify-center rounded-full border border-white/70 bg-white/82 text-slate-600 shadow-[0_10px_18px_rgba(15,23,42,0.05)] transition-all hover:text-slate-950"
                  title="Thông báo"
                >
                  <Bell size={18} />
                  {unreadCount > 0 ? (
                    <span className="absolute -right-0.5 -top-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[var(--brand)] px-1 text-[10px] font-bold text-white">
                      {unreadCount > 9 ? "9+" : unreadCount}
                    </span>
                  ) : null}
                </button>

                {notificationsOpen ? (
                  <div className="absolute right-0 top-14 z-[10020] w-[340px] rounded-[1.55rem] border border-white/80 bg-[rgba(255,255,255,0.94)] p-3 shadow-[0_28px_60px_rgba(15,23,42,0.14)] backdrop-blur-2xl">
                    <div className="mb-3 flex items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-semibold text-slate-950">Thông báo</p>
                        <p className="text-[11px] text-slate-500">Cập nhật mới trong lớp học và hệ thống.</p>
                      </div>
                      {unreadCount > 0 ? (
                        <button onClick={handleMarkAllRead} className="text-[11px] font-semibold text-[var(--brand)]">
                          Đánh dấu đã đọc
                        </button>
                      ) : null}
                    </div>

                    <div className="space-y-2">
                      {notifications.length === 0 ? (
                        <div className="rounded-[1.2rem] bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
                          Chưa có thông báo nào.
                        </div>
                      ) : (
                        notifications.map((item) => (
                          <div
                            key={item.id}
                            className={clsx(
                              "rounded-[1.2rem] border px-3.5 py-3",
                              item.is_read
                                ? "border-transparent bg-slate-50"
                                : "border-[rgba(0,113,227,0.12)] bg-[rgba(239,246,255,0.9)]",
                            )}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="text-sm font-semibold text-slate-950">{item.title}</p>
                                <p className="mt-1 text-sm leading-relaxed text-slate-600">{item.body}</p>
                              </div>
                              {!item.is_read ? <span className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-[var(--brand)]" /> : null}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                ) : null}
              </div>

              <div ref={profileRef} className="relative hidden sm:block">
                <button
                  onClick={() => {
                    setProfileOpen((open) => !open);
                    setNotificationsOpen(false);
                  }}
                  className="flex items-center gap-3 rounded-full border border-white/70 bg-white/84 px-3 py-2 shadow-[0_10px_18px_rgba(15,23,42,0.05)] transition-all hover:-translate-y-0.5"
                >
                  <div className="min-w-0 text-right">
                    <p className="truncate text-[11px] font-medium text-slate-500">{roleLabel}</p>
                    <p className="truncate text-sm font-semibold text-slate-950">{user.name || "Người dùng"}</p>
                  </div>
                  <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[linear-gradient(180deg,#eff6ff,#dbeafe)] text-[var(--brand)]">
                    <ChevronDown size={16} className={profileOpen ? "rotate-180 transition-transform" : "transition-transform"} />
                  </div>
                </button>

                {profileOpen ? (
                  <div className="absolute right-0 top-14 z-[10020] w-[250px] rounded-[1.55rem] border border-white/80 bg-[rgba(255,255,255,0.95)] p-3 shadow-[0_28px_60px_rgba(15,23,42,0.14)] backdrop-blur-2xl">
                    <div className="rounded-[1.2rem] bg-slate-50 px-4 py-3">
                      <p className="text-[11px] text-slate-500">{roleLabel}</p>
                      <p className="mt-0.5 text-sm font-semibold text-slate-950">{user.name || "Người dùng"}</p>
                      {user.id ? <p className="mt-1 font-mono text-[11px] text-slate-500">{user.id}</p> : null}
                    </div>

                    <div className="mt-3 space-y-2">
                      <Link
                        href="/change-password"
                        className="flex items-center gap-3 rounded-[1rem] px-3 py-3 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50 hover:text-slate-950"
                      >
                        <KeyRound size={16} />
                        <span>Đổi mật khẩu</span>
                      </Link>
                      <button
                        onClick={handleLogout}
                        className="flex w-full items-center gap-3 rounded-[1rem] px-3 py-3 text-left text-sm font-medium text-red-600 transition-colors hover:bg-red-50"
                      >
                        <LogOut size={16} />
                        <span>Đăng xuất</span>
                      </button>
                    </div>
                  </div>
                ) : null}
              </div>

              <button
                onClick={() => {
                  setMobileMenuOpen((open) => !open);
                  setNotificationsOpen(false);
                  setProfileOpen(false);
                }}
                className="flex h-11 w-11 items-center justify-center rounded-full border border-white/70 bg-white/82 text-slate-700 shadow-[0_10px_18px_rgba(15,23,42,0.05)] lg:hidden"
                title="Menu"
              >
                {mobileMenuOpen ? <X size={18} /> : <Menu size={18} />}
              </button>
            </div>
          </div>

          {mobileMenuOpen ? (
            <div className="mt-4 space-y-4 border-t border-white/70 pt-4 lg:hidden">
              <div className="grid gap-2">
                {navs.map((item) => {
                  const active = isNavActive(item.href);
                  return (
                    <Link
                      key={item.name}
                      href={item.href}
                      className={clsx(
                        "flex items-center justify-between rounded-[1.3rem] px-4 py-3 text-sm font-medium transition-all",
                        active
                          ? "bg-[linear-gradient(180deg,#ffffff,#eef5ff)] text-slate-950 shadow-[0_12px_22px_rgba(0,113,227,0.12)]"
                          : "bg-white/78 text-slate-600",
                      )}
                    >
                      <span className="flex items-center gap-3">
                        <item.icon size={16} className={active ? "text-[var(--brand)]" : "text-slate-400"} />
                        {item.name}
                      </span>
                      <ChevronDown size={16} className="-rotate-90 text-slate-400" />
                    </Link>
                  );
                })}
              </div>

              <div className="section-panel flex items-center justify-between px-4 py-3 sm:hidden">
                <div className="min-w-0">
                  <p className="text-[11px] text-slate-500">{roleLabel}</p>
                  <p className="truncate text-sm font-semibold text-slate-950">{user.name || "Người dùng"}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Link
                    href="/change-password"
                    className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-700"
                  >
                    <KeyRound size={16} />
                  </Link>
                  <button
                    onClick={handleLogout}
                    className="flex h-10 w-10 items-center justify-center rounded-full bg-red-50 text-red-600"
                  >
                    <LogOut size={16} />
                  </button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </nav>
  );
}
