export type ConfirmAlertOptions = {
  title?: string;
  message: string;
  confirmText?: string;
  cancelText?: string;
  tone?: "default" | "danger";
};

type ConfirmHandler = (options: ConfirmAlertOptions) => Promise<boolean>;

let confirmHandler: ConfirmHandler | null = null;

export function registerConfirmAlertHandler(handler: ConfirmHandler) {
  confirmHandler = handler;
  return () => {
    if (confirmHandler === handler) {
      confirmHandler = null;
    }
  };
}

export async function confirmAlert(input: ConfirmAlertOptions | string): Promise<boolean> {
  const options: ConfirmAlertOptions =
    typeof input === "string"
      ? {
          message: input,
        }
      : input;

  if (confirmHandler) {
    return confirmHandler({
      confirmText: "Xác nhận",
      cancelText: "Hủy",
      tone: "default",
      ...options,
    });
  }

  return false;
}
