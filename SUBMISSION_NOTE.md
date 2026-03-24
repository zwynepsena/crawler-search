# Submission Note

This submission contains a localhost-runnable web crawler and search system built for the homework.

Included files:
- `README.md` — project overview, setup, and usage instructions
- `product_prd.md` — PRD written for AI-assisted project building
- `recommendation.md` — short production deployment recommendations
- `requirements.txt` — Python dependencies
- `db/crawler.db` — crawled and indexed data storage (SQLite)

## GitHub Repository

https://github.com/zwynepsena/crawler-search

## Run

```bash
pip install -r requirements.txt
python app.py

Then open:

```text
http://127.0.0.1:5000
```

## Notes

- The project is designed for a single-machine localhost environment.
- It uses a local SQLite database for crawled and indexed data storage.
- In this implementation, SQLite (db/crawler.db) is used instead of a flat raw storage file such as data/storage/p.data.
- Search is designed to work while indexing is active.
- The implementation intentionally favors lightweight, language-native components where practical.