// Frontend-side mirror of backend format_money / format_dual.
// Keeps presentation consistent with bot output.

const NBSP = "\u00a0";

export function formatMoney(value: string | number, currency?: string): string {
  const num = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(num)) return `${value}${currency ? ` ${currency}` : ""}`;
  const fixed = num.toFixed(2);
  const [int, dec] = fixed.split(".");
  const sign = int.startsWith("-") ? "-" : "";
  const digits = sign ? int.slice(1) : int;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  const out = `${sign}${grouped}.${dec}`;
  return currency ? `${out}${NBSP}${currency}` : out;
}

export function formatDual(
  amountOriginal: string | number,
  currencyOriginal: string,
  amountBase: string | number,
  baseCurrency: string,
): string {
  if ((currencyOriginal || "").toUpperCase() === (baseCurrency || "").toUpperCase()) {
    return formatMoney(amountOriginal, currencyOriginal);
  }
  return `${formatMoney(amountOriginal, currencyOriginal)} ≈ ${formatMoney(amountBase, baseCurrency)}`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const day = String(d.getDate()).padStart(2, "0");
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${day}.${month} ${hh}:${mm}`;
  } catch {
    return iso;
  }
}

export function formatNet(value: string | number, currency: string): string {
  const num = typeof value === "string" ? Number(value) : value;
  const sign = num > 0 ? "+" : "";
  return `${sign}${formatMoney(num, currency)}`;
}
