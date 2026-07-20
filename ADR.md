# Architecture Decision Record — TTB label verification prototype

README.md is the "how" (setup, run, summary); this file is the "why."

## Decisions

0. Requirements — explicit vs. implicit
1. No database (stateless)
2. Python / FastAPI
3. React + Vite
4. One isolated external dependency
5. Single extraction function (no interface)
6. Fuzzy vs. strict comparison
7. Global bounded concurrency
8. Shared HTTP client (lifespan)
9. Keep-alive ping (cold starts)
10. Upload validation (magic bytes)
11. Deferred / out of scope
12. Batch input: CSV matched by filename
13. Streaming batch results (live progress)
14. Flat file structure, minimal abstraction
15. Conditional, class-specific label fields

---

## 0. Requirements — explicit vs. implicit

> The requirements the prototype targets, and whether each was stated by a
> stakeholder (explicit) or inferred (implicit).

- Verify label image against application data — Explicit
- Government warning, exact/strict match — Explicit (Jenny)
- Fuzzy match for brand / class / net-contents / name-address — Implicit (Dave's "Stone's Throw" anecdote)
- Batch upload support — Explicit (Sarah, Janet)
- Deployed, working URL — Explicit
- Source repo + README/ADR — Explicit
- Test data: a clean pass and a clear failure — Implicit (how a reviewer validates the logic)
- ~5-second per-label response time — Explicit (Sarah)
- Simple, low-friction UI — Explicit (Sarah)
- Graceful handling of failed extraction — Implicit (reject, ask for a better image)
- Document the network/firewall risk on the LLM dependency — Implicit (Marcus's vendor pilot)
- English-only label enforcement — Implicit (27 CFR, not the interviews)
- Tunable, documented match thresholds — Implicit (design-quality signal)

**Source doesn't set priority.** The highest-value requirement here — fuzzy
matching — was never asked for directly; it's inferred from Dave's
false-rejection complaint. English-only enforcement, which *does* trace to
federal regulation, matters far less to whether the tool works. Whether a
requirement was stated or inferred says nothing about how much it matters.

---

## 1. No database (stateless)

> Nothing is saved — each request is checked, the answer returned, then
> forgotten.

**Why:** Marcus (IT admin) asked us not to store anything sensitive. There
are no user accounts or sessions to track, and a database would bring
privacy and data-retention obligations with no upside at this scale.

**Alternative:** a small SQLite database to track batch progress. Not
needed — a batch streams its results back over one open request (§13), so
there's no in-progress state to remember between requests.

**Trade-off:** no record of past checks. A production system would want one
for compliance.

---

## 2. Python / FastAPI

> FastAPI (Python) for the backend.

**Why:** the work is mostly *waiting* on the vision API, not heavy
computation — so a faster compiled language wouldn't help; the network wait
dominates either way. Python won on build speed and its mature AI/vision
libraries, the fastest route to a working prototype on a deadline.

**Alternatives:** C#/.NET — a better long-term fit if this ever joins the
real COLA system (which is .NET, per Marcus, and years away), but slower to
build here. Java/Spring — comparable runtime, often used in government repos.

**Trade-off:** if this is ever folded into COLA, it'd likely be rewritten in
.NET then. Fine — that's a separate future decision.

---

## 3. React + Vite

> Plain React with Vite, function components and hooks — no Next.js or
> Angular.

**Why:** it's one screen (upload, submit, view results). Next.js and Angular
add routing, server rendering, and structure this app has no use for. Vite +
React is the smallest thing that does the job.

---

## 4. One isolated external dependency

> Only one thing reaches outside the system — the vision API call in
> `extraction.py`. Everything else runs locally.

**Why:** Marcus described a past vendor pilot where half the features broke
when Treasury's firewall blocked outbound AI calls. Keeping that one
unavoidable external call in a single, swappable function means if the same
thing happens again, only that function has to change.

---

## 5. Single extraction function (no interface)

> The vision call is one plain function. An earlier version wrapped it in a
> class hierarchy with a factory; that was removed.

**Why reverted:** there's only one provider. A pluggable interface pays off
when you have two or more implementations to switch between; with one, the
extra class, factory, and global state were just overhead. The goal —
keeping the external call in one place — was already met by a single
function.

**Rule applied:** don't build an abstraction for a second case that doesn't
exist yet. If a real second provider shows up (a self-hosted model, an
internal proxy), that's the time to generalize — from two concrete examples,
which is easy. Guessing the shape up front usually gets it wrong.

**Trade-off:** a future second provider means editing this function rather
than adding a subclass. Fine — none is planned.

---

## 6. Fuzzy vs. strict comparison

> Forgiving similarity matching for brand, class/type, net contents, bottler
> name/address, and country of origin when supplied; exact matching for the
> government warning; a numeric tolerance for ABV (wider for high-ABV wine).

**Why:** Dave (senior agent) pointed to rejecting "STONE'S THROW" vs "Stone's
Throw" — plainly the same brand, but an exact text match flags it, and that
kind of false rejection wastes agents' time. Jenny (junior agent) had the
reverse case: a warning printed in title case has to be rejected, because
its exact wording, casing, and bold formatting are fixed by law (27 CFR part
16, checked against ttb.gov).

**Alternative:** a single similarity score for every field. Rejected — it
would either wave through warning violations that happened to score high, or
bring back the false rejections Dave complained about.

---

## 7. Global bounded concurrency

> One shared limiter (an `asyncio.Semaphore`) caps how many vision-API calls
> run at once — across the whole app, not per batch.

**Why:** Sarah described peak batches of 200-300 labels. Running them one at
a time takes minutes; running them all at once risks tripping the vision
API's rate limit. A limiter fixes that for one batch — but a *per-batch*
limiter would let several big batches arriving together still blow past the
limit. One shared limiter for the whole process closes that gap.

---

## 8. Shared HTTP client (lifespan)

> Open one HTTP client at startup and reuse it for every vision-API call,
> instead of making a new one each time.

**Why:** opening a fresh encrypted (HTTPS) connection is slow — it takes
several network round-trips to set up before the request even goes out.
Reusing one client keeps those connections open and warm, so only the first
call pays that cost. It matters under Sarah's ~5-second budget and adds up
across a big batch. (FastAPI's `lifespan` hook opens the client at startup
and closes it cleanly on shutdown.) This fixes per-call connection cost, not
cold starts — see §9.

---

## 9. Keep-alive ping (cold starts)

> Ping `/health` on a schedule so a free host doesn't put the whole app to
> sleep.

**Why:** free hosting tiers (e.g. Render) suspend the entire process after
~15 minutes idle, and the first request after that waits 30-60s while it
wakes back up. The warm connections from §8 can't help — the process holding
them isn't running. A lightweight scheduled ping (e.g. cron-job.org hitting
`/health` every ~10 minutes) keeps the process awake. `/health` deliberately
doesn't call the vision API, so the ping costs no API budget.

**Alternative:** a paid always-on tier removes the problem outright; the ping
is the free-tier workaround. Neither lives in the code — it's a
deployment/ops choice, documented in README.

---

## 10. Upload validation (magic bytes)

> Accept only JPEG/PNG, reject files over 1.5MB, and check the file's real
> signature bytes — not the type the client claims.

**Why:** the limits match TTB's own COLAs Online upload rules, so they're
defensible rather than arbitrary.

**Magic-byte check:** a file's claimed type is trivial to fake by renaming,
so `_sniff_image_type` reads the leading bytes that only a real JPEG
(`FF D8 FF`) or PNG (`89 50 4E 47 0D 0A 1A 0A`) will have. That verified type
is what's sent to the vision API too, so a spoofed header can't slip through.

---

## 11. Deferred / out of scope

> Intentionally left out — deliberate scoping, not oversights.

- Blurry, glare, or poorly-lit photos (Jenny flagged this herself).
- Type-specific conditional label fields, which vary by product class — see §15.
- COLA system integration (the real system is .NET and years away, per Marcus).
- Authentication / access control, PII/retention (no data is stored — see §1).
- Per-caller rate limiting (total concurrency is capped; per-user is not).
- Full prompt-injection hardening — bounded, because the model's output only
  feeds read-only comparisons and never triggers actions, but not
  eliminated; an industry-wide open problem, not specific to this app.

---

## 12. Batch input: CSV matched by filename

> Batch application data is a CSV, matched to images by a `filename` column —
> so files and rows need not be in the same order, and a missing, extra, or
> failed item becomes a per-item error instead of failing the whole batch.

**Why CSV:** agents live in spreadsheets, so "export to CSV, upload" fits
their workflow and needs no JSON knowledge. The earlier raw-JSON textarea was
developer-facing and all-or-nothing — one syntax slip failed everything.

**Why match by filename, not position:** the old endpoint zipped images to a
JSON array by order, so a reordered upload silently mis-paired data with the
wrong image. Keying on the `filename` column (case-insensitively, so
`Old_Tom.PNG` matches `old_tom.png`) takes order out of the equation.

**Why it can't fail the whole batch:** `/verify/batch` always returns 200.
An image with no CSV row, a row with no image, a row with bad values, and a
failed extraction each become a per-item `error` row; only a structurally
unusable CSV (unreadable, or missing a required column) is a 400. So one bad
item never sinks the rest. Images are still capped at 300 (§7 / `config.py`).

---

## 13. Streaming batch results (live progress)

> `/verify/batch` streams newline-delimited JSON — a `meta` line, one
> `result` line per label as it finishes, then a `summary` — so the UI can
> show a real "142 / 300" progress bar instead of a spinner.

**Why:** a 300-label batch takes 1-2.5 minutes (bounded by the §7 concurrency
cap). Returning everything in one response means the browser sees nothing
until the very end — a long, blank wait. Emitting each result as it completes
lets the client count done/total for genuine progress.

**Why stream, not poll a job:** a job + status endpoint would need
server-side state to track progress, which breaks the stateless design (§1).
Streaming keeps it to one stateless request — results are pushed as they
finish, nothing is stored.

**Trade-off:** results arrive in completion order, not file order (the client
sorts by filename before rendering), and the response is no longer one JSON
object, so a consumer must read it line by line.

**Implementation constraint:** every upload must be read into memory *before*
the streaming response begins. FastAPI closes the multipart form — and with it
each `UploadFile`'s spooled temp file — as soon as the handler returns, which
is before the response body is iterated. Reading lazily inside the generator
raises "I/O operation on closed file" and kills the stream after the `meta`
line, which surfaces as a progress bar frozen at 0.

---

## 14. Flat file structure, minimal abstraction

**Decision:** five backend modules, three frontend files, no `services/`,
`routes/`, `types/`, or class-hierarchy subfolders. One file per concern,
not per possible future concern.

**Why:** this codebase took the more "enterprise" path once, briefly --
a `LabelExtractor` interface with a factory function (§5) -- before there
was a second implementation to justify it. Reverted, because the
abstraction wasn't paying for itself: one provider, one plain function,
done. The same logic governs the whole layout, not just that one case.
A folder per technical layer earns its cost once there are several
features that need keeping apart; with one feature (verify a label), it
just adds navigation overhead without adding clarity.

**Rule applied:** add structure when a second real case shows up to
generalize from, not in anticipation of one. Guessing the right
abstraction shape in advance usually guesses wrong; refactoring from two
concrete examples, once they exist, is easy and well-motivated.

**Trade-off:** if this app ever grows a second, genuinely distinct
feature, the flat layout would need to become more structured. Not a
cost worth paying today for a one-feature app.

---

## 15. Conditional, class-specific label fields

> The app checks the six fields mandatory for every product class. The
> conditional fields that vary by class — sulfite declarations, age
> statements, appellation/varietal rules, coloring disclosures, placement —
> are deliberately not checked.

**Why:** brand name, class/type, ABV, net contents, bottler name/address, and
the government warning are required for distilled spirits, wine, and malt
beverages alike. One comparison path therefore covers every product, which is
what keeps the prototype small enough to be verifiably correct.

A conditional field needs two things the core six don't: its own comparison
rule, *and* a reliable signal for whether it applies to this product at all.
The application data carries no such signal — nothing states whether a wine
was sulfited, whether a spirit is young enough to require an age statement, or
whether a colorant was used. The app would have to guess at applicability
before it could begin comparing, and a wrong guess produces exactly the
failure Dave complained about: a confident false rejection that wastes an
agent's time. A check that can't tell whether it should run is worse than no
check.

**Deliberately excluded:**

- Sulfite declaration, appellation and varietal rules (wine)
- Age statements (distilled spirits)
- FD&C coloring disclosures
- The "same field of vision" placement rule

**Where the line is drawn:** two class-dependent behaviours *are* implemented,
because each modifies a comparison the app already makes rather than adding a
field with new applicability logic:

- The wider federal ABV tolerance for wine at or above 14% (27 CFR) — same
  field, same comparison, different threshold.
- Country of origin — compared when the applicant fills it in, skipped when
  blank, so applicability comes from submitted data rather than a guess (§6).

**Trade-off:** a label that passes every check here can still be
non-compliant on a conditional field. This is a pre-screen that catches the
universal errors before an agent looks, not a replacement for full review.
Extending it means first deciding where applicability data comes from — an
expanded application form, or inference from the label itself — which is a
requirements question, not a coding one.