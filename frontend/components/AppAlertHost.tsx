"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, CircleAlert } from "lucide-react";

import { registerConfirmAlertHandler, type ConfirmAlertOptions } from "@/services/alerts";

type PendingConfirm = ConfirmAlertOptions & {
  resolve: (value: boolean) => void;
};

export default function AppAlertHost() {
  const [activeConfirm, setActiveConfirm] = useState<PendingConfirm | null>(null);
  const queueRef = useRef<PendingConfirm[]>([]);
  const activeRef = useRef(false);

  useEffect(() => {
    const pump = () => {
      if (activeRef.current || queueRef.current.length === 0) return;
      activeRef.current = true;
      setActiveConfirm(queueRef.current.shift() || null);
    };

    return registerConfirmAlertHandler((options) => {
      return new Promise<boolean>((resolve) => {
        queueRef.current.push({ ...options, resolve });
        pump();
      });
    });
  }, []);

  useEffect(() => {
    if (!activeConfirm) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        activeConfirm.resolve(false);
        activeRef.current = false;
        setActiveConfirm(null);
        window.setTimeout(() => {
          if (!activeRef.current && queueRef.current.length > 0) {
            activeRef.current = true;
            setActiveConfirm(queueRef.current.shift() || null);
          }
        }, 0);
      }
    };

    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = originalOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [activeConfirm]);

  const palette = useMemo(() => {
    if (activeConfirm?.tone === "danger") {
      return {
        iconWrap: "bg-rose-50 text-rose-500 border-rose-100",
        confirmBtn:
          "border border-rose-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(255,241,242,0.98))] text-rose-600 shadow-[0_12px_32px_rgba(244,63,94,0.12)]",
        icon: <AlertTriangle size={18} />,
      };
    }

    return {
      iconWrap: "bg-sky-50 text-sky-500 border-sky-100",
      confirmBtn:
        "border border-sky-200 bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(240,249,255,0.98))] text-sky-700 shadow-[0_12px_32px_rgba(14,165,233,0.12)]",
      icon: <CircleAlert size={18} />,
    };
  }, [activeConfirm?.tone]);

  const close = (confirmed: boolean) => {
    if (!activeConfirm) return;
    activeConfirm.resolve(confirmed);
    activeRef.current = false;
    setActiveConfirm(null);
    window.setTimeout(() => {
      if (!activeRef.current && queueRef.current.length > 0) {
        activeRef.current = true;
        setActiveConfirm(queueRef.current.shift() || null);
      }
    }, 0);
  };

  if (!activeConfirm) return null;

  return (
    <div className="fixed inset-0 z-[12000] flex items-center justify-center bg-white/28 p-4 backdrop-blur-[10px]">
      <div className="w-full max-w-md overflow-hidden rounded-[1.9rem] border border-white/80 bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(248,250,252,0.94))] shadow-[0_28px_80px_rgba(15,23,42,0.14)]">
        <div className="border-b border-slate-200/80 px-5 py-4">
          <div className="flex items-center gap-3">
            <div className={`flex h-11 w-11 items-center justify-center rounded-[1rem] border ${palette.iconWrap}`}>
              {palette.icon}
            </div>
            <div>
              <p className="text-[11px] font-semibold text-slate-400">Nova Campus</p>
              <h3 className="mt-0.5 text-[17px] font-semibold tracking-[-0.03em] text-slate-900">
                {activeConfirm.title || "Xác nhận thao tác"}
              </h3>
            </div>
          </div>
        </div>

        <div className="px-5 py-5">
          <p className="whitespace-pre-line text-[14px] leading-7 text-slate-600">{activeConfirm.message}</p>
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-slate-200/80 px-5 py-4">
          <button
            type="button"
            onClick={() => close(false)}
            className="inline-flex min-w-[92px] items-center justify-center rounded-full border border-slate-200 bg-white px-4 py-2.5 text-[12px] font-semibold text-slate-600 transition hover:bg-slate-50"
          >
            {activeConfirm.cancelText || "Hủy"}
          </button>
          <button
            type="button"
            onClick={() => close(true)}
            className={`inline-flex min-w-[120px] items-center justify-center rounded-full px-4 py-2.5 text-[12px] font-semibold transition hover:brightness-[1.02] ${palette.confirmBtn}`}
          >
            {activeConfirm.confirmText || "Xác nhận"}
          </button>
        </div>
      </div>
    </div>
  );
}
