"use client";

import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "react-hot-toast";
import {
  ArrowRight,
  BookOpen,
  FileText,
  FolderOpen,
  GraduationCap,
  LayoutDashboard,
  LibraryBig,
  Plus,
  Sparkles,
  Users,
} from "lucide-react";

type SubjectItem = {
  id: number;
  name: string;
  description?: string;
  icon?: string;
  class_count?: number;
};

type ClassroomItem = {
  id: number;
  name: string;
  subject_id: number;
  subject: string;
  class_code: string;
  teacher_id: number;
  student_count?: number;
};

type DocumentItem = {
  id: number;
  title?: string;
  filename?: string;
  subject?: string;
  is_visible_to_students?: boolean;
};

type TeacherModuleCardProps = {
  title: string;
  description: string;
  href: string;
  icon: React.ReactNode;
  metric: string;
  chips?: string[];
  accentClass: string;
};

function TeacherModuleCard({
  title,
  description,
  href,
  icon,
  metric,
  chips = [],
  accentClass,
}: TeacherModuleCardProps) {
  return (
    <Link href={href} className="section-panel group p-5 transition-all hover:-translate-y-1">
      <div className="flex items-start justify-between gap-4">
        <div className={`flex h-11 w-11 items-center justify-center rounded-[1rem] ${accentClass}`}>
          {icon}
        </div>
        <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-slate-500">
          {metric}
        </span>
      </div>

      <h3 className="mt-4 text-base font-black text-slate-900">{title}</h3>
      <p className="mt-2 text-sm leading-6 text-slate-600">{description}</p>

      {chips.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {chips.slice(0, 3).map((chip) => (
            <span
              key={chip}
              className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-600"
            >
              {chip}
            </span>
          ))}
        </div>
      ) : null}

      <div className="mt-4 flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.18em] text-[var(--brand)]">
        <span>Mở khu vực</span>
        <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
      </div>
    </Link>
  );
}

export default function TeacherPage() {
  const router = useRouter();
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8010";

  const [teacherId, setTeacherId] = useState<string | null>(null);
  const [subjects, setSubjects] = useState<SubjectItem[]>([]);
  const [allClasses, setAllClasses] = useState<ClassroomItem[]>([]);
  const [documents, setDocuments] = useState<DocumentItem[]>([]);

  const [loadingOverview, setLoadingOverview] = useState(true);
  const [loadingDocuments, setLoadingDocuments] = useState(false);

  const [selectedSubjectId, setSelectedSubjectId] = useState<number | null>(null);
  const [selectedClassId, setSelectedClassId] = useState<number | null>(null);

  useEffect(() => {
    const role = localStorage.getItem("role");
    const userId = localStorage.getItem("userId");

    if (role !== "teacher" || !userId) {
      router.push("/auth");
      return;
    }

    setTeacherId(userId);
  }, [router]);

  useEffect(() => {
    if (!teacherId) return;
    void loadOverview(teacherId);
  }, [teacherId]);

  const filteredClasses = useMemo(() => {
    if (!selectedSubjectId) return [];
    return allClasses.filter((item) => item.subject_id === selectedSubjectId);
  }, [allClasses, selectedSubjectId]);

  const selectedSubject = useMemo(
    () => subjects.find((item) => item.id === selectedSubjectId) || null,
    [subjects, selectedSubjectId]
  );

  const selectedClass = useMemo(
    () => allClasses.find((item) => item.id === selectedClassId) || null,
    [allClasses, selectedClassId]
  );

  const totalStudents = useMemo(
    () => allClasses.reduce((sum, item) => sum + Number(item.student_count || 0), 0),
    [allClasses]
  );

  const visibleDocuments = useMemo(
    () => documents.filter((item) => item.is_visible_to_students).length,
    [documents]
  );

  useEffect(() => {
    if (!subjects.length) {
      setSelectedSubjectId(null);
      return;
    }

    setSelectedSubjectId((current) => {
      if (current && subjects.some((item) => item.id === current)) {
        return current;
      }

      const storedClassId = Number(localStorage.getItem("currentClassId") || localStorage.getItem("classId"));
      if (storedClassId) {
        const matchedClass = allClasses.find((item) => item.id === storedClassId);
        if (matchedClass) {
          return matchedClass.subject_id;
        }
      }

      return subjects[0]?.id ?? null;
    });
  }, [subjects, allClasses]);

  useEffect(() => {
    if (!filteredClasses.length) {
      setSelectedClassId(null);
      return;
    }

    setSelectedClassId((current) => {
      if (current && filteredClasses.some((item) => item.id === current)) {
        return current;
      }

      const storedClassId = Number(localStorage.getItem("currentClassId") || localStorage.getItem("classId"));
      if (storedClassId && filteredClasses.some((item) => item.id === storedClassId)) {
        return storedClassId;
      }

      return filteredClasses[0]?.id ?? null;
    });
  }, [filteredClasses]);

  useEffect(() => {
    if (!selectedClassId) {
      setDocuments([]);
      return;
    }

    localStorage.setItem("currentClassId", String(selectedClassId));
    localStorage.setItem("classId", String(selectedClassId));
    void loadDocuments(selectedClassId);
  }, [selectedClassId]);

  const loadOverview = async (id: string) => {
    setLoadingOverview(true);
    try {
      const [subjectsRes, classesRes] = await Promise.all([
        axios.get(`${apiBaseUrl}/api/subjects`),
        axios.get(`${apiBaseUrl}/api/classroom/teacher/${id}`),
      ]);

      const subjectList = Array.isArray(subjectsRes.data) ? subjectsRes.data : [];
      const classList = Array.isArray(classesRes.data) ? classesRes.data : [];

      classList.sort((a: ClassroomItem, b: ClassroomItem) => b.id - a.id);

      setSubjects(subjectList);
      setAllClasses(classList);
    } catch {
      toast.error("Không thể tải dữ liệu tổng quan giảng viên");
      setSubjects([]);
      setAllClasses([]);
    } finally {
      setLoadingOverview(false);
    }
  };

  const loadDocuments = async (classId: number) => {
    setLoadingDocuments(true);
    try {
      const res = await axios.get(`${apiBaseUrl}/api/upload/documents`, {
        params: { class_id: classId },
      });
      setDocuments(Array.isArray(res.data) ? res.data : []);
    } catch {
      setDocuments([]);
      toast.error("Không thể tải tài liệu của lớp đang chọn");
    } finally {
      setLoadingDocuments(false);
    }
  };

  const subjectChips = useMemo(
    () => subjects.slice(0, 3).map((item) => `${item.icon ? `${item.icon} ` : ""}${item.name}`),
    [subjects]
  );

  const classChips = useMemo(
    () => filteredClasses.slice(0, 3).map((item) => item.name),
    [filteredClasses]
  );

  const documentChips = useMemo(
    () =>
      documents
        .slice(0, 3)
        .map((item) => String(item.title || item.filename || `Tài liệu ${item.id}`)),
    [documents]
  );

  return (
    <div className="page-shell app-bg">
      <div className="page-container space-y-5">
        <section className="hero-panel overflow-hidden">
          <div className="grid gap-0 xl:grid-cols-[1.08fr_0.92fr]">
            <div className="soft-grid border-b border-[rgba(15,23,42,0.08)] p-5 md:p-6 xl:border-b-0 xl:border-r">
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 items-center justify-center rounded-[1.15rem] bg-[rgba(140,59,46,0.08)] text-[var(--brand)]">
                  <LayoutDashboard className="h-5 w-5" />
                </div>
                <div className="max-w-3xl">
                  <p className="text-[10px] font-black uppercase tracking-[0.26em] text-slate-400">
                    Tổng quan giảng viên
                  </p>
                  <h1 className="mt-2 text-2xl font-black text-[#251917] md:text-4xl">
                    Không gian điều phối học phần
                  </h1>
                  <p className="mt-3 text-sm leading-7 text-slate-600">
                    Trang này tổng hợp các khu vực quản lý môn học, lớp học, học viên,
                    tài liệu, ngân hàng câu hỏi và sinh đề thi. Các thao tác chi tiết sẽ
                    mở sang đúng trang chức năng thay vì dồn hết vào một màn hình.
                  </p>
                </div>
              </div>

              <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <div className="metric-panel p-4">
                  <p className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
                    Môn học
                  </p>
                  <p className="mt-1 text-2xl font-black text-slate-900">
                    {loadingOverview ? "..." : subjects.length}
                  </p>
                </div>
                <div className="metric-panel p-4">
                  <p className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
                    Lớp học
                  </p>
                  <p className="mt-1 text-2xl font-black text-slate-900">
                    {loadingOverview ? "..." : allClasses.length}
                  </p>
                </div>
                <div className="metric-panel p-4">
                  <p className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
                    Học viên
                  </p>
                  <p className="mt-1 text-2xl font-black text-slate-900">
                    {loadingOverview ? "..." : totalStudents}
                  </p>
                </div>
                <div className="metric-panel p-4">
                  <p className="text-[10px] font-black uppercase tracking-[0.24em] text-slate-400">
                    Tài liệu lớp chọn
                  </p>
                  <p className="mt-1 text-2xl font-black text-slate-900">
                    {selectedClassId ? documents.length : 0}
                  </p>
                </div>
              </div>
            </div>

            <div className="section-panel rounded-none border-0 p-5 md:p-6">
              <p className="text-[10px] font-black uppercase tracking-[0.26em] text-slate-400">
                Thao tác nhanh
              </p>
              <div className="mt-4 grid gap-3">
                <Link
                  href="/teacher/subjects?mode=create_subject"
                  className="flex items-center justify-between rounded-[1.2rem] border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-800 transition-all hover:border-[var(--brand)] hover:text-[var(--brand)]"
                >
                  <span className="flex items-center gap-2">
                    <Plus className="h-4 w-4" />
                    Tạo môn học mới
                  </span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  href={
                    selectedSubjectId
                      ? `/teacher/subjects?subject_id=${selectedSubjectId}&mode=create_class`
                      : "/teacher/subjects"
                  }
                  className="flex items-center justify-between rounded-[1.2rem] border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-800 transition-all hover:border-[var(--brand)] hover:text-[var(--brand)]"
                >
                  <span className="flex items-center gap-2">
                    <GraduationCap className="h-4 w-4" />
                    Tạo lớp cho môn đang chọn
                  </span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  href="/teacher/documents"
                  className="flex items-center justify-between rounded-[1.2rem] border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-800 transition-all hover:border-[var(--brand)] hover:text-[var(--brand)]"
                >
                  <span className="flex items-center gap-2">
                    <FolderOpen className="h-4 w-4" />
                    Mở kho tài liệu
                  </span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
                <Link
                  href="/teacher/exam"
                  className="flex items-center justify-between rounded-[1.2rem] border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-800 transition-all hover:border-[var(--brand)] hover:text-[var(--brand)]"
                >
                  <span className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4" />
                    Tạo đề & chấm OMR
                  </span>
                  <ArrowRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <TeacherModuleCard
            title="Quản lý môn học"
            description="Thêm, sửa, xóa môn học; từ từng môn có thể đi tiếp sang tạo lớp và nạp học liệu."
            href="/teacher/subjects"
            icon={<BookOpen className="h-5 w-5 text-sky-700" />}
            metric={`${subjects.length} môn`}
            chips={subjectChips}
            accentClass="bg-sky-50"
          />
          <TeacherModuleCard
            title="Lớp và học viên"
            description="Theo dõi học viên trong từng lớp, xem thống kê điểm, lịch sử bài thi và xuất báo cáo."
            href="/teacher/members"
            icon={<Users className="h-5 w-5 text-emerald-700" />}
            metric={`${totalStudents} học viên`}
            chips={classChips}
            accentClass="bg-emerald-50"
          />
          <TeacherModuleCard
            title="Kho tài liệu"
            description="Quản lý file tài liệu, bật hiển thị cho sinh viên và kiểm tra nhanh trạng thái từng file."
            href="/teacher/documents"
            icon={<FolderOpen className="h-5 w-5 text-amber-700" />}
            metric={`${documents.length} tài liệu`}
            chips={documentChips}
            accentClass="bg-amber-50"
          />
          <TeacherModuleCard
            title="Ngân hàng câu hỏi"
            description="Xem bộ câu hỏi theo tài liệu, thêm 10 câu mới, chỉnh tay và kiểm tra nội dung đã lưu."
            href="/teacher/question-bank"
            icon={<LibraryBig className="h-5 w-5 text-violet-700" />}
            metric={selectedSubject ? selectedSubject.name : "Chưa chọn môn"}
            chips={selectedClass ? [selectedClass.name] : []}
            accentClass="bg-violet-50"
          />
          <TeacherModuleCard
            title="Tạo đề & chấm OMR"
            description="Tạo đề trắc nghiệm Word, tải phiếu OMR, biểu mẫu đáp án Excel và chấm bài bằng PDF hoặc ảnh trên cùng một màn hình."
            href="/teacher/exam"
            icon={<FileText className="h-5 w-5 text-rose-700" />}
            metric={allClasses.length ? `${allClasses.length} lớp dùng được` : "Chưa có lớp"}
            chips={selectedClass ? [selectedClass.subject, selectedClass.name] : []}
            accentClass="bg-rose-50"
          />
        </section>

      </div>
    </div>
  );
}
