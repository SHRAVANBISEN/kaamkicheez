# news_fetcher.py — Global market news fetcher
# Sources: RSS feeds (free, no API key, no rate limits)
# Covers: Global markets, Indian markets, stock-specific news

import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import time
import re

# ── RSS Feed Sources ───────────────────────────────────────

GLOBAL_MARKET_FEEDS = [
    # Global Markets
    {
        "name": "Reuters Markets",
        "url":  "https://feeds.reuters.com/reuters/businessNews",
        "tags": ["global", "economy", "fed", "rates"]
    },
    {
        "name": "CNBC Markets",
        "url":  "https://search.cnbc.com/rs/search/combinedcsvfeed?tag=worldmarketsNews&moduleId=0_16&assetType=RSS",
        "tags": ["global", "markets", "wall street"]
    },
    {
        "name": "Yahoo Finance",
        "url":  "https://finance.yahoo.com/news/rssindex",
        "tags": ["global", "stocks", "earnings"]
    },
    # Indian Markets
    {
        "name": "Economic Times Markets",
        "url":  "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
        "tags": ["india", "nse", "bse", "sensex", "nifty"]
    },
    {
        "name": "Economic Times Economy",
        "url":  "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms",
        "tags": ["india", "rbi", "inflation", "gdp"]
    },
    {
        "name": "Mint Markets",
        "url":  "https://www.livemint.com/rss/markets",
        "tags": ["india", "nse", "markets"]
    },
    {
        "name": "Business Standard Markets",
        "url":  "https://www.business-standard.com/rss/markets-106.rss",
        "tags": ["india", "markets", "stocks"]
    },
    # Macro / Global Factors
    {
        "name": "Google News - India Markets",
        "url":  "https://news.google.com/rss/search?q=indian+stock+market+nifty+sensex&hl=en-IN&gl=IN&ceid=IN:en",
        "tags": ["india", "nifty", "sensex"]
    },
    {
        "name": "Google News - Global Economy",
        "url":  "https://news.google.com/rss/search?q=global+economy+stock+market+fed+rates&hl=en&gl=US&ceid=US:en",
        "tags": ["global", "economy", "fed", "rates"]
    },
    {
        "name": "Google News - FII DII",
        "url":  "https://news.google.com/rss/search?q=FII+DII+indian+market+investment&hl=en-IN&gl=IN&ceid=IN:en",
        "tags": ["india", "fii", "dii", "flows"]
    },
]

# Stock-specific query templates
STOCK_NEWS_TEMPLATES = [
    "https://news.google.com/rss/search?q={company}+NSE+stock+share&hl=en-IN&gl=IN&ceid=IN:en",
    "https://economictimes.indiatimes.com/rssfeedstopstories.cms",
]

# Company name map for better search results
COMPANY_NAMES = {
    "RELIANCE":   "Reliance Industries",
    "TCS":        "Tata Consultancy Services TCS",
    "INFY":       "Infosys",
    "HDFCBANK":   "HDFC Bank",
    "ICICIBANK":  "ICICI Bank",
    "SBIN":       "State Bank of India SBI",
    "WIPRO":      "Wipro",
    "AXISBANK":   "Axis Bank",
    "LT":         "Larsen Toubro L&T",
    "BAJFINANCE": "Bajaj Finance",
    "TATAMOTORS": "Tata Motors",
    "SUNPHARMA":  "Sun Pharma",
    "ADANIENT":   "Adani Enterprises",
    "HCLTECH":    "HCL Technologies",
    "KOTAKBANK":  "Kotak Mahindra Bank",
    "BHARTIARTL": "Bharti Airtel",
    "MARUTI":     "Maruti Suzuki",
    "TITAN":      "Titan Company",
    "ULTRACEMCO": "UltraTech Cement",
    "NESTLEIND":  "Nestle India",
}


# ── Core RSS Parser ────────────────────────────────────────

def _parse_rss(url, max_items=5, timeout=8):
    """Parse RSS feed and return list of headline dicts."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; StockTradingAlgo/1.0)"
        }
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()

        root  = ET.fromstring(resp.content)
        items = []

        # Handle both RSS and Atom formats
        channel = root.find("channel")
        entries = channel.findall("item") if channel else root.findall(".//{http://www.w3.org/2005/Atom}entry")

        for item in entries[:max_items]:
            # Get title
            title_el = item.find("title")
            title    = title_el.text if title_el is not None else ""
            if not title:
                continue

            # Clean title (remove CDATA, HTML tags)
            title = re.sub(r"<[^>]+>", "", title).strip()
            title = re.sub(r"\s+", " ", title)

            # Get published date
            pub_el  = item.find("pubDate") or item.find("published")
            pub_str = pub_el.text if pub_el is not None else ""

            # Get description/summary
            desc_el  = item.find("description") or item.find("summary")
            desc_str = desc_el.text if desc_el is not None else ""
            desc_str = re.sub(r"<[^>]+>", "", desc_str or "").strip()[:200]

            items.append({
                "title":       title,
                "description": desc_str,
                "published":   pub_str,
                "source":      url,
            })

        return items

    except Exception as e:
        return []


def _is_recent(pub_str, hours=48):
    """Check if a news item is within the last N hours."""
    if not pub_str:
        return True  # assume recent if no date
    try:
        # Try common date formats
        for fmt in [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S%z",
        ]:
            try:
                pub_dt = datetime.strptime(pub_str.strip(), fmt)
                if pub_dt.tzinfo:
                    pub_dt = pub_dt.replace(tzinfo=None)
                cutoff = datetime.utcnow() - timedelta(hours=hours)
                return pub_dt > cutoff
            except ValueError:
                continue
        return True  # if can't parse, include it
    except Exception:
        return True


def _deduplicate(headlines):
    """Remove duplicate headlines by similarity."""
    seen  = []
    dedup = []
    for h in headlines:
        title = h["title"].lower()[:60]
        if not any(title[:40] in s for s in seen):
            seen.append(title)
            dedup.append(h)
    return dedup


# ── Public Functions ───────────────────────────────────────

def fetch_global_market_news(max_per_source=3, max_total=20):
    """
    Fetch global and Indian market news from all sources.
    Returns list of headline dicts sorted by relevance.
    Used for: morning brief, stock recommendations.
    """
    all_headlines = []

    for feed in GLOBAL_MARKET_FEEDS:
        try:
            items = _parse_rss(feed["url"], max_items=max_per_source)
            for item in items:
                item["source_name"] = feed["name"]
                item["tags"]        = feed["tags"]
                all_headlines.append(item)
            time.sleep(0.2)  # be polite to servers
        except Exception:
            continue

    # Filter to recent only
    all_headlines = [h for h in all_headlines if _is_recent(h["published"], hours=48)]

    # Deduplicate
    all_headlines = _deduplicate(all_headlines)

    return all_headlines[:max_total]


def fetch_stock_news(symbol, max_items=6):
    """
    Fetch news specific to one stock.
    Used for: individual stock analysis.
    Returns list of headline strings.
    """
    symbol      = symbol.upper().strip()
    company     = COMPANY_NAMES.get(symbol, symbol)
    all_items   = []

    # Google News search for this stock
    urls = [
        f"https://news.google.com/rss/search?q={company.replace(' ', '+')}+stock+share&hl=en-IN&gl=IN&ceid=IN:en",
        f"https://news.google.com/rss/search?q={symbol}+NSE&hl=en-IN&gl=IN&ceid=IN:en",
    ]

    for url in urls:
        items = _parse_rss(url, max_items=4)
        all_items.extend(items)
        time.sleep(0.2)

    # Filter recent, deduplicate
    all_items = [h for h in all_items if _is_recent(h["published"], hours=72)]
    all_items = _deduplicate(all_items)

    # Return just headlines (titles)
    return [item["title"] for item in all_items[:max_items]]


def fetch_macro_news(max_items=8):
    """
    Fetch macro-economic news that affects all stocks.
    RBI, inflation, FII/DII flows, global cues.
    """
    macro_feeds = [
        "https://news.google.com/rss/search?q=RBI+interest+rate+india&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=US+Fed+rate+decision+markets&hl=en&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=FII+selling+buying+india+2026&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=india+inflation+GDP+economy&hl=en-IN&gl=IN&ceid=IN:en",
        "https://news.google.com/rss/search?q=crude+oil+price+india+impact&hl=en&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=dollar+rupee+exchange+rate&hl=en-IN&gl=IN&ceid=IN:en",
    ]

    all_items = []
    for url in macro_feeds:
        items = _parse_rss(url, max_items=2)
        all_items.extend(items)
        time.sleep(0.15)

    all_items = [h for h in all_items if _is_recent(h["published"], hours=48)]
    all_items = _deduplicate(all_items)

    return [item["title"] for item in all_items[:max_items]]


def get_news_for_analysis(symbol):
    """
    Main function called by ai_analyst.py for stock analysis.
    Returns dict with stock-specific + macro news.
    """
    stock_news = fetch_stock_news(symbol, max_items=5)
    macro_news = fetch_macro_news(max_items=4)

    return {
        "symbol":      symbol,
        "stock_news":  stock_news,
        "macro_news":  macro_news,
        "fetched_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def format_news_for_prompt(news_data):
    """Format news dict into clean prompt section."""
    if not news_data:
        return "No recent news available."

    lines = []

    stock_news = news_data.get("stock_news", [])
    if stock_news:
        lines.append(f"RECENT NEWS — {news_data.get('symbol','')} (last 72 hours):")
        for i, headline in enumerate(stock_news, 1):
            lines.append(f"  {i}. {headline}")

    macro_news = news_data.get("macro_news", [])
    if macro_news:
        lines.append("\nMACRO / GLOBAL MARKET NEWS (last 48 hours):")
        for i, headline in enumerate(macro_news, 1):
            lines.append(f"  {i}. {headline}")

    lines.append(f"\n  (News fetched at: {news_data.get('fetched_at','')})")

    return "\n".join(lines)


def get_news_for_batch(symbols):
    """
    Fetch news for multiple stocks efficiently.
    Returns dict of {symbol: news_data}
    Used for watchlist batch analysis.
    """
    # Fetch macro news once (shared for all stocks)
    macro_news   = fetch_macro_news(max_items=5)
    batch_news   = {}

    for symbol in symbols:
        stock_news = fetch_stock_news(symbol, max_items=4)
        batch_news[symbol] = {
            "symbol":     symbol,
            "stock_news": stock_news,
            "macro_news": macro_news,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        time.sleep(0.3)  # polite delay between stocks

    return batch_news


# ── Stock Recommendation from News ────────────────────────

def fetch_news_for_recommendations(max_headlines=25):
    """
    Fetch comprehensive news for Gemini to recommend
    tradeable stocks from. Used by recommendation engine.
    Returns formatted string of all news.
    """
    all_news   = fetch_global_market_news(max_per_source=4, max_total=25)
    macro      = fetch_macro_news(max_items=6)

    lines = []
    lines.append("=== GLOBAL + INDIAN MARKET NEWS (last 48 hours) ===\n")

    # Group by source category
    india_news  = [h for h in all_news if "india" in h.get("tags", [])]
    global_news = [h for h in all_news if "global" in h.get("tags", [])]

    if india_news:
        lines.append("INDIAN MARKET NEWS:")
        for h in india_news[:10]:
            lines.append(f"  • {h['title']}")
        lines.append("")

    if global_news:
        lines.append("GLOBAL MARKET NEWS:")
        for h in global_news[:8]:
            lines.append(f"  • {h['title']}")
        lines.append("")

    if macro:
        lines.append("MACRO / FII / RATES:")
        for h in macro[:6]:
            lines.append(f"  • {h}")
        lines.append("")

    return "\n".join(lines)


# ── Entry point ────────────────────────────────────────────

if __name__ == "__main__":
    print("Testing news fetcher...\n")

    print("📰 Global market news:")
    news = fetch_global_market_news(max_per_source=2, max_total=10)
    for h in news[:5]:
        print(f"  [{h['source_name']}] {h['title'][:80]}")

    print("\n📰 RELIANCE specific news:")
    stock_news = fetch_stock_news("RELIANCE")
    for h in stock_news:
        print(f"  • {h[:80]}")

    print("\n📰 Macro news:")
    macro = fetch_macro_news()
    for h in macro[:4]:
        print(f"  • {h[:80]}")

    print("\n✅ News fetcher working")