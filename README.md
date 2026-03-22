# Local Web Crawler & Search System

A localhost-runnable web crawler and search application built for a take-home engineering exercise.

The system provides two core capabilities:

- **Index**: start crawling from an origin URL up to depth `k`
- **Search**: query indexed pages and return relevant results while indexing may still be running

This project is intentionally designed as a **single-machine prototype** with a strong focus on clarity, reasonable scalability, persistence, and architectural simplicity. It favors **language-native functionality** and lightweight dependencies over large external frameworks.

---

## Features

- Crawl from a given origin URL up to a maximum depth
- Avoid crawling the same page twice within a session
- Store crawl state and indexed pages in a local SQLite database
- Search indexed content while the crawler is still active
- Show crawl sessions, system status, queue depth, and progress in a local web UI
- Use bounded queues and worker limits as a form of back pressure
- Keep the implementation lightweight and easy to inspect

---

## Tech Stack

- **Python 3**
- **Flask** for the local web server and UI routes
- **SQLite** for persistent local storage
- **threading** and **queue** for worker management
- **urllib** for HTTP fetching
- **html.parser** for lightweight HTML parsing
- **FTS / text matching in SQLite** for search

The project intentionally avoids fully featured crawler/search frameworks and instead relies mostly on Python standard library components plus Flask for the UI/API layer.

---

## Project Structure

```text
crawler-search/
├── app.py
├── requirements.txt
├── README.md
├── product_prd.md
├── recommendation.md
├── db/
│   └── crawler.db
├── services/
│   ├── crawler_service.py
│   ├── fetcher.py
│   ├── parser.py
│   ├── search_service.py
│   └── storage.py
└── demo/
    ├── index.html
    ├── crawler.html
    ├── search.html
    ├── detail.html
    ├── js/
    └── css/
```

> Depending on your final cleanup, the exact file list may vary slightly, but the core structure above reflects the intended organization.

---

## How It Works

### 1. Indexing

A crawl session begins with:
- an **origin URL**
- a **maximum depth `k`**
- optional limits such as max URLs, worker count, queue size, or rate settings depending on the implementation

The crawler:
- starts from the origin at depth `0`
- extracts links from fetched HTML pages
- resolves relative links to absolute URLs
- assigns each discovered page a depth equal to `parent_depth + 1`
- stops expanding children once the depth limit is reached
- records fetched pages and metadata into SQLite

Within a single session, the same normalized URL is not crawled twice.

### 2. Search

The search flow:
- accepts a query string
- searches over indexed content already stored in SQLite
- returns relevant results as triples:

```text
(relevant_url, origin_url, depth)
```

Search is designed to work **while indexing is still active**. As pages are fetched and committed to the database, they become searchable without waiting for the whole crawl to complete.

### 3. Status / Observability

The UI makes it possible to inspect:
- available crawl sessions
- current session state
- crawl progress
- indexed/discovered page counts
- queue depth
- worker / in-flight activity
- search results

This helps demonstrate the crawler’s runtime behavior and load-control decisions.

---

## Architecture Overview

The application is split into a few lightweight layers:

### Web Layer
`app.py` exposes:
- page routes for the local interface
- JSON endpoints for crawling, session status, and search

### Crawler Service
Responsible for:
- session creation
- queue management
- worker thread coordination
- deduplication
- back pressure
- persistence of discovered and fetched pages

### Fetching / Parsing
The fetcher retrieves pages using lightweight HTTP logic, while the parser extracts:
- title
- text content
- child links

### Search Service
Responsible for:
- query handling
- SQLite search access
- ranking / ordering of relevant results
- returning the expected result structure

### Storage Layer
SQLite acts as the persistent local store for:
- crawl sessions
- indexed pages
- metadata
- search index / searchable text

WAL mode is used or recommended so reads and writes can coexist more smoothly while crawling and searching happen at the same time.

---

## Back Pressure / Load Control

A key requirement of the exercise is some notion of controlled load. This project addresses that with a combination of the following ideas:

- bounded queue size
- limited worker concurrency
- optional max URL count per session
- request timeouts
- optional rate limiting between fetches

These controls help prevent the crawler from growing work indefinitely and make the system safer and easier to observe on localhost.

---

## Search While Indexing

One of the design goals is that search should not require indexing to finish first.

This is handled by:
- writing fetched page content to SQLite incrementally
- reading search results directly from the database
- allowing committed pages to become searchable immediately

This gives the system a simple but effective **incremental indexing** behavior.

---

## Setup

### 1. Clone the repository

```bash
git clone <your-repo-url>
cd crawler-search
```

### 2. Create a virtual environment

```bash
python -m venv .venv
```

Activate it:

#### macOS / Linux
```bash
source .venv/bin/activate
```

#### Windows
```bash
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

---

## Run the Project

Start the application with:

```bash
python app.py
```

Then open your browser and go to:

```text
http://127.0.0.1:5000
```

From there, you can:
- start a crawl session
- inspect session progress
- search indexed pages
- view system status

---

## Usage

### Start a Crawl
From the crawler page:
1. Enter an origin URL
2. Choose a maximum depth
3. Optionally configure crawl limits if supported
4. Start indexing

### View Crawl State
Use the session/status views to inspect:
- session metadata
- indexed page counts
- queue depth
- completion/error state
- detailed crawl results

### Search
Go to the search page:
1. Enter a query
2. Run search
3. View relevant results including:
   - relevant URL
   - origin URL
   - depth

---

## Example Behavior

If you start crawling:

```text
https://www.wikipedia.org/
```

with depth `2`, then:

- the origin page is depth `0`
- links found directly on that page are depth `1`
- links found from those depth `1` pages are depth `2`

Search results returned by the system are shaped like:

```text
(relevant_url, origin_url, depth)
```

For example:

```text
(https://en.wikipedia.org/wiki/Web_crawler, https://www.wikipedia.org/, 1)
```

---

## Assumptions and Scope

This is a deliberately scoped implementation for a take-home project. A few assumptions were made to keep the system practical and well-crafted within the available time:

- the crawler runs on a single machine
- indexing and search use a local database
- JavaScript-rendered pages are out of scope
- relevance is intentionally simple and explainable
- the system prioritizes clarity and correctness over internet-scale completeness

This is not intended to be a production web crawler, but rather a solid local prototype with sensible architecture.

---

## Design Choices

### Why SQLite?
SQLite is a strong fit for this assignment because:
- it is local and simple to run
- it supports persistence without external infrastructure
- it works well for moderate-scale single-machine applications
- it can support concurrent reads with WAL mode

### Why Threads + Queue?
Using Python threads and a bounded queue is a lightweight way to:
- model crawl workers
- control concurrency
- implement back pressure
- keep the code easy to reason about

### Why Lightweight Parsing and Fetching?
The assignment explicitly prefers language-native functionality. Using `urllib`, `html.parser`, `queue`, `threading`, and `sqlite3` demonstrates the core engineering logic directly instead of outsourcing it to large frameworks.

---

## Limitations

This project intentionally does **not** include full production crawler functionality. Current limitations may include:

- no distributed crawling
- limited URL canonicalization
- no robots.txt compliance
- no JavaScript rendering
- simple relevance/ranking
- no advanced duplicate-content detection
- limited domain-level politeness logic
- partial rather than full crash-safe resume behavior

These are acceptable tradeoffs for the scope of the exercise.

---

## Production Next Steps

Production-oriented recommendations are documented in:

```text
recommendation.md
```

In summary, the most important next steps would be:
- stronger fault tolerance and durable job state
- better domain-aware crawl politeness
- richer indexing and ranking
- stronger observability and metrics
- improved recovery/resume behavior
- eventual separation of crawler, API, and search components if scale grows

---

## Deliverables Included

This repository includes:

- runnable source code
- local web UI
- persistent local database support
- `README.md`
- `product_prd.md`
- `recommendation.md`

---

## Evaluation Fit

This project is designed to align with the exercise goals:

- thoughtful architecture over unnecessary complexity
- localhost runnable
- persistent local DB
- indexing + search
- search during active crawling
- system status visibility
- back pressure / load control
- lightweight implementation choices

---

## Notes

If a pre-existing database file is included in the repository, you may remove it for a cleaner first run and let the application recreate it automatically. This is usually the tidiest option for final submission.

If needed, reset the local database before rerunning with a clean state by deleting the SQLite files in the `db/` directory.

---

## License

This project was created as part of a take-home engineering exercise.requ