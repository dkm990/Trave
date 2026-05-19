# Frontend UX notes

Short, actionable UX hints for `frontend/src/pages/*.tsx`. These are not bugs in the current MVP; they are inspired by Spliit / SplitGram / Nomad Expense observations during the reuse audit (see `docs/reuse-audit.md`). Apply incrementally, do not rework pages just to follow them.

## TripsPage
- Empty state already exists. Consider adding a tiny "Что это" hint near the form (Spliit landing has a one-line value-prop on the empty state).
- After "Создать", we navigate the user to the new trip dashboard? Currently we just reload the list. Add `useNavigate` to push to `/trips/{id}` for a faster onboarding (SplitGram pattern).

## TripDashboardPage
- Show top numbers: total group spending in `default_currency`, count of expenses, count of members. Spliit shows them as small chips above the action grid.
- Add a `Copy invite link` button if the trip is bound to a Telegram chat — `t.me/<bot>?startgroup=trip-<id>` (SplitGram-style group invite).

## ExpensesPage
- Form is fine for MVP. Consider:
  - **Category select** (column already exists on `Expense.category`). Suggested values: `food`, `transport`, `lodging`, `tickets`, `groceries`, `other`. Spliit uses a fixed list.
  - **Split mode** segmented control: `Поровну` / `По долям` / `По суммам`. Hidden until backend supports it (TODO in `expense_service.py`).
  - **Quick re-add**: tap on a past expense to pre-fill the form (Nomad Expense pattern).
- Pending status badge is shown but never set today. Either remove the tag or wire the `pending_confirmed` status from the bot confirmation flow (low priority).

## BalancesPage
- Show "Все рассчитались" with a subtle 🎉 (Splitwise Telegram Bot UX). Currently a plain hint.
- Show base currency once, do not repeat it on every row. Already true.
- For long debt lists (>5), group by creditor (Spliit "reimbursement to X" grouping).

## ConverterPage / DocumentsPage
- No notes for MVP.

## Mini App chrome
- We already inject Telegram theme variables. Make sure `MainButton` is used for primary actions inside long forms (ExpensesPage submit, TripsPage create) — currently we render an HTML button. Out of scope for this audit, follow up later.

## A11y
- All inputs have visible placeholders but no `<label>`s. Adding labels is a small a11y improvement we can do separately.
