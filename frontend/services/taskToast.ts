import toast from "react-hot-toast";

import { normalizeApiError } from "./api";

export function startTaskToast(message: string) {
  return toast.loading(message);
}

export function succeedTaskToast(toastId: string | undefined, message: string) {
  toast.success(message, { id: toastId });
}

export function failTaskToast(toastId: string | undefined, error: unknown, fallback: string) {
  toast.error(normalizeApiError(error, fallback), { id: toastId });
}
