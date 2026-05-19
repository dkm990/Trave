export interface TripMember {
  id: number;
  user_id: number;
  display_name: string | null;
  role: string;
}

export interface Trip {
  id: number;
  title: string;
  default_currency: string;
  local_currency: string | null;
  telegram_chat_id: number | null;
  created_at: string;
  members: TripMember[];
}

export interface TripUpdateRequest {
  title?: string;
  local_currency?: string;
}

export interface ExpenseShare {
  user_id: number;
  share_amount_base: string;
}

export interface Expense {
  id: number;
  trip_id: number;
  payer_user_id: number;
  title: string;
  category: string | null;
  amount_original: string;
  currency_original: string;
  amount_base: string;
  base_currency: string;
  exchange_rate: string;
  status: string;
  created_at: string;
  updated_at: string | null;
  canceled_at: string | null;
  edited_count: number;
  note: string | null;
  source: string | null;
  shares: ExpenseShare[];
}

export interface ExpenseUpdateRequest {
  title?: string;
  amount?: string;
  currency?: string;
  category?: string;
  payer_user_id?: number;
  participant_user_ids?: number[];
  note?: string;
}

export interface Balance {
  user_id: number;
  paid: string;
  owes: string;
  net: string;
}

export interface DebtTransfer {
  from_user_id: number;
  to_user_id: number;
  amount: string;
}

export interface BalancesResponse {
  base_currency: string;
  balances: Balance[];
  transfers: DebtTransfer[];
}

export interface CurrencyRate {
  base: string;
  quote: string;
  rate: string;
  rate_date: string;
  provider: string;
  fetched_at: string;
  from_cache: boolean;
}

export interface CurrencyConvert {
  amount: string;
  base: string;
  quote: string;
  converted: string;
  rate: CurrencyRate;
}

export interface QuickCurrenciesResponse {
  currencies: string[];
}

export interface TravelDocument {
  id: number;
  trip_id: number;
  owner_user_id: number;
  visibility: string;
  doc_type: string;
  title: string;
  telegram_file_id: string;
  file_name: string | null;
  mime_type: string | null;
  file_size: number | null;
  note: string | null;
  created_at: string;
}

export interface DashboardMember {
  user_id: number;
  display_name: string;
  role: string;
}

export interface DashboardTotals {
  total?: string;
  total_display?: string;
  base_currency?: string;
  display_currency?: string;
  by_original_currency?: Record<string, string>;
  totals_by_original_currency?: Record<string, string>;
  by_category: Record<string, string>;
  count: number;
}

export interface DashboardBalance {
  user_id: number;
  name: string;
  paid: string;
  owes: string;
  net: string;
}

export interface DashboardTransfer {
  from_user_id: number;
  to_user_id: number;
  from_name: string;
  to_name: string;
  amount: string;
}

export interface DashboardResponse {
  trip: {
    id: number;
    title: string;
    default_currency: string;
    local_currency: string | null;
    members: DashboardMember[];
  };
  today: DashboardTotals;
  trip_total: DashboardTotals;
  balances: DashboardBalance[];
  transfers: DashboardTransfer[];
}

export interface AnalyticsCurrencyAmount {
  currency: string;
  amount: string;
}

export interface AnalyticsCategory {
  category: string;
  amount_display: string;
  original: AnalyticsCurrencyAmount[];
}

export interface AnalyticsPerson {
  user_id: number;
  name: string;
  amount_display?: string;
  share_display?: string;
}

export interface AnalyticsByDay {
  date: string;
  amount_display: string;
}

export interface AnalyticsResponse {
  trip: {
    id: number;
    title: string;
    default_currency: string;
    local_currency: string | null;
  };
  period: "trip" | "today";
  display_currency: string;
  local_currency: string | null;
  total_display: string;
  totals_by_original_currency: AnalyticsCurrencyAmount[];
  by_category: AnalyticsCategory[];
  by_payer: AnalyticsPerson[];
  by_participant: AnalyticsPerson[];
  by_day: AnalyticsByDay[];
  debts: DashboardTransfer[];
  count: number;
}
