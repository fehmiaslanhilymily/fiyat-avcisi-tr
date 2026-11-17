import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone

DATA_DIR = "data"
DEALS_FILE = os.path.join(DATA_DIR, "deals.json")
HISTORY_FILE = os.path.join(DATA_DIR, "price_history.json")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except Exception:
                return default
    return default


def save_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def is_url_alive(url):
    """404 veya kırık sayfa dönen linkleri elemek için kontrol eder."""
    if not url or not url.startswith("http"):
        return False
    try:
        req = urllib.request.Request(url, headers=HEADERS, method="HEAD")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def parse_price_tr(text):
    if not text:
        return None
    cleaned = re.sub(r"[^\d,\.]", "", str(text))
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


def fetch_product_page_price(url):
    """Gerçek ürün sayfasından başlık ve güncel fiyat çekmeyi dener."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw = resp.read()
            encoding = resp.headers.get_content_charset() or "utf-8"
            html = raw.decode(encoding, errors="replace")

        title_match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.I | re.S)
        title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""

        price_matches = re.findall(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*₺", html)
        prices = [p for p in (parse_price_tr(x) for x in price_matches) if p is not None]
        if prices:
            return title[:120], min(prices), max(prices)
    except Exception:
        pass
    return None, None, None


def classify_deal(item, history):
    current = float(item["current_price"])
    old = float(item.get("old_price") or current)
    prev_prices = history.get(item["id"], [])
    avg_price = (sum(prev_prices) / len(prev_prices)) if prev_prices else old

    discount_pct = round(((avg_price - current) / avg_price) * 100, 1) if avg_price > 0 else 0
    is_error_price = discount_pct >= 60.0

    prev_prices.append(current)
    history[item["id"]] = prev_prices[-15:]

    return {
        "id": item["id"],
        "platform": item["platform"],
        "title": item["title"],
        "current_price": current,
        "old_price": old,
        "avg_price": round(avg_price, 2),
        "discount_pct": max(discount_pct, 0),
        "deal_type": "ERROR_PRICE" if is_error_price else "NORMAL_DEAL",
        "url": item["url"],
    }


def main():
    history = load_json(HISTORY_FILE, {})
    watchlist = load_json(WATCHLIST_FILE, [])
    deals = []

    for item in watchlist:
        url = item.get("url", "")
        if not url.startswith("http"):
            continue

        live_title, live_min, live_max = fetch_product_page_price(url)
        current_price = float(live_min if live_min else item.get("current_price", 100))
        old_price = float(live_max if (live_max and live_max > current_price) else item.get("old_price", current_price * 1.5))

        if old_price <= current_price:
            old_price = round(current_price * 1.35, 2)

        title = (live_title.strip() if live_title else "") or item.get("title", "İndirimli Ürün")

        enriched = {
            "id": item["id"],
            "platform": item["platform"],
            "title": title[:120],
            "current_price": current_price,
            "old_price": old_price,
            "url": url,
        }
        deals.append(classify_deal(enriched, history))
        time.sleep(0.5)

    deals.sort(key=lambda x: x["discount_pct"], reverse=True)

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "total": len(deals),
        "deals": deals,
    }

    save_json(HISTORY_FILE, history)
    save_json(DEALS_FILE, output)
    print(f"Kaydedilen fırsat sayısı: {len(deals)}")
