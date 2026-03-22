# Product PRD — Local Web Crawler & Search System

## 1. Product Overview

This project is a localhost-runnable web crawler and search system designed for a take-home engineering exercise. The system must expose two primary capabilities:

1. **Index**: Start crawling from an origin URL up to a maximum depth `k`, ensuring the same page is never crawled twice within the same crawl session.
2. **Search**: Accept a text query and return relevant indexed URLs as triples of the form:

```text
(relevant_url, origin_url, depth)
```

Where:
- `relevant_url` is the indexed page considered relevant to the query
- `origin_url` is the original URL used to start the crawl session
- `depth` is the number of hops from the origin to that page

The project should be intentionally scoped for a **single-machine, localhost environment**, while still demonstrating sound architectural thinking for large crawl workloads. The solution should favor **language-native functionality** and lightweight dependencies over full-featured crawling or search frameworks.

---

## 2. Goal

Build a practical, understandable crawler/search application that:

- crawls pages up to depth `k`
- avoids revisiting the same page in a crawl session
- stores crawl results persistently in a local database
- supports search while indexing is still in progress
- shows crawl and system status through a simple UI
- demonstrates back pressure / load control
- can be run and evaluated easily on localhost

This project is not intended to be a production-grade internet crawler. It is intended to show strong engineering judgment, solid implementation choices, and clear tradeoffs within a limited time window.

---

## 3. Primary Users

### 3.1 Evaluator / Reviewer

A technical reviewer who wants to:
- run the project locally
- inspect the architecture
- confirm the crawler/search behavior
- verify the UI and system observability
- assess scalability thinking and implementation quality

### 3.2 Developer

A developer using this PRD to implement or extend the system with AI assistance.

---

## 4. Core Requirements

### 4.1 Index Capability

The system must expose an indexing workflow that:
- accepts:
  - `origin` (URL)
  - `k` (maximum crawl depth)
- starts crawling from `origin`
- explores links breadth-first or equivalently by tracked depth
- never crawls the same normalized URL twice within the same session
- records:
  - discovered URL
  - originating crawl session
  - depth of discovery
  - crawl/fetch result metadata
  - extracted page text for search
- stops discovering children once depth exceeds `k`

#### Expected behavior

- depth `0` = origin page
- direct links from origin = depth `1`
- links found from depth `1` pages = depth `2`, etc.

---

### 4.2 Search Capability

The system must expose a search workflow that:
- accepts a free-text query string
- returns relevant indexed results as triples:

```text
(relevant_url, origin_url, depth)
```

- works while indexing is still active
- reflects newly indexed pages as they are committed to the database

#### Relevancy assumption

For this exercise, relevance may be defined using a lightweight text-matching strategy, such as:
- token matching on page title and body text
- SQL `LIKE` search or SQLite FTS-based ranking
- a simple, explainable scoring function

The goal is not advanced information retrieval quality, but a reasonable and transparent search implementation.

---

### 4.3 UI / CLI Requirement

The project must include a simple interface that makes it easy to:
- initiate indexing
- run search
- inspect crawl status
- view queue depth / in-flight work / progress indicators
- understand whether load control or back pressure is active

A web UI is preferred for clarity, but a CLI is acceptable if it satisfies the same usability goals.

---

### 4.4 Persistence

The system should persist state to a local database so that:
- indexed pages survive application restarts
- crawl sessions can be inspected after completion
- search operates over persisted indexed content

A lightweight local DB such as SQLite is appropriate.

---

### 4.5 Resume Capability (Nice to Have)

It is a plus, though not strictly required, if the crawl can resume after interruption without restarting everything from scratch.

For the initial version, partial persistence of completed work is sufficient even if full crash-safe queue replay is not implemented.

---

## 5. Non-Goals

The following are explicitly out of scope for this exercise:
- distributed crawling across multiple machines
- advanced politeness rules across many domains
- JavaScript rendering with a headless browser
- large-scale ranking algorithms like PageRank
- semantic vector search
- duplicate-content clustering across the entire web
- production-grade anti-bot / anti-ban strategies
- authentication-protected crawling
- full internet-scale scheduling/orchestration

---

## 6. Functional Requirements

### 6.1 Session Management

The system must support multiple crawl sessions over time.

Each crawl session should store:
- session ID
- origin URL
- requested max depth
- optional crawl limits (e.g. max URLs)
- status (`running`, `completed`, `error`)
- timestamps
- aggregate crawl metrics

---

### 6.2 URL Deduplication

The crawler must avoid duplicate crawling within a session.

Deduplication should be based on normalized URLs, for example:
- normalized scheme/host casing
- fragment removal
- basic canonicalization where reasonable

At minimum:
- exact duplicate URLs must not be re-crawled twice
- pages already seen in the same session should not be enqueued again

---

### 6.3 Link Extraction

For fetched HTML pages, the system must:
- parse anchor tags
- resolve relative links against the current page URL
- filter to supported HTTP/HTTPS URLs
- assign child depth = parent depth + 1

---

### 6.4 Content Extraction

For fetched HTML pages, the system should:
- extract page title if available
- extract visible or text-like content in a lightweight way
- store enough textual material to support keyword search

Implementation should prefer standard or lightweight parsing over heavy libraries.

---

### 6.5 Crawl Limits

The indexer should include guardrails such as:
- maximum depth
- maximum indexed URLs per session
- bounded work queue
- request timeout
- optional per-second fetch throttling

These controls ensure the system remains stable and evaluable on localhost.

---

### 6.6 Back Pressure

The system must implement some notion of back pressure or controlled load.

Acceptable mechanisms include:
- bounded queue size
- rate limiting between fetches
- limiting number of worker threads
- rejecting or delaying additional enqueues when the queue is full

The system should surface this state in the UI or status output where possible.

---

### 6.7 Search Output Format

Search results must include, directly or indirectly:
- relevant URL
- origin URL
- depth

Optional metadata may also include:
- title
- short snippet
- session ID
- score

---

### 6.8 Search During Active Indexing

Search should not require the crawl to finish first.

As new pages are fetched and stored:
- they should become searchable
- readers should not block ongoing writes unnecessarily

This is a core expectation of the system design.

---

## 7. Suggested Architecture

A practical architecture for this project is:

### 7.1 Frontend / UI

A minimal local web UI that provides:
- crawl start form
- session list
- session detail / status view
- search form and results
- live or refresh-based progress indicators

### 7.2 Application Layer

A thin HTTP server (e.g. Flask) providing:
- page routes for UI
- JSON APIs for crawler actions, status, and search

### 7.3 Crawler Service

Responsible for:
- session creation
- queue management
- worker lifecycle
- deduplication
- link extraction
- fetch scheduling
- back pressure control
- persistence of discovered/fetched pages

### 7.4 Search Service

Responsible for:
- query parsing
- DB lookup
- ranking / simple relevance scoring
- returning structured result rows

### 7.5 Storage Layer

A local SQLite database handling:
- sessions
- indexed pages
- discovered URLs
- search text / FTS index
- metrics

Using SQLite WAL mode is strongly recommended so reads and writes can coexist more smoothly.

---

## 8. Data Model Recommendations

The exact schema may vary, but the system should conceptually store the following entities.

### 8.1 Crawl Sessions

Fields may include:
- `id`
- `origin_url`
- `max_depth`
- `status`
- `created_at`
- `updated_at`
- `pages_crawled`
- `pages_discovered`
- `errors_count`

### 8.2 Indexed Pages

Fields may include:
- `id`
- `session_id`
- `url`
- `normalized_url`
- `depth`
- `parent_url`
- `http_status`
- `content_type`
- `title`
- `body_text`
- `fetch_status`
- `error_message`
- `created_at`

### 8.3 Search Index

One of:
- SQLite FTS table over page title/body
- or simpler indexed text columns with fallback matching

---

## 9. Technical Constraints

- Must run on localhost
- Must use a local DB
- Should prefer Python standard library and lightweight dependencies
- Should avoid using fully featured external crawler/search frameworks that solve the exercise out of the box
- Must be understandable and reviewable within the scope of a take-home project

---

## 10. Recommended Implementation Choices

### 10.1 Fetching

Use:
- `urllib.request` or similarly lightweight built-in functionality

Support:
- timeouts
- basic redirect handling
- content-type checks

### 10.2 HTML Parsing

Use:
- Python `html.parser`
- or another lightweight parser if necessary

### 10.3 Concurrency

Use:
- `threading`
- `queue.Queue`
- a small fixed worker pool

This is sufficient for a single-machine crawl design and easy to reason about.

### 10.4 Persistence

Use:
- `sqlite3`

Recommended SQLite settings:
- WAL mode
- proper indexes
- foreign keys
- careful write boundaries

---

## 11. Search-While-Indexing Design Recommendation

Although the exercise states we may assume `index` is invoked before `search`, the system should still support search while indexing is active.

Recommended approach:
- crawler workers write indexed pages to SQLite as soon as each page is processed
- search queries read directly from SQLite
- SQLite WAL mode allows readers and writers to coexist with low contention
- each page becomes searchable immediately after its transaction commits

This design keeps the implementation simple while still demonstrating real-time incremental indexing behavior.

---

## 12. Back Pressure Design Recommendation

A reasonable back pressure strategy is:
- fixed number of worker threads
- bounded queue of pending URLs
- per-request delay or token bucket style throttling
- max pages per crawl session
- timeout and error handling for slow/unreachable pages

The UI/status view should show at least some of:
- queue depth
- pages crawled
- in-flight workers
- whether the queue is near capacity

---

## 13. UI Requirements

The UI should include at minimum:

### 13.1 Crawl Start View

Inputs:
- origin URL
- max depth
- optional max URLs / rate settings

Action:
- start new crawl session

### 13.2 Session List / Dashboard

Show:
- session ID
- origin
- status
- created time
- crawled count
- discovered count

### 13.3 Session Detail / Status View

Show:
- current state
- queue depth
- in-flight work
- number of indexed pages
- number of errors
- recent discovered pages or results

### 13.4 Search View

Inputs:
- query
- optional session filter

Show:
- relevant URL
- origin URL
- depth
- optional title/snippet

---

## 14. Error Handling Expectations

The system should behave gracefully for:
- invalid URLs
- DNS failures
- non-HTML content
- redirects
- timeouts
- broken pages
- empty search results

Errors should be recorded without crashing the entire crawl session whenever possible.

---

## 15. Local Run Expectations

The repository should be easy to run on localhost with:
- a short install step
- a single startup command
- clear documentation in `README.md`

Expected repo deliverables:
- runnable source code
- `README.md`
- `product_prd.md`
- `recommendation.md`

---

## 16. Acceptance Criteria

The project is considered successful if:

1. A user can start a crawl from a URL with depth `k`
2. The crawler does not repeatedly crawl the same page within a session
3. Indexed pages are stored in a local database
4. A user can search indexed content and receive relevant results
5. Search can return results while crawling is still ongoing
6. The user can inspect crawl/system state in a simple UI or CLI
7. The project runs locally with documented steps
8. The implementation demonstrates sensible load control and architectural judgment

---

## 17. Tradeoff Guidance

Because this is a 3–5 hour scoped exercise, priority should be:
1. correctness of crawl/session behavior
2. clarity of architecture
3. live search over persisted data
4. observability/status visibility
5. thoughtful constraints and back pressure
6. polish

It is better to deliver a smaller, cleanly implemented system than an overly ambitious one with fragile features.

---

## 18. Future Extension Ideas

Possible future improvements include:
- robots.txt support
- domain scoping controls
- stronger URL canonicalization
- better duplicate detection
- richer ranking/snippet generation
- crash-safe queue recovery
- scheduled recrawls
- per-domain politeness policies
- production-ready worker orchestration

---

## 19. Deliverables Summary

The repository should include:
- source code for crawler, search, storage, and UI
- localhost-runnable application
- `README.md` explaining setup and usage
- `product_prd.md` describing product requirements for AI-assisted building
- `recommendation.md` with short production next-step recommendations

---

## 20. Final Product Intent

This product should feel like a thoughtful engineering exercise submission:
- simple
- inspectable
- locally runnable
- architecturally sensible
- explicit about tradeoffs
- strong enough to demonstrate how indexing, searching, persistence, and system visibility work together