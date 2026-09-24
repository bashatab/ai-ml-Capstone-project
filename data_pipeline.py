"""Module 1: scrape -> clean -> enrich -> SQLite -> SQL -> pandas validation."""
from pathlib import Path
from urllib.parse import urljoin
import re, sqlite3, time
import truststore
truststore.inject_into_ssl()
import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://books.toscrape.com/"
CATALOGUE_URL = urljoin(BASE_URL, "catalogue/")
GBP_TO_INR = 105.50
PAGES = 5
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "zepto_books.db"
RAW_PATH = BASE_DIR / "books_raw.csv"
CLEAN_PATH = BASE_DIR / "books_cleaned.csv"
QUERY_PATH = BASE_DIR / "query_outputs.txt"
COMPARE_PATH = BASE_DIR / "join_comparison.csv"
RATING_MAP = {"One":1,"Two":2,"Three":3,"Four":4,"Five":5}
HEADERS = {"User-Agent":"Mozilla/5.0 (compatible; AIMLCapstoneStudentProject/1.0)"}

def get_soup(url, retries=3):
    last = None
    for attempt in range(1, retries+1):
        try:
            r=requests.get(url,headers=HEADERS,timeout=30)
            r.raise_for_status()
            return BeautifulSoup(r.text,"html.parser")
        except requests.RequestException as e:
            last=e; print(f"Attempt {attempt} failed for {url}: {e}")
            if attempt<retries: time.sleep(2)
    raise last

def clean_price(text):
    if text is None: return None
    value=re.sub(r"[^0-9.]","",str(text))
    try: return float(value) if value else None
    except ValueError: return None

def clean_rating(text): return RATING_MAP.get(str(text).strip()) if text else None

def clean_stock(text):
    if text is None: return None
    value=" ".join(str(text).split()).lower()
    if "out of stock" in value: return False
    if "in stock" in value: return True
    return None

def get_category(book_url):
    links=get_soup(book_url).select("ul.breadcrumb li a")
    return links[2].get_text(strip=True) if len(links)>=3 else None

def scrape_page(url,page_number):
    cards=get_soup(url).select("article.product_pod")
    rows=[]
    for i,card in enumerate(cards,1):
        a=card.select_one("h3 a"); price=card.select_one("p.price_color")
        rating=card.select_one("p.star-rating"); stock=card.select_one("p.instock.availability")
        if not all([a,price,rating,stock]): continue
        title=a.get("title",a.get_text(strip=True))
        rating_word=next((c for c in rating.get("class",[]) if c in RATING_MAP),None)
        book_url=urljoin(url,a.get("href"))
        try: category=get_category(book_url)
        except requests.RequestException as e:
            print(f"Category failed for {title}: {e}"); category=None
        rows.append({"title":title,"price":price.get_text(strip=True),"star_rating":rating_word,
                     "availability":stock.get_text(" ",strip=True),"category":category})
        print(f"Page {page_number}, book {i}: {title}")
        time.sleep(.05)
    return rows

def scrape_books():
    rows=[]
    for p in range(1,PAGES+1):
        url=urljoin(CATALOGUE_URL,f"page-{p}.html")
        print(f"\nScraping page {p}: {url}")
        rows.extend(scrape_page(url,p))
    return pd.DataFrame(rows)

def clean_data(raw):
    if raw.empty: raise ValueError("The scraper returned no rows.")
    df=raw.copy()
    df["price_gbp"]=df["price"].apply(clean_price)
    df["rating"]=df["star_rating"].apply(clean_rating)
    df["in_stock"]=df["availability"].apply(clean_stock)
    required=["title","price_gbp","rating","in_stock","category"]
    print("\nMissing before cleaning:\n",df[required].isna().sum())
    before=len(df); df=df.dropna(subset=required).drop_duplicates(["title","category"]).copy()
    print(f"Rows removed: {before-len(df)}")
    df["price_gbp"]=df["price_gbp"].astype(float).round(2)
    df["rating"]=df["rating"].astype(int)
    df["in_stock"]=df["in_stock"].astype(bool)
    df["price_inr"]=(df["price_gbp"]*GBP_TO_INR).round(2)
    return df[["title","price_gbp","price_inr","rating","in_stock","category"]].reset_index(drop=True)

def validate(df):
    assert len(df)>=60, "Need at least 60 valid books"
    assert df.category.nunique()>=3, "Need at least 3 categories"
    assert df.rating.between(1,5).all(), "Ratings must be 1 to 5"
    assert (((df.price_gbp*GBP_TO_INR).round(2)-df.price_inr).abs()<.01).all(), "INR conversion failed"
    print(f"\nValidation passed: {len(df)} books, {df.category.nunique()} categories")

def create_database(df):
    con=sqlite3.connect(DB_PATH); con.execute("PRAGMA foreign_keys=ON")
    con.executescript("""
    DROP TABLE IF EXISTS books; DROP TABLE IF EXISTS categories;
    CREATE TABLE categories(category_id INTEGER PRIMARY KEY, category_name TEXT UNIQUE NOT NULL);
    CREATE TABLE books(book_id INTEGER PRIMARY KEY, title TEXT NOT NULL, price_gbp REAL NOT NULL,
      price_inr REAL NOT NULL, rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
      in_stock INTEGER NOT NULL CHECK(in_stock IN (0,1)), category_id INTEGER NOT NULL,
      FOREIGN KEY(category_id) REFERENCES categories(category_id));
    """)
    cats=sorted(df.category.unique())
    con.executemany("INSERT INTO categories(category_name) VALUES (?)",[(x,) for x in cats])
    cmap=dict(con.execute("SELECT category_name,category_id FROM categories").fetchall())
    rows=[(r.title,float(r.price_gbp),float(r.price_inr),int(r.rating),int(r.in_stock),cmap[r.category]) for r in df.itertuples(index=False)]
    con.executemany("INSERT INTO books(title,price_gbp,price_inr,rating,in_stock,category_id) VALUES (?,?,?,?,?,?)",rows)
    con.commit(); return con

def queries():
    return {
      "1 SELECT WHERE":"SELECT book_id,title,rating,price_inr FROM books WHERE rating=5 ORDER BY title;",
      "2 ORDER BY LIMIT":"SELECT book_id,title,price_gbp,price_inr FROM books ORDER BY price_gbp DESC LIMIT 10;",
      "3 DISTINCT":"SELECT DISTINCT category_name FROM categories ORDER BY category_name;",
      "4 BETWEEN":"SELECT book_id,title,price_gbp,rating FROM books WHERE price_gbp BETWEEN 20 AND 40 ORDER BY price_gbp;",
      "5 IN":"SELECT book_id,title,rating,in_stock FROM books WHERE rating IN (4,5) ORDER BY rating DESC,title;",
      "6 JOIN":"""SELECT b.book_id,b.title,b.price_gbp,b.price_inr,b.rating,b.in_stock,c.category_id,c.category_name
        FROM books b JOIN categories c ON b.category_id=c.category_id ORDER BY b.book_id;"""
    }

def run_queries(con):
    sections=[]
    for name,q in queries().items():
        result=pd.read_sql_query(q,con)
        sections += ["="*70,name,"="*70,q,"\nOutput:",result.to_string(index=False),""]
        print(f"\n{name}\n{result.to_string(index=False)}")
    QUERY_PATH.write_text("\n".join(sections),encoding="utf-8")

def compare_join(con):
    sql=pd.read_sql_query(queries()["6 JOIN"],con).sort_values("book_id").reset_index(drop=True)
    books=pd.read_sql_query("SELECT * FROM books",con)
    cats=pd.read_sql_query("SELECT * FROM categories",con)
    merged=pd.merge(books,cats,on="category_id",how="inner")[sql.columns].sort_values("book_id").reset_index(drop=True)
    match=sql.equals(merged)
    pd.DataFrame({"sql_title":sql.title,"pandas_title":merged.title,"rows_match":sql.title.eq(merged.title)}).to_csv(COMPARE_PATH,index=False)
    print(f"\nSQL JOIN matches pandas merge: {match}")
    if not match: raise ValueError("JOIN outputs do not match")

def main():
    raw=scrape_books(); raw.to_csv(RAW_PATH,index=False)
    clean=clean_data(raw); validate(clean); clean.to_csv(CLEAN_PATH,index=False)
    con=create_database(clean)
    try:
        run_queries(con)
        pd.read_sql_query("SELECT * FROM books WHERE rating=5",con)
        pd.read_sql_query("SELECT * FROM books ORDER BY price_gbp DESC LIMIT 10",con)
        compare_join(con)
    finally: con.close()
    print("\nMODULE 1 COMPLETED SUCCESSFULLY")
    for p in [RAW_PATH,CLEAN_PATH,DB_PATH,QUERY_PATH,COMPARE_PATH]: print("-",p.name)

if __name__=="__main__": main()
