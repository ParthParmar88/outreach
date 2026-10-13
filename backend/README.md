# Backend

FastAPI service. Python 3.11+ and PostgreSQL.

This page covers setup and the website crawler. How a search works is in the
[root README](../README.md), and measuring prompt changes is in
[eval/README.md](eval/README.md).

---

## 1. Install PostgreSQL

**With Docker:** run `docker compose up -d` from the repository root. It starts
PostgreSQL with the account that `.env.example` already expects, so skip to
step 3.

**Without Docker, on Windows:** download the installer from
<https://www.postgresql.org/download/windows/> and run it.

During setup:

- set a password for the `postgres` superuser and **write it down**
- leave the port as **5432**
- you do not need Stack Builder afterwards

No extensions are needed.

## 2. Choose a database account

The database and its tables are created for you on first startup either way. The
only decision is which account the app logs in as.

### Option A — nothing to do

Use the `postgres` superuser the installer already created. In `.env`, put the
password you chose during installation:

```
DATABASE_URL=postgresql+asyncpg://postgres:YOUR_INSTALL_PASSWORD@localhost:5432/outreach
```

URL-encode special characters: `@` → `%40`, `#` → `%23`, `/` → `%2F`.

No SQL to run. Fine locally; never ship a superuser connection to production.

### Option B — a dedicated role

One command, slightly safer, and it matches the default already in `.env.example`.

Open **SQL Shell (psql)** from the Start menu, press Enter through the prompts,
give the `postgres` password, then:

```sql
CREATE ROLE outreach WITH LOGIN CREATEDB PASSWORD 'outreach';
```

`\q` to leave. `CREATEDB` matters — without it the app cannot create its own
database and startup stops with a message telling you so.

> Never create tables by hand in psql. Alembic keeps its own record of what it
> has applied, and a hand-made table is invisible to it, so the next migration
> fails in a confusing way.

## 3. Set up Python

```bash
cd backend
py -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
```

Copy the settings file and check the password matches what you used above:

```bash
copy .env.example .env
```

```
DATABASE_URL=postgresql+asyncpg://outreach:outreach@localhost:5432/outreach
```

## 4. Tables — nothing to do

The database and its tables are created on first startup, and every new migration
is applied automatically.

This is controlled by `AUTO_MIGRATE=true` in `.env`. **Set it to `false` in
production** — two instances starting together would migrate at the same time, and
a bad migration should fail a deploy rather than take the running service down.

To apply migrations by hand instead:

```bash
.venv\Scripts\python.exe -m alembic upgrade head
```

## 5. Run it

```bash
.venv\Scripts\python.exe -m uvicorn outreach.main:app --reload
```

- API: <http://localhost:8000/api/v1>
- Interactive docs: <http://localhost:8000/docs>
- Readiness, which actually queries the database: <http://localhost:8000/api/v1/ready>

---

## Trying the crawler without a database

The fastest way to see whether it picked the right pages:

```bash
.venv\Scripts\python.exe ..\scripts\try_crawl.py https://example.com
.venv\Scripts\python.exe ..\scripts\try_crawl.py https://example.com --save out.md
.venv\Scripts\python.exe ..\scripts\try_crawl.py https://example.com --max-pages 10
```

It prints which mode discovery chose, which pages it read, how many words each
gave, and the first part of the combined markdown. No PostgreSQL involved.

## The crawler's endpoints

Every endpoint, with its request and response shapes, is listed at
<http://localhost:8000/docs>. These are the ones the crawler serves:

```
POST /api/v1/products                      { "name": "...", "url": "..." }
GET  /api/v1/products
GET  /api/v1/products/{id}                 status and the page list
GET  /api/v1/products/{id}/markdown        the combined document
POST /api/v1/products/{id}/recrawl         the only way a site is re-read
```

`POST /products` returns straight away with `state: "queued"` and reads the site
in the background. Poll `GET /products/{id}` until `state` becomes `ready`.

### The states

| state | meaning |
|---|---|
| `queued` | registered, crawl not started |
| `crawling` | in progress |
| `ready` | done, markdown stored |
| `thin` | fetched fine but every page was empty — a JavaScript-rendered site |
| `failed` | something broke, reason in `failure_reason` |

---

## How the crawl decides what to read

`connectors/website/discovery.py` looks for documentation in four places and
stops at the first real hit:

1. the usual paths — `/docs`, `/documentation`, `/guide`, `/reference` and friends
2. a docs subdomain — `docs.`, `help.`, `developers.`
3. `sitemap.xml`, looking for docs URLs inside it
4. the homepage's own links, for one whose text says "Docs"

A candidate only counts if the request succeeded, we were not redirected
somewhere unrelated, and there are at least 80 words on the page. Sites without
docs very often redirect `/docs` to the homepage, and that must not count.

**Documentation found → docs mode.** Only URLs under the docs root are crawled.
Nothing else on the site is touched.

**No documentation → site mode.** Pages are ranked by how likely they are to
explain the product:

```
first    /features /product /how-it-works /use-cases
         /solutions /platform /pricing /faq
then     the homepage, /about, /overview
never    /blog /news /careers /jobs /legal /privacy
         /terms /login /signup /contact /press
```

Blog posts and job adverts are excluded on purpose. They read like the product
without being about the product, and they are the biggest source of confusing
material.

## Manners

- `robots.txt` is read first and obeyed
- one page every half second, never in parallel against one host
- a real `User-Agent` naming us, with a contact URL
- 5xx and timeouts back off and retry three times; 4xx are not retried

## The seatbelts

Not targets. Stop lines, so one enormous documentation site cannot run for
hours. All in `.env`:

```
CRAWL_MAX_PAGES=500
CRAWL_MAX_SECONDS=900
CRAWL_MAX_BYTES=100000000
```

If one trips, `truncated` is set and `stop_reason` says which. The user is told
"we read 500 of about 5,000 pages" rather than being left to assume we read
everything.

---

## Two decisions written into this code

**No AI in the crawler.** Fetching, boilerplate removal and markdown
conversion, nothing else. That keeps it free to re-run, testable without a
model, and deterministic.

**Never re-read on a schedule.** A site is read once. The only way it is read
again is `POST /recrawl`, which only a person can trigger.

## One known limit

Crawls and searches run as FastAPI background tasks, in the same process as
the API. A server restart in the middle of one ends it. That is fine for one
person on one machine; a real deployment would move them to a job queue.
