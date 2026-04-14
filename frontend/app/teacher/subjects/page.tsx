'use client';

import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import { toast } from 'react-hot-toast';
import {
  LibraryBig,
  Plus,
  Pencil,
  Trash2,
  Loader2,
  FolderOpen,
  FileText,
  Save,
  X,
  Copy,
  Check,
} from 'lucide-react';
import { useRouter, useSearchParams } from 'next/navigation';
import FileUploader from '@/components/FileUploader';
import DocumentManager from '@/components/DocumentManager';

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
};

const SUBJECT_ICON_OPTIONS = [
  '📘',
  '📚',
  '🧠',
  '⚛️',
  '🧪',
  '🧬',
  '📐',
  '📉',
  '💻',
  '🌍',
  '🗺️',
  '🏛️',
  '🎨',
  '🎵',
  '⚙️',
  '🧩',
  '📦',
  '🔗',
  '🖥️',
  '📡',
];

export default function TeacherSubjectsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [subjects, setSubjects] = useState<SubjectItem[]>([]);
  const [classes, setClasses] = useState<ClassroomItem[]>([]);
  const [loadingSubjects, setLoadingSubjects] = useState(true);
  const [loadingClasses, setLoadingClasses] = useState(false);

  const [selectedSubjectId, setSelectedSubjectId] = useState<number | null>(null);
  const [selectedClassId, setSelectedClassId] = useState<number | null>(null);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [icon, setIcon] = useState('');
  const [editingSubjectId, setEditingSubjectId] = useState<number | null>(null);

  const [newClassName, setNewClassName] = useState('');
  const [editingClassId, setEditingClassId] = useState<number | null>(null);
  const [editingClassName, setEditingClassName] = useState('');

  const [savingSubject, setSavingSubject] = useState(false);
  const [savingClass, setSavingClass] = useState(false);
  const [copiedClassId, setCopiedClassId] = useState<number | null>(null);

  const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
  const teacherId = typeof window !== 'undefined' ? localStorage.getItem('userId') : null;

  const authHeaders = token ? { Authorization: `Bearer ${token}` } : {};

  const selectedSubject = useMemo(
    () => subjects.find((s) => s.id === selectedSubjectId) || null,
    [subjects, selectedSubjectId]
  );

  const normalizeName = (value: string) => value.trim().toLowerCase();

  const managementMode = searchParams.get('mode') || '';
  const targetSubjectName = (searchParams.get('subject') || (typeof window !== 'undefined' ? localStorage.getItem('novaTargetSubject') : '') || '').trim();
  const targetSubjectIdParam = (searchParams.get('subject_id') || (typeof window !== 'undefined' ? localStorage.getItem('novaTargetSubjectId') : '') || '').trim();
  const targetClassName = (searchParams.get('class_name') || (typeof window !== 'undefined' ? localStorage.getItem('novaTargetClass') : '') || '').trim();
  const targetDocumentName = (searchParams.get('document_name') || (typeof window !== 'undefined' ? localStorage.getItem('novaTargetDocument') : '') || '').trim();
  const targetClassIdParam = (searchParams.get('class_id') || (typeof window !== 'undefined' ? localStorage.getItem('novaTargetClassId') : '') || '').trim();

  const mappedUploaderClasses = useMemo(
    () =>
      classes.map((c) => ({
        id: c.id,
        name: c.name,
        subject: c.subject,
        subject_name: c.subject,
        class_code: c.class_code,
      })),
    [classes]
  );

  const resetSubjectForm = () => {
    setName('');
    setDescription('');
    setIcon(SUBJECT_ICON_OPTIONS[0]);
    setEditingSubjectId(null);
  };

  const loadSubjects = async () => {
    setLoadingSubjects(true);
    try {
      const res = await axios.get('http://localhost:8000/api/subjects');
      const list = res.data || [];
      setSubjects(list);
      if (managementMode === 'create_subject') {
        setSelectedSubjectId(null);
        setSelectedClassId(null);
      } else if (!selectedSubjectId && list.length > 0) {
        setSelectedSubjectId(list[0].id);
      }
      if (selectedSubjectId && !list.some((s: SubjectItem) => s.id === selectedSubjectId)) {
        setSelectedSubjectId(list.length > 0 ? list[0].id : null);
      }
    } catch {
      toast.error('Không thể tải danh sách môn học');
      setSubjects([]);
    } finally {
      setLoadingSubjects(false);
    }
  };

  const loadClassesBySubject = async (subjectId: number) => {
    if (!teacherId) return;
    setLoadingClasses(true);
    try {
      const res = await axios.get('http://localhost:8000/api/classroom/list', {
        params: { teacher_id: Number(teacherId), subject_id: subjectId },
      });
      const list = res.data || [];
      setClasses(list);
      if (list.length === 0) {
        setSelectedClassId(null);
      } else if (!selectedClassId || !list.some((c: ClassroomItem) => c.id === selectedClassId)) {
        setSelectedClassId(list[0].id);
      }
    } catch {
      setClasses([]);
      setSelectedClassId(null);
      toast.error('Không thể tải danh sách lớp theo môn học');
    } finally {
      setLoadingClasses(false);
    }
  };

  useEffect(() => {
    const role = localStorage.getItem('role');
    if (role !== 'teacher') {
      router.push('/auth');
      return;
    }
    if (!icon) {
      setIcon(SUBJECT_ICON_OPTIONS[0]);
    }
    loadSubjects();
  }, [router]);

  useEffect(() => {
    if (selectedSubjectId) {
      loadClassesBySubject(selectedSubjectId);
    } else {
      setClasses([]);
      setSelectedClassId(null);
    }
  }, [selectedSubjectId]);

  useEffect(() => {
    if (subjects.length === 0) return;

    if (managementMode === 'create_subject') {
      if (targetSubjectName) {
        setName(targetSubjectName);
        setEditingSubjectId(null);
      }
      if (typeof window !== 'undefined') {
        localStorage.removeItem('novaTargetSubject');
        localStorage.removeItem('novaTargetClass');
        localStorage.removeItem('novaTargetDocument');
      }
      return;
    }

    const subjectIdCandidate = targetSubjectIdParam && !Number.isNaN(Number(targetSubjectIdParam))
      ? subjects.find((item) => item.id === Number(targetSubjectIdParam))
      : null;

    if (subjectIdCandidate) {
      setSelectedSubjectId(subjectIdCandidate.id);
      if (typeof window !== 'undefined') {
        localStorage.removeItem('novaTargetSubjectId');
      }
      return;
    }

    const rawTarget = targetSubjectName;
    if (!rawTarget) return;

    const targetName = normalizeName(rawTarget);
    const matched = subjects.find((s) => normalizeName(s.name || '') === targetName);

    if (matched) {
      setSelectedSubjectId(matched.id);
      if (typeof window !== 'undefined') {
        localStorage.removeItem('novaTargetSubject');
      }
      return;
    }

    if (typeof window !== 'undefined' && managementMode !== 'create_class') {
      localStorage.removeItem('novaTargetSubject');
    }
    if (managementMode !== 'create_class') {
      toast.error(`Không tìm thấy môn học "${rawTarget}" trong danh sách.`);
    }
  }, [subjects, searchParams]);

  useEffect(() => {
    if (subjects.length === 0) return;
    if (!targetClassName && !targetClassIdParam) return;

    const matchedByName = targetClassName
      ? classes.find((item) => normalizeName(item.name || '') === normalizeName(targetClassName))
      : null;
    const matchedById = targetClassIdParam && !Number.isNaN(Number(targetClassIdParam))
      ? classes.find((item) => item.id === Number(targetClassIdParam))
      : null;

    const matchedClass = matchedById || matchedByName;
    if (matchedClass) {
      setSelectedClassId(matchedClass.id);
      if (typeof window !== 'undefined') {
        localStorage.removeItem('novaTargetClass');
      }
    }

    if (managementMode === 'create_class' && targetClassName) {
      setNewClassName(targetClassName);
    }

    if (managementMode === 'upload_document' && targetClassName && !matchedClass) {
      toast.error(`Không tìm thấy lớp học "${targetClassName}" trong danh sách.`);
    }
  }, [classes, subjects.length, targetClassName, targetClassIdParam, managementMode]);

  const handleSaveSubject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      toast.error('Vui lòng nhập tên môn học');
      return;
    }
    if (!token) {
      toast.error('Thiếu token xác thực. Vui lòng đăng nhập lại.');
      return;
    }

    setSavingSubject(true);
    try {
      if (editingSubjectId) {
        await axios.put(
          `http://localhost:8000/api/subjects/${editingSubjectId}`,
          { name: name.trim(), description: description.trim() || null, icon: icon.trim() || null },
          { headers: authHeaders }
        );
        toast.success('Cập nhật môn học thành công');
      } else {
        await axios.post(
          'http://localhost:8000/api/subjects',
          { name: name.trim(), description: description.trim() || null, icon: icon.trim() || null },
          { headers: authHeaders }
        );
        toast.success('Tạo môn học thành công');
      }
      resetSubjectForm();
      await loadSubjects();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Lỗi khi lưu môn học');
    } finally {
      setSavingSubject(false);
    }
  };

  const handleEditSubject = (s: SubjectItem) => {
    setEditingSubjectId(s.id);
    setName(s.name || '');
    setDescription(s.description || '');
    setIcon(s.icon || SUBJECT_ICON_OPTIONS[0]);
  };

  const handleDeleteSubject = async (s: SubjectItem) => {
    if (!token) {
      toast.error('Thiếu token xác thực. Vui lòng đăng nhập lại.');
      return;
    }
    if (!window.confirm(`Xóa môn học "${s.name}"?`)) return;

    try {
      await axios.delete(`http://localhost:8000/api/subjects/${s.id}`, { headers: authHeaders });
      toast.success('Xóa môn học thành công');
      if (selectedSubjectId === s.id) {
        setSelectedSubjectId(null);
      }
      await loadSubjects();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Lỗi khi xóa môn học');
    }
  };

  const handleCreateClass = async () => {
    if (!newClassName.trim()) {
      toast.error('Vui lòng nhập tên lớp');
      return;
    }
    if (!selectedSubjectId || !teacherId) {
      toast.error('Vui lòng chọn môn học và đăng nhập lại');
      return;
    }

    setSavingClass(true);
    try {
      const res = await axios.post('http://localhost:8000/api/classroom/create', {
        name: newClassName.trim(),
        subject_id: selectedSubjectId,
        teacher_id: Number(teacherId),
      });
      toast.success('Tạo lớp thành công');
      setNewClassName('');
      await loadClassesBySubject(selectedSubjectId);
      if (res?.data?.id) {
        setSelectedClassId(res.data.id);
      }
      await loadSubjects();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Lỗi khi tạo lớp học');
    } finally {
      setSavingClass(false);
    }
  };

  const startEditClass = (item: ClassroomItem) => {
    setEditingClassId(item.id);
    setEditingClassName(item.name);
  };

  const cancelEditClass = () => {
    setEditingClassId(null);
    setEditingClassName('');
  };

  const handleCopyClassCode = (code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedClassId(code ? parseInt(code) : null);
    toast.success('Đã copy mã lớp');
    setTimeout(() => setCopiedClassId(null), 2000);
  };

  const handleSaveClass = async (classId: number) => {
    if (!editingClassName.trim() || !teacherId) {
      toast.error('Tên lớp học không hợp lệ');
      return;
    }

    setSavingClass(true);
    try {
      await axios.put(`http://localhost:8000/api/classroom/update/${classId}`, {
        name: editingClassName.trim(),
        teacher_id: Number(teacherId),
      });
      toast.success('Cập nhật lớp thành công');
      if (selectedSubjectId) {
        await loadClassesBySubject(selectedSubjectId);
      }
      cancelEditClass();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Lỗi khi cập nhật lớp học');
    } finally {
      setSavingClass(false);
    }
  };

  const handleDeleteClass = async (item: ClassroomItem) => {
    if (!teacherId) {
      toast.error('Thiếu thông tin giáo viên. Vui lòng đăng nhập lại.');
      return;
    }

    if (!window.confirm(`Xóa lớp "${item.name}"? Tài liệu của lớp sẽ bị xóa theo.`)) return;

    setSavingClass(true);
    try {
      await axios.delete(`http://localhost:8000/api/classroom/delete/${item.id}`, {
        params: { teacher_id: Number(teacherId) },
      });
      toast.success('Đã xóa lớp học');
      if (selectedClassId === item.id) {
        setSelectedClassId(null);
      }
      if (selectedSubjectId) {
        await loadClassesBySubject(selectedSubjectId);
      }
      await loadSubjects();
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Lỗi khi xóa lớp học');
    } finally {
      setSavingClass(false);
    }
  };

  return (
    <div className="min-h-[calc(100vh-4rem)] app-bg p-4 md:p-8">
      <div className="max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-6">
        <section className="lg:col-span-4 space-y-6">
          <div className="bg-white rounded-3xl border border-slate-200 p-6 flex items-center gap-4">
            <div className="w-12 h-12 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <LibraryBig size={24} />
            </div>
            <div>
              <h1 className="text-2xl font-black text-slate-800">Quản Lý Môn Học</h1>
              <p className="text-sm text-slate-500 font-medium">Chọn môn để quản lý lớp và tài liệu của môn đó</p>
            </div>
          </div>

          <form onSubmit={handleSaveSubject} className="bg-white rounded-3xl border border-slate-200 p-6 space-y-3">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Tên môn học"
              className="w-full px-4 py-3 rounded-xl border border-slate-200 font-semibold text-slate-900 outline-none focus:border-indigo-500"
            />
            <p className="text-xs font-black uppercase tracking-widest text-slate-500">Icon</p>
            <select
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              title="Chọn icon môn học"
              className="w-full px-4 py-3 rounded-xl border border-slate-200 font-semibold text-slate-900 outline-none focus:border-indigo-500"
            >
              {SUBJECT_ICON_OPTIONS.map((iconItem) => (
                <option key={iconItem} value={iconItem}>{iconItem}</option>
              ))}
            </select>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Mô tả (tuỳ chọn)"
              className="w-full px-4 py-3 rounded-xl border border-slate-200 font-semibold text-slate-900 outline-none focus:border-indigo-500"
            />
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={savingSubject}
                className="px-4 py-2.5 rounded-xl bg-indigo-600 text-white font-black text-xs uppercase tracking-widest hover:bg-indigo-700 disabled:opacity-60 flex items-center gap-2"
              >
                {savingSubject ? <Loader2 size={16} className="animate-spin" /> : <Plus size={16} />}
                {editingSubjectId ? 'Lưu môn' : 'Thêm môn'}
              </button>
              {editingSubjectId && (
                <button
                  type="button"
                  onClick={resetSubjectForm}
                  className="px-4 py-2.5 rounded-xl bg-slate-100 text-slate-700 font-black text-xs uppercase tracking-widest"
                >
                  Hủy
                </button>
              )}
            </div>
          </form>

          <div className="bg-white rounded-3xl border border-slate-200 p-4">
            {loadingSubjects ? (
              <div className="py-10 text-center text-slate-400 font-bold text-xs uppercase">Đang tải môn học...</div>
            ) : subjects.length === 0 ? (
              <div className="py-10 text-center text-slate-400 font-bold text-xs uppercase">Chưa có môn học</div>
            ) : (
              <div className="space-y-2 max-h-[420px] overflow-auto pr-1">
                {subjects.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setSelectedSubjectId(s.id)}
                    className={`w-full text-left p-4 rounded-2xl border transition-all ${
                      selectedSubjectId === s.id
                        ? 'bg-indigo-50 border-indigo-200'
                        : 'bg-slate-50 border-slate-200 hover:bg-slate-100'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="font-black text-slate-800 text-sm truncate">{s.icon ? `${s.icon} ` : ''}{s.name}</p>
                        <p className="text-xs text-slate-500">Số lớp: {s.class_count || 0}</p>
                        {s.description && <p className="text-xs text-slate-500 mt-1 truncate">{s.description}</p>}
                      </div>
                      <div className="flex gap-1 shrink-0">
                        <span
                          onClick={(e) => {
                            e.stopPropagation();
                            handleEditSubject(s);
                          }}
                          className="p-2 rounded-lg text-indigo-600 hover:bg-indigo-100"
                          title="Sửa môn học"
                        >
                          <Pencil size={16} />
                        </span>
                        <span
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteSubject(s);
                          }}
                          className="p-2 rounded-lg text-red-500 hover:bg-red-100"
                          title="Xóa môn học"
                        >
                          <Trash2 size={16} />
                        </span>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="lg:col-span-8 space-y-6">
          {!selectedSubject ? (
            <div className="bg-white rounded-3xl border border-dashed border-slate-200 p-12 text-center text-slate-400 font-bold text-sm">
              Chọn một môn học để quản lý lớp và học liệu
            </div>
          ) : (
            <>
              <div className="bg-white rounded-3xl border border-slate-200 p-6 space-y-4">
                <div className="flex items-center gap-2 text-slate-800">
                  <FolderOpen size={20} className="text-indigo-600" />
                  <h2 className="text-lg font-black">Lớp học thuộc môn: {selectedSubject.name}</h2>
                </div>

                <div className="flex gap-2">
                  <input
                    value={newClassName}
                    onChange={(e) => setNewClassName(e.target.value)}
                    placeholder="Thêm lớp mới cho môn này"
                    className="flex-1 px-4 py-2.5 rounded-xl border border-slate-200 text-slate-900 font-semibold outline-none focus:border-indigo-500"
                  />
                  <button
                    onClick={handleCreateClass}
                    disabled={savingClass}
                    className="px-4 py-2.5 rounded-xl bg-indigo-600 text-white font-black text-xs uppercase tracking-widest hover:bg-indigo-700 disabled:opacity-60"
                  >
                    {savingClass ? <Loader2 size={16} className="animate-spin" /> : 'Thêm lớp'}
                  </button>
                </div>

                {loadingClasses ? (
                  <div className="py-8 text-center text-slate-400 font-bold text-xs uppercase">Đang tải lớp...</div>
                ) : classes.length === 0 ? (
                  <div className="py-8 text-center text-slate-400 font-bold text-xs uppercase border border-dashed border-slate-200 rounded-2xl">
                    Môn này chưa có lớp
                  </div>
                ) : (
                  <div className="space-y-2">
                    {classes.map((item) => (
                      <div
                        key={item.id}
                        className={`p-3 rounded-xl border ${
                          selectedClassId === item.id ? 'border-indigo-200 bg-indigo-50' : 'border-slate-200 bg-slate-50'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <button
                            onClick={() => setSelectedClassId(item.id)}
                            className="text-left min-w-0 flex-1"
                          >
                            {editingClassId === item.id ? (
                              <input
                                value={editingClassName}
                                onChange={(e) => setEditingClassName(e.target.value)}
                                className="w-full px-3 py-2 rounded-lg border border-slate-300 text-slate-900 font-semibold outline-none focus:border-indigo-500"
                              />
                            ) : (
                              <>
                                <p className="font-black text-slate-800 text-sm truncate">{item.name}</p>
                                <p className="text-xs text-slate-500">Mã lớp: {item.class_code}</p>
                              </>
                            )}
                          </button>

                          {editingClassId === item.id ? (
                            <div className="flex gap-1">
                              <button
                                onClick={() => handleSaveClass(item.id)}
                                className="p-2 rounded-lg text-emerald-600 hover:bg-emerald-100"
                                title="Lưu tên lớp"
                              >
                                <Save size={16} />
                              </button>
                              <button
                                onClick={cancelEditClass}
                                className="p-2 rounded-lg text-slate-600 hover:bg-slate-200"
                                title="Hủy sửa"
                              >
                                <X size={16} />
                              </button>
                            </div>
                          ) : (
                            <div className="flex gap-1">
                              <button
                                onClick={() => handleCopyClassCode(item.class_code)}
                                className={`p-2 rounded-lg ${
                                  copiedClassId === item.id
                                    ? 'text-emerald-600 bg-emerald-100'
                                    : 'text-slate-500 hover:bg-slate-100'
                                }`}
                                title="Copy mã lớp"
                              >
                                {copiedClassId === item.id ? <Check size={16} /> : <Copy size={16} />}
                              </button>
                              <button
                                onClick={() => startEditClass(item)}
                                className="p-2 rounded-lg text-indigo-600 hover:bg-indigo-100"
                                title="Sửa lớp học"
                              >
                                <Pencil size={16} />
                              </button>
                              <button
                                onClick={() => handleDeleteClass(item)}
                                className="p-2 rounded-lg text-red-500 hover:bg-red-100"
                                title="Xóa lớp học"
                              >
                                <Trash2 size={16} />
                              </button>
                            </div>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="bg-white rounded-3xl border border-slate-200 p-6 space-y-4">
                <div className="flex items-center gap-2 text-slate-800">
                  <FileText size={20} className="text-indigo-600" />
                  <h2 className="text-lg font-black">Quản lý học liệu của môn</h2>
                </div>
                <p className="text-sm font-medium text-slate-500">
                  Chọn lớp trong môn để thêm/xóa tài liệu. Luồng upload vẫn gắn theo class_id để AI agents truy cập đúng kho tri thức.
                </p>

                {selectedClassId ? (
                  <>
                    <div className="bg-indigo-50 border border-indigo-100 rounded-2xl p-4">
                      <p className="text-xs font-black uppercase tracking-widest text-indigo-700 mb-3">Nạp tài liệu cho lớp đã chọn</p>
                      <FileUploader
                        teacherId={teacherId}
                        classId={selectedClassId}
                        externalClasses={mappedUploaderClasses}
                        onUploadSuccess={() => toast.success('Đã nạp tài liệu thành công')}
                      />
                    </div>

                    <DocumentManager classId={selectedClassId} />
                  </>
                ) : (
                  <div className="py-8 text-center text-slate-400 font-bold text-xs uppercase border border-dashed border-slate-200 rounded-2xl">
                    Hãy chọn lớp học để quản lý tài liệu
                  </div>
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
