# Reuse Audit — Yo Travel Mini App

Date: 2026-05-16
Scope: targeted reuse audit of four open-source references vs current codebase in `E:\Projects\Yo`.

Goal: do **not** rewrite our project, do **not** clone any external project. Only reuse small, license-compatible ideas, algorithms, test cases, UX patterns.

Our stack is fixed:
- Backend: FastAPI + aiogram 3 + SQLAlchemy 2 (async)
- Frontend: React + Vite + TypeScript
- DB: SQLite (default) / PostgreSQL (optional)
- AI: rule-based (default) / Ollama (optional)
- No mandatory paid API

Hard rules applied to every repo:
- No LICENSE or unclear LICENSE → behavior/idea reuse only, no code copy.
- MIT/Apache/BSD → small functions allowed with attribution in `docs/third-party-notices.md`.
- Never copy big UI or backend chunks.
- Never introduce paid APIs (OpenAI, Splitwise, supermemory, …) as mandatory.

---

## 1. SplitGram

| Field | Value |
|---|---|
| Repo URL | https://github.com/luca-martinelli-09/splitgram (verified). Also runs as @SplitGram_bot on Telegram. |
| License detected | **No LICENSE file in the repo.** GitHub `license` field is `null` (verified via REST API on 2026-05-16) and the root listing has no `LICENSE`/`LICENSE.md`. README mentions donations but no license. Under our hard rule, this means **code copy is forbidden, only behavior/idea reuse**. |
| Stack | TypeScript + SvelteKit webapp + Telegraf-style Telegram bot, MongoDB (collections `users`, `groups`, `splits`, `payments`), Docker Compose deploy. |
| What is useful | (a) Group onboarding sequence per the README: *"Add the bot to your group → wait for all group members to join → use /app to launch the webapp and manage expenses and splits."* (b) Single-command launcher `/app` — same name we already use. (c) Generic currency symbol "¤" as a placeholder when the trip currency is not chosen. (d) Telegram group privacy limitation: the bot cannot enumerate group members, so participants must self-join — same constraint we have today via `/join`. |
| What is incompatible | Stack mismatch (SvelteKit + MongoDB vs React/Vite + SQLAlchemy). No license to allow copy anyway. Generic currency symbol is a UI choice — we already require an explicit `default_currency` per trip, which is stricter and clearer. |
| Copy code? | **No.** No LICENSE → reference only. |
| If yes → files | n/a |
| If no → idea to adapt | (a) Make the group `/newtrip` welcome message explicitly state the join flow ("each participant must say /join — the bot cannot read group membership") so users do not assume the bot auto-detects them. (b) Keep `/app` as the canonical launcher command, which we already do. |
| Risks | License missing → strict reference-only. Telegram group privacy is a real platform constraint, not a project bug — UX must surface it to avoid confusion. |

**Status in our repo:**
- Trip↔chat binding: implemented (`Trip.telegram_chat_id`, `TripService.get_trip_for_chat`, `bind_to_chat`).
- Group `/newtrip` welcome: extended with explicit 4-step onboarding and `@bot 100 THB Coffee` examples in the previous quick-win pass. Optional follow-up: add a one-line note "бот не видит список участников — каждый пишет /join". Logged as a small UX TODO.

---

## 2. Spliit (`spliit-app/spliit`)

| Field | Value |
|---|---|
| Repo URL | https://github.com/spliit-app/spliit |
| License detected | **MIT** © 2023 Sebastien Castiel. Verified by reading `LICENSE` file. |
| Stack | Next.js + TailwindCSS + shadcn/ui + Prisma + PostgreSQL. |
| What is useful | (a) Balance algorithm in `src/lib/balances.ts` — `getBalances` + `getSuggestedReimbursements` with stable comparator, "last participant gets the rounding remainder", explicit handling of reimbursement expenses (`isReimbursement`). (b) Split modes: `EVENLY`, `BY_SHARES`, `BY_PERCENTAGE`, `BY_AMOUNT`. (c) Reimbursement expense as a first-class expense type — clean settlement model. (d) Categories on expenses. (e) Image attachments to expenses (idea only — we explicitly do **not** want server-side image storage). (f) "Tell the application who you are when opening a group" — active user concept. |
| What is incompatible | Different stack (Node/Prisma) — we do not port code as-is. Built-in OpenAI receipt scan + GPT category extract — both opt-in in Spliit, but **forbidden as mandatory** for us. AWS S3 for documents — incompatible with our zero-storage policy (we keep only `telegram_file_id`). |
| Copy code? | **No (algorithm reused as idea / pattern, re-implemented in Python).** Our existing `simplify_debts` is functionally equivalent (greedy + epsilon). |
| If yes → files | n/a — we already have an equivalent `app/services/balance_service.py`. The Spliit comparator is documented in `docs/third-party-notices.md` as inspiration. |
| If no → idea to adapt | (a) Add `is_reimbursement` flag to `Expense` model — TODO comment, not implemented in this audit. (b) Split modes enum: TODO marker added in expense model + ExpenseInput. (c) Categories already exist on `Expense.category`, but no UI. TODO. (d) Add balance test cases inspired by Spliit (3-creditor / 1-debtor, settled, exact rounding). |
| Risks | License-safe (MIT) but copying TS code into Python is unnecessary; native re-implementation avoids any attribution doubt. The receipt-scan and category-extract features rely on OpenAI — must stay forbidden in our project. |

**Status in our repo:**
- Balances + simplify: implemented and tested. Quick win: add 1–2 more edge tests.
- Reimbursement model: not implemented. **TODO** added.
- Split modes: only `EVENLY`. **TODO** added in `expense_service.py`.
- Categories: column exists, no UI. **TODO** for frontend.
- Image attachments: explicitly out of scope.

---

## 3. Nomad Expense

| Field | Value |
|---|---|
| Repo URL | https://github.com/kubk/nomad-expense (verified). Live bot: https://t.me/expense_tracker_turkey_bot. |
| License detected | **No LICENSE file in the repo.** GitHub `license` field is `null` (verified via REST API on 2026-05-16) and the root listing has no `LICENSE`. Under our hard rule, **code copy is forbidden, only behavior/idea reuse**. |
| Stack (per README) | React 19 + Tailwind v4 + shadcn/ui + TanStack Query (frontend); tRPC on Cloudflare Workers (backend); PostgreSQL + Drizzle ORM; Telegram OAuth + Mini App; **GPT-4 Vision** for bank-statement OCR; **grammy.js** bot; Cloudflare Workers + GitHub Actions CI/CD. |
| What is useful | (a) **Telegram Mini App expense-tracker pattern** — webapp + bot + auto-currency conversion to a family base currency, very close to our trip model. (b) **Multi-currency account model** — accounts in arbitrary currencies (incl. crypto), all amounts auto-convert to the family base via live FX. (c) **Bot input pattern** — short message `100 THB Coffee` → bot parses amount + currency + free-text title, picks the matching account, saves. This is the exact short-form input we already added to our rule-based parser. (d) **Family-sharing model** — invite members, shared accounts, Telegram notifications on new expense. (e) Monthly analytics: expense/income breakdown, last-30-days summary, trending data, filterable history. |
| What is incompatible (do NOT adopt) | (a) **GPT-4 Vision dependency** for receipt / bank-statement OCR — paid OpenAI API. Forbidden as mandatory in our project. (b) **Cloudflare Workers + tRPC + Drizzle + Postgres** stack — does not fit our FastAPI + SQLAlchemy + SQLite-default architecture. (c) **Bank statement import** as a feature — out of scope (we do not store financial PDFs and have no statement parser). (d) **Crypto accounts** — out of scope for travel-MVP. (e) **TanStack Query / shadcn/ui** — adding a data-fetching layer and a component library to our small Vite app is overkill at MVP scale. |
| Copy code? | **No.** No LICENSE → reference only. |
| If yes → files | n/a |
| If no → idea to adapt | (a) Short-form bot input `100 THB Coffee` — already implemented in `app/ai/rule_based.py` after the previous quick-win pass; tests in `tests/test_parser.py`. (b) "Auto-convert to base currency" — already implemented (`Trip.default_currency` + `CurrencyService.convert`). (c) Account/wallet model — keep as a longer-term idea, not for MVP. (d) "Trends / analytics" — out of scope. |
| Risks | (1) License missing → strict reference-only. (2) Any "easy" port of GPT-4 Vision OCR would silently introduce a paid API dependency — must remain forbidden. (3) Bank statement OCR is a much bigger surface than expense tracking — scope creep risk. |

**Status in our repo:**
- Short-form parser (`100 THB Coffee` / `50 USD lunch` / `200р такси`): implemented and tested.
- Per-trip default currency: implemented.
- Multi-account-per-family model: out of scope. Kept as discussion only, not as a code TODO.
- OCR / receipt scan: explicitly NOT planned.

---

## 4. Splitwise Telegram Connector

We surveyed two candidate references with that role:
- `juanedi/splitbot` (Haskell, BSD-3-Clause-style, https://github.com/juanedi/splitbot)
- `krnbatra/SplitwiseTelegramBot` (Python, MIT, https://github.com/krnbatra/SplitwiseTelegramBot)

| Field | Value |
|---|---|
| Repo URL | juanedi/splitbot, krnbatra/SplitwiseTelegramBot |
| License detected | juanedi/splitbot — modified BSD-3 ("Author name here"). krnbatra/SplitwiseTelegramBot — MIT. Both verified by fetching `LICENSE`/`LICENSE.md`. |
| Stack | juanedi: Haskell + cabal, BasicEngine conversation state machine, Splitwise REST. krnbatra: python-telegram-bot v13 + Splitwise SDK + Redis state. |
| What is useful | (a) Conversation state machine for adding an expense: `take_input → typing_reply → confirm → save`. (b) Confirmation step with explicit "Are you sure?" buttons before write — exactly our `exp:yes/edit/no`. (c) Validation errors as typed exceptions (`InvalidAmountError`, `InvalidDescriptionError`) with friendly retry. (d) `peer notification` after save — notify the other party. (e) "Hold on a sec…" interim message before the API call. (f) Error handler with traceback to dev chat. |
| What is incompatible | (a) Splitwise API as backend — we MUST NOT introduce Splitwise as a dependency. (b) Long-living Redis state — we use in-memory `_PENDING` keyed by uuid, fine for MVP. (c) Per-user OAuth flow with Splitwise — irrelevant. (d) python-telegram-bot v13 — we are on aiogram 3, do not copy any handler code. |
| Copy code? | **No.** Even though MIT allows it, our framework is different (aiogram vs ptb). Re-implementation is cleaner and avoids licensing footnotes. |
| If yes → files | n/a |
| If no → idea to adapt | (a) Add explicit "Invalid amount, try again" path in `/add` — already partially present (we say "Не понял расход" and show example). (b) "Hold on…" pre-confirmation message — TODO; not added (UX flicker, not worth it for MVP). (c) Test cases for parser failure modes (empty title, missing currency, two numbers). Added. (d) Short balance summary right after expense is recorded — UX note added in audit, not implemented. |
| Risks | Splitwise as dependency is blocked. Telegram bot framework mismatch — copying handler code would be a large and pointless port. |

**Status in our repo:**
- Confirmation flow: present (`exp:yes/edit/no`). Good.
- Parser error paths: improved with new tests. Quick win.
- Peer notification after save: out of scope (we are group-first, the message itself is visible to all).

---

## Cross-cutting suggestions (not implemented in this audit)

These are TODOs we add as comments in code, not full features:

1. **Reimbursement expense type** (Spliit) — clean settlement: add a flag on `Expense` so `is_reimbursement` does not contribute to group spending but reduces balance. Today we have a separate `Settlement` model that is unused by the balance algorithm. Recommendation: keep `Settlement` for an explicit "mark as paid" log, but also expose a "reimbursement expense" via `Expense.is_reimbursement` later. — **TODO** added in `app/models/expense.py`.

2. **Uneven split (`split_mode`)** — Spliit's BY_SHARES, BY_PERCENTAGE, BY_AMOUNT. Today we only do EVENLY. Recommendation: add `split_mode` + per-share `weight`/`amount` columns. — **TODO** added in `app/services/expense_service.py` and `app/models/expense.py`.

3. **Categories UI** — column exists, but `ExpensesPage.tsx` does not let users pick one. — **TODO** in frontend (`docs/frontend-ux-notes.md`).

4. **Active-user concept** for Mini App (Spliit "tell who you are") — already covered by Telegram `initData` (`X-Telegram-User-Id`).

5. **Receipt OCR / category-extract via OpenAI** — explicitly NOT planned. We keep AI provider pluggable (rule-based default, Ollama optional) and never make external paid APIs mandatory.

---

## Summary

| Repo | URL | License | Code copied | Idea reused |
|---|---|---|---|---|
| SplitGram | luca-martinelli-09/splitgram | **no LICENSE file** (GitHub `license`=null) | no | group onboarding flow, `/app` launcher command, "participants must self-join" UX cue |
| Spliit | spliit-app/spliit | MIT | no (re-implemented natively earlier) | balance + reimbursements algorithm shape, split modes (TODO), categories (TODO) |
| Nomad Expense | kubk/nomad-expense | **no LICENSE file** (GitHub `license`=null) | no | short-form parser input "100 THB Coffee", per-trip currency, family-sharing model (idea only) |
| Splitwise Telegram Connector (juanedi, krnbatra) | juanedi/splitbot, krnbatra/SplitwiseTelegramBot | BSD-3 / MIT | no | confirmation flow, parser validation errors, conversation state |

No third-party code lines were copied into our repo.
