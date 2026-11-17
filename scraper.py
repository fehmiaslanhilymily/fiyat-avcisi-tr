import json
import os
import time
from datetime import datetime, timezone

DATA_DIR = "data"
DEALS_FILE = os.path.join(DATA_DIR, "deals.json")
HISTORY_FILE = os.path.join(DATA_DIR, "price_history.json")

PLATFORMS = [
    "Trendyol", "Hepsiburada", "Amazon TR", "N11", "Pazarama", "Teknosa"
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

def fetch_platform_candidates():
    # Buraya platform API / feed veya çerezli istek fonksiyonlarınızı bağlayabilirsiniz.
    # Örnek test verisi (sistem çalıştığında arayüzde hemen görünmesi için):
    return [
        {
            "id": "ty-1001",
            "platform": "Trendyol",
            "title": "Örnek Akıllı Robot Süpürge (Test Fırsatı)",
            "current_price": 4299.0,
            "old_price": 12999.0,
            "url": "https://www.trendyol.com"
        },
        {
            "id": "hb-2002",
            "platform": "Hepsiburada",
            "title": "Örnek Kablosuz Kulaklık ANC (Test Fırsatı)",
            "current_price": 1850.0,
            "old_price": 2499.0,
            "url": "https://www.hepsiburada.com"
        }
    ]

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
        "url": item.get("url", "#")
    }

def main():
    history = load_json(HISTORY_FILE, {})
    raw_items = fetch_platform_candidates()
    deals = []

    for item in raw_items:
        if float(item["current_price"]) < float(item.get("old_price", item["current_price"])):
            deals.append(classify_deal(item, history))
        time.sleep(0.2)

    deals.sort(key=lambda x: x["discount_pct"], reverse=True)

    output = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "total": len(deals),
        "deals": deals
    }

    save_json(HISTORY_FILE, history)
    save_json(DEALS_FILE, output)
    print(f"Güncellendi: {len(deals)} fırsat kaydedildi.")

if __name__ == "__main__":
    main()
