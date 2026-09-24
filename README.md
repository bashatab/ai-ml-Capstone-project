# Module 1: Data Pipeline

## Overview

This module implements an end-to-end ETL workflow:

1. Scrape the first five pages from Books to Scrape.
2. Capture title, GBP price, rating, availability and category.
3. Clean fields into typed columns.
4. Convert price using the required fixed rate: **1 GBP = 105.50 INR**.
5. Load data into normalized SQLite `categories` and `books` tables.
6. Execute SQL queries covering SELECT, WHERE, ORDER BY, LIMIT, DISTINCT, BETWEEN, IN and JOIN.
7. Reproduce the SQL JOIN with `pandas.merge()` and verify matching output.

## Install

```bash
python -m pip install -r data_pipeline/requirements.txt
```

## Run

From the repository root:

```bash
python data_pipeline/data_pipeline.py
```

## Generated files

- `books_raw.csv`
- `books_cleaned.csv`
- `zepto_books.db`
- `query_outputs.txt`
- `join_comparison.csv`

## Cleaning decision

Rows missing a required factual field are dropped rather than inventing category, rating or stock information. The program prints missing-value and removed-row counts.

## Security note

`truststore` uses the operating system trust store on managed Windows devices. Certificate verification is not disabled.
