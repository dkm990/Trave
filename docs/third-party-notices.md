# Third-party notices

This file lists every external open-source project that was studied as a reference for `Yo Travel Mini App` and explicitly states whether code was copied. See `docs/reuse-audit.md` for the full audit.

Policy:
- Code is copied **only** from MIT/Apache/BSD-licensed sources, with attribution here.
- If a repository has no LICENSE or unclear LICENSE, only behavior/idea is reused; no code, no string copy.

## Spliit — `spliit-app/spliit`

- URL: https://github.com/spliit-app/spliit
- License: MIT (Copyright © 2023 Sebastien Castiel). LICENSE verified.
- Reference only, no code copied. Reused as inspiration:
  - balance + reimbursement algorithm shape (`src/lib/balances.ts`)
  - split modes (`EVENLY`, `BY_SHARES`, `BY_PERCENTAGE`, `BY_AMOUNT`) — added as TODO
  - categories on expenses
- Our `app/services/balance_service.py` was implemented natively before this audit; the public-API shape (paid / paid_for / total + suggested reimbursements) is similar to Spliit because the problem is well-known. We did not import any TS source.

## SplitwiseTelegramBot — `krnbatra/SplitwiseTelegramBot`

- URL: https://github.com/krnbatra/SplitwiseTelegramBot
- License: MIT (Copyright © Karan Deep Batra). LICENSE.md verified.
- Reference only, no code copied. Reused as inspiration:
  - conversation state machine for `/create_expense` with explicit confirmation (`bot/create_expense.py`)
  - typed validation errors (`InvalidAmountError`, `InvalidDescriptionError`)
- Our handlers use aiogram 3 (different framework), so direct code reuse is impractical. No string or function was copied.

## splitbot — `juanedi/splitbot`

- URL: https://github.com/juanedi/splitbot
- License: modified BSD-3-Clause (LICENSE present, copyright placeholder "Author name here"). LICENSE verified.
- Reference only, no code copied. Reused as inspiration:
  - `Conversation` state machine pattern (Haskell `src/Conversation.hs`) — `Continue / Terminate / Done`
  - "Hold on a sec…" interim UX, peer-notification idea
- Stack mismatch (Haskell vs Python) and Splitwise dependency — code copy not applicable.

## SplitGram — `luca-martinelli-09/splitgram`

- URL: https://github.com/luca-martinelli-09/splitgram. Hosted bot: @SplitGram_bot.
- License: **no LICENSE file present in the repository.** GitHub REST API returns `license: null` (verified 2026-05-16). Under our policy, code copy is forbidden when no permissive license is declared.
- Reference only, no code copied. Reused as inspiration:
  - group onboarding flow from the README ("add the bot to your group → wait for members to join → /app to launch the webapp")
  - `/app` command name as the canonical Mini App launcher
  - explicit "participants must self-join" UX cue (Telegram group privacy limitation)

## Nomad Expense — `kubk/nomad-expense`

- URL: https://github.com/kubk/nomad-expense. Live bot: https://t.me/expense_tracker_turkey_bot.
- License: **no LICENSE file present in the repository.** GitHub REST API returns `license: null` (verified 2026-05-16). Under our policy, code copy is forbidden when no permissive license is declared.
- Reference only, no code copied. Reused as inspiration:
  - Telegram Mini App expense-tracker pattern (webapp + bot + base-currency auto-conversion)
  - short-form bot input pattern `100 THB Coffee` (we already implemented this in our rule-based parser)
  - multi-currency / multi-account model — kept as a longer-term idea, not implemented
- Explicitly NOT adopted from this repo:
  - GPT-4 Vision OCR for bank statements / receipts (paid OpenAI API, forbidden as mandatory)
  - Cloudflare Workers + tRPC + Drizzle + PostgreSQL stack (architecture mismatch)

---

## Direct dependencies

Our runtime dependencies (FastAPI, aiogram, SQLAlchemy, Alembic, httpx, pydantic, React, Vite, etc.) are listed in `backend/requirements.txt` and `frontend/package.json` and ship under their own licenses. They are not part of this audit.
