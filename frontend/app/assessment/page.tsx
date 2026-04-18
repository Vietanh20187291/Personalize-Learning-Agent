"use client";

import React from 'react';
import AssessmentForm from '@/components/AssessmentForm'; 
import OrbitPanel from '@/components/OrbitPanel';

export default function AssessmentPage() {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8010';
  const orbitUserId = typeof window !== 'undefined'
    ? parseInt(localStorage.getItem('userId') || localStorage.getItem('user_id') || '0', 10)
    : 0;
  return (
    <>
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
    <OrbitPanel
      userId={orbitUserId}
      apiBaseUrl={apiBaseUrl}
      enrolledClasses={[]}
    />
    </>
  );
}