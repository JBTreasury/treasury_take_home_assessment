# Architecture Decision Record — TTB Label Verification Prototype

## Decisions

0. Requirements — explicit and implicit
1. No database (stateless)
2. Python/FastAPI
3. React/Vite
4. Flat file structure, minimal abstraction
5. Batch input: CSV matched by filename
6. Batch results progress bar UI
7. One isolated external dependency
8. Single extraction function (no interface)
9. Fuzzy vs. strict comparison
10. Global bounded concurrency
11. Shared HTTP client (lifespan)
12. Keep-alive ping (cold starts)
13. Upload validation (magic bytes)
14. Deferred / out of scope

---

## 0. Requirements — explicit vs. implicit

- Deployed on a live URL — Explicit
- Source repo available with README and ADR — Explicit
- Verify label image against application data — Explicit
- Government warning, exact match — Explicit (Jenny)
- Fuzzy match allowance for other categories
- Batch upload capability up to 300 — Explicit (Sarah, Janet)
- Test data to evaluate pass, fuzzy match, and failure — Implicit
- 5 second or less per-label response time — Explicit (Sarah)
- Simple and intuitive UI — Explicit (Sarah)
- Graceful handling of failed extraction — Implicit
- Tunable, documented match thresholds — Implicit 

---

## 1. No database (stateless)

> Nothing is saved — each request is checked and the answer is returned

**Why:** Marcus (IT admin) asked us not to store anything sensitive. There
are no user accounts or sessions to track, and a database would bring
privacy and data-retention obligations with no upside at this scale.

**Alternative:** a small SQLite database to track batch progress. Not
needed at this time since the batch streams results back over one request so
there's no in-progress state to remember between requests.

**Trade-off:** no record of past checks. A production system would want one
for compliance.

---

## 2. Python / FastAPI

> FastAPI (Python) for the backend.

**Why:** the work is mostly *waiting* on the vision API, not heavy
computation — so a faster compiled language wouldn't improve performance. Python is faster to stand up and is compatible with AI/vision libraries, the fastest route to a working prototype on a deadline.

**Alternatives:** C#/.NET and Java were also considerations since they are widely used high level languages. Java/Spring is widely used in government operations and the real COLA system is C#/.NET, but slower to build so Python made the most sense to quickly scale a prototype.

**Trade-off:** probably not the best choice for production in COLA, which is likely years away.

---

## 3. React + Vite

> Plain React with Vite, function components and hooks.

**Why:** it's one screen (upload, submit, view results). Next.js and Angular
add routing, server rendering, and structure this app has no use for. Vite +
React is the smallest thing that does the job and faster to write.

---

## 4. Flat file structure, minimal abstraction

**Decision:** five backend modules, three frontend files, no `services/`,
`routes/`, `types/`, or class-hierarchy subfolders. One file per concern.

**Why:** this code intentionally takes a minimalist approach in order to
keep code simple and brief as an MVP for a prototype.
A folder per technical layer earns its cost once there are several
features.

**Trade-off:** if this app ever grows a second, genuinely distinct
feature, the flat layout would need to become more structured and may take more time.

---

## 5. Batch input: CSV matched by filename

> Batch application data is a CSV, matched to images by a `filename` column —
> so files and rows need not be in the same order, and a missing, extra, or
> failed item becomes a per-item error instead of failing the whole batch.

**Why CSV:** agents usually work with spreadsheets and are more familiar with it.
Initally, a JSON array was used which failed the whole batch with any error and had
to be ordered.

**Why match by filename, not position:** the old endpoint zipped images to a
JSON array by order, so a reordered upload silently mis-paired data with the
wrong image. Keying on the `filename` column (case-insensitive, so
`Old_Tom.PNG` matches `old_tom.png`.)

**Why it can't fail the whole batch:** `/verify/batch` always returns 200.
An image with no CSV row, a row with no image, a row with bad values, and a
failed extraction each become a per-item `error` row; only a structurally
unusable CSV (unreadable, or missing a required column) is a 400. So one bad
item never sinks the rest.

---

## 6. Batch results progress bar UI

> `/verify/batch` streams newline-delimited JSON — a `meta` line, one
> `result` line per label as it finishes, then a `summary` — so the UI can
> show a real progress bar instead of a spinner.

**Why:** a 300-label batch takes 1-2.5 minutes (bounded by the §10 concurrency
cap). Returning everything in one response means the browser sees nothing
until the very end, which can cause users to believe it is not working.

**Trade-off:** results arrive in completion order and not file order since the client
sorts by filename before rendering.

---

## 7. One isolated external dependency

> Only one thing reaches outside the system — the vision API call in
> `extraction.py`. Everything else runs locally.

**Why:** Marcus described a past vendor pilot where half the features broke
when Treasury's firewall blocked outbound AI calls. Keeping that one
unavoidable external call in a single function means if the same
thing happens again, only that function has to change.

---

## 8. Single extraction function (no interface)

> The vision call is one plain function. An earlier version wrapped it in a
> class hierarchy with a factory but that was removed.

**Why reverted:** there's only one provider. A pluggable interface pays off
with multiple implementations, but with one, the extra class, factory, and global state were just overhead.

**Rule applied:** don't build an abstraction for a second case that doesn't
exist yet.

**Trade-off:** a future second provider means editing this function and additional work.

---

## 9. Fuzzy vs. strict comparison

> Fuzzy match allowance for brand, class/type, net contents, bottler
> name/address, and country of origin if applicable. exact matching for the
> government warning with a numeric tolerance for wine ABV.

**Why:** Dave (senior agent) pointed to rejecting "STONE'S THROW" vs "Stone's
Throw" — plainly the same brand, but an exact text match flags it, and that
kind of false rejection wastes agents' time. Jenny (junior agent) had the
reverse case: a warning printed in title case has to be rejected, because
its exact wording, casing, and bold formatting are fixed by law (27 CFR part
16, checked against ttb.gov).

**Alternative:** a single similarity score for every field. Rejected — it
would either wave through warning violations that happened to score high, or
bring back the false rejections Dave complained about which would not save agents' time.

---

## 10. Global bounded concurrency

> One shared limiter as `asyncio.Semaphore` caps how many vision-API calls
> run at once (10).

**Why:** Sarah described peak batches of 200-300 labels. Running them one at
a time takes some time, running them all at once risks tripping the vision
API's rate limit. A global limiter prevents several users from overwhelming the system. One shared limiter batches 10 images at a time globally.

---

## 11. Shared HTTP client (lifespan)

> Open one HTTP client at startup and reuse it for every vision-API call,
> instead of making a new one each time.

**Why:** opening a new encrypted (HTTPS) connection is slow — it takes
several network round-trips to set up before the request even goes out.
Reusing one client keeps those connections open, so only the first
call pays that cost. This keeps latency per call low.

---

## 12. Keep-alive ping (cold starts)

> Ping `/health` on a schedule so a free host doesn't put the app to
> sleep.

**Why:** free hosting tiers (e.g. Render) suspend the process after
~15 minutes idle, and the first request can take 30-60s while it
wakes back up. cron job hits `/health` every ~10 minutes to keep the app live.

**Alternative:** a paid tier removes the problem. This is a work-around.

---

## 13. Upload validation (magic bytes)

> Accept only JPEG/PNG, reject files over 1.5MB, and check the file's real
> signature bytes — not the type the client claims.

**Why:** the limits match TTB's own COLAs Online upload rules, so that labels aren't approved by us and later denied.

**Magic-byte check:** this avoids spoofing by actually checking the file type
so `_sniff_image_type` reads the leading bytes that only a real JPEG
(`FF D8 FF`) or PNG (`89 50 4E 47 0D 0A 1A 0A`) will have.

---

## 14. Deferred / out of scope

> Intentionally left out, not oversights.

- Blurry, glare, or poorly-lit photos (Jenny).
- Conditional label fields, which vary by product.
- COLA system integration (the real system is .NET and years away, per Marcus).
- Authentication / access control, PII/retention.
- Per-caller rate limiting (global concurrency is capped but user is not).
- Security and prompt-injection hardening.
- Other various inputs such as sulfite declaration, appellation and varietal 
rules (wine) age statements (distilled spirits), and FD&C coloring disclosures