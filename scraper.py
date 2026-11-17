import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

DATA_DIR = "data"
DEALS_FILE = os.path.join(DATA_DIR, "deals.json")
HISTORY_FILE = os.path.join(DATA_DIR, "price_history.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Taramak istediğin kategori / indirim / arama URL'leri ve platform adları
# Bot, bu sayfalardaki ürün kartlarını ve doğrudan ürün linklerini tarar.
SCAN_SOURCES = [
    {
        "platform": "N11",
        "url": "https://www.n11.com/bilgisayar",
    },
    {
        "platform": "Pazarama",
        "url": "https://www.pazarama.com/elektronik",
    },
    {
        "platform": "Teknosa",
        "url": "https://www.teknosa.com/telefon-c-100001",
    },
]


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


def fetch_html(url, timeout=15):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        encoding = resp.headers.get_content_charset() or "utf-8"
        return raw.decode(encoding, errors="replace")


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


def extract_products_from_html(platform, base_url, html):
    """
    Sayfa içindeki ürün bağlantılarını ve fiyatlarını ayıklar.
    Her ürün için doğrudan ürün sayfasının tam URL'sini üretir.
    """
    products = []
    seen_urls = set()

    # Sayfadaki tüm <a> etiketlerini bul
    for match in re.finditer(
        r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        href, inner = match.group(1), match.group(2)
        full_url = urllib.parse.urljoin(base_url, href.strip())

        # Sadece ürün detay sayfasına benzeyen URL'leri al
        if not any(k in full_url.lower() for k in ["-p-", "/p/", "/urun/", "dp/", "pd/"]):
            continue
        if full_url in seen_urls:
            continue

        clean_text = re.sub(r"<[^>]+>", " ", inner)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        if len(clean_text) < 8:
            continue

        # Kart çevresindeki fiyat ifadelerini ara
        start = max(0, match.start() - 400)
        end = min(len(html), match.end() + 400)
        window = re.sub(r"<[^>]+>", " ", html[start:end])
        window = re.sub(r"\s+", " ", window)

        price_matches = re.findall(r"(\d{1,3}(?:\.\d{3})*,\d{2})\s*₺?", window)
        prices = [parse_price_tr(p) for p in price_matches]
        prices = [p for p in prices if p is not None]

        if len(prices) >= 2:
            prices_sorted = sorted(set(prices))
            current_price = prices_sorted[0]
            old_price = prices_sorted[-1]
            if current_price < old_price:
                seen_urls.add(full_url)
                products.append({
                    "id": f"{platform.lower()}-{abs(hash(full_url))}",
                    "platform": platform,
                    "title": clean_text[:120],
                    "current_price": current_price,
                    "old_price": old_price,
                    "url": full_url,
                })

    return products


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
    all_deals = []

    for source in SCAN_SOURCES:
        platform = source["platform"]
        url = source["url"]
        try:
            html = fetch_html(url)
            candidates = extract_products_from_html(platform, url, html)
            for item in candidates:
                all_deals.append(classify_deal(item, history))
            print(f"{platform}: {len(candidates)} indirimli ürün bulundu.")
        except Exception as e:
            print(f"{platform} taranamadı: {e}")
        time.sleep(1)

    # Sadece gerçek indirimli ürünleri tut
    all_deals = [d for d in all_deals if d["discount_pct"] > 0]
    all_deals.sort(key=lambda x: x["discount_pct"], reverse=True)

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "total": len(all_deals),
        "deals": all_deals,
    }

    save_json(HISTORY_FILE, history)
    save_json(DEALS_FILE, output)
    print(f"Toplam {len(all_deals)} fırsat kaydedildi.")


if __name__ == "__main__":
    main()
