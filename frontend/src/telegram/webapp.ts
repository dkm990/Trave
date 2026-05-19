// Минимальная обертка над window.Telegram.WebApp без сторонних SDK.

export interface TelegramUser {
  id: number;
  username?: string;
  first_name?: string;
  last_name?: string;
}

interface TelegramWebApp {
  initData: string;
  initDataUnsafe?: { user?: TelegramUser };
  themeParams?: Record<string, string>;
  expand: () => void;
  ready: () => void;
  MainButton?: {
    text: string;
    show: () => void;
    hide: () => void;
    setText: (s: string) => void;
    onClick: (cb: () => void) => void;
    offClick: (cb: () => void) => void;
  };
  HapticFeedback?: {
    impactOccurred: (style: "light" | "medium" | "heavy") => void;
    notificationOccurred: (type: "success" | "warning" | "error") => void;
  };
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}

let cached: TelegramWebApp | null = null;

export function tg(): TelegramWebApp | null {
  if (cached) return cached;
  cached = window.Telegram?.WebApp ?? null;
  return cached;
}

export function initTelegram(): void {
  const wa = tg();
  if (!wa) return;
  try {
    wa.ready();
    wa.expand();
  } catch {
    /* noop */
  }
}

export function getInitData(): string {
  return tg()?.initData ?? "";
}

export function getCurrentUser(): TelegramUser | null {
  return tg()?.initDataUnsafe?.user ?? null;
}

export function haptic(type: "success" | "warning" | "error" = "success") {
  try {
    tg()?.HapticFeedback?.notificationOccurred(type);
  } catch {
    /* noop */
  }
}
