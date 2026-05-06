"use client";

import AssessmentForm from "@/components/AssessmentForm";

export default function AssessmentPage() {
  return (
    <div className="page-shell">
      <div className="page-container">
        <div className="hero-panel soft-grid mb-8 px-6 py-8 text-center">
          <h1 className="display-font mb-2 text-3xl font-extrabold text-[#201915]">Assessment Control Room</h1>
          <p className="mx-auto max-w-2xl text-sm text-[#6f6156]">
            Chon dung ngu canh tai lieu, lam bai va nhan phan hoi tren cung mot phien hoc.
          </p>
        </div>

        <div className="flex justify-center">
          <div className="w-full max-w-5xl">
            <AssessmentForm />
          </div>
        </div>
      </div>
    </div>
  );
}
