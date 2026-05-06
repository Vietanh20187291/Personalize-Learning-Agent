import axios, { AxiosRequestConfig } from 'axios';

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8010';
export const API_URL = `${API_BASE_URL}/api`;

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 0,
});

export const longRequestConfig: AxiosRequestConfig = {
  timeout: 0,
};

const extractRequestId = (payload: unknown): string => {
  if (!payload || typeof payload !== 'object') return '';
  const requestId = (payload as Record<string, unknown>).request_id;
  return typeof requestId === 'string' ? requestId.trim() : '';
};

export const normalizeApiError = (error: unknown, fallback = 'Không thể hoàn tất yêu cầu lúc này.'): string => {
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data;
    const detail =
      typeof payload?.detail === 'string'
        ? payload.detail.trim()
        : typeof error.message === 'string' && error.message.trim()
          ? error.message.trim()
          : fallback;

    const requestId = extractRequestId(payload);
    if (requestId) {
      return `${detail} (Mã yêu cầu: ${requestId})`;
    }
    return detail || fallback;
  }

  if (error instanceof Error) {
    const detail = error.message?.trim() || fallback;
    return detail;
  }

  return fallback;
};

export async function runLongRequest<T>(
  requestFactory: () => Promise<T>,
  options?: {
    onSlowStateChange?: (isSlow: boolean) => void;
    slowDelayMs?: number;
  }
): Promise<T> {
  const slowDelayMs = Math.max(1000, options?.slowDelayMs ?? 4500);
  let timer: ReturnType<typeof setTimeout> | null = setTimeout(() => {
    options?.onSlowStateChange?.(true);
  }, slowDelayMs);

  try {
    return await requestFactory();
  } finally {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
    options?.onSlowStateChange?.(false);
  }
}

export const api = {
  analyzeSubject: async (formData: FormData) => {
    return apiClient.post(`${API_URL}/upload/analyze-subject`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },

  uploadFile: async (formData: FormData, onProgress?: (percent: number) => void) => {
    return apiClient.post(`${API_URL}/upload/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (progressEvent) => {
        if (onProgress && progressEvent.total) {
          const percent = Math.round((progressEvent.loaded * 100) / progressEvent.total);
          onProgress(percent);
        }
      },
    });
  },

  generateAssessment: async (subject: string) => {
    const response = await apiClient.post(`${API_URL}/assessment/generate`, { subject });
    return response.data;
  },

  submitAssessment: async (submissionData: {
    subject: string,
    answers: { question_id: number, selected_option: string }[],
    duration_seconds: number
  }) => {
    const response = await apiClient.post(`${API_URL}/assessment/submit`, submissionData);
    return response.data;
  },

  getLearningStats: async () => {
    const response = await apiClient.get(`${API_URL}/assessment/history/all`);
    return response.data;
  },

  getAdaptiveRoadmap: async (subject: string) => {
    const response = await apiClient.get(`${API_URL}/adaptive/recommend/${subject}`);
    return response.data;
  },

  chatWithTutor: async (chatData: {
    subject: string,
    message: string,
    roadmap_context: string
  }) => {
    const response = await apiClient.post(`${API_URL}/adaptive/chat`, chatData);
    return response.data;
  }
};
