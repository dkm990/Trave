import { getCurrentUser, getInitData } from "../telegram/webapp";

const BASE_URL: string = import.meta.env.VITE_API_BASE_URL || "";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };

  const initData = getInitData();
  if (initData) headers["X-Telegram-Init-Data"] = initData;

  // dev fallback: если запущено вне Telegram, прокидываем dev user id
  const user = getCurrentUser();
  if (!initData) {
    const devId = localStorage.getItem("dev_user_id");
    if (devId) headers["X-Telegram-User-Id"] = devId;
    else if (user?.id) headers["X-Telegram-User-Id"] = String(user.id);
    else headers["X-Telegram-User-Id"] = "1";
  }

  const url = `${BASE_URL}${path}`;
  const resp = await fetch(url, { ...options, headers });
  if (!resp.ok) {
    const text = await resp.text().catch(() => "");
    throw new ApiError(`${resp.status} ${text}`, resp.status);
  }
  if (resp.status === 204) return null as unknown as T;
  return (await resp.json()) as T;
}
