"use client";

import React from 'react';
import AssessmentForm from '@/components/AssessmentForm'; 

export default function AssessmentPage() {
  return (
    <div className="page-shell">
      

      <div className="page-container">
        {/* 2. Phần tiêu đề trang */}
        <div className="hero-panel soft-grid text-center mb-8 py-8 px-6">
          <h1 className="display-font text-3xl font-extrabold text-slate-900 mb-2">
            AI Personalized Learning
          </h1>
          <div className="h-1 w-20 bg-teal-600 mx-auto rounded-full"></div>
        </div>

        {/* 3. Component chứa toàn bộ logic làm bài */}
        <div className="flex justify-center">
          <div className="w-full max-w-5xl">
            <AssessmentForm />
          </div>
        </div>
      </div>
    </div>
  );
}