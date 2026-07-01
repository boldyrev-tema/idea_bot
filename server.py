import os
import random
import time

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

# ── настройки ──────────────────────────────────────────────────────────────────
TWOGIS_API_KEY = os.environ["TWOGIS_API_KEY"]
MOSCOW_CITY_ID = "4504222397630173"
CATALOG_URL = "https://catalog.api.2gis.ru/3.0/items"
CACHE_TTL_SECONDS = 3600  # кэш на категорию, чтобы не жечь лимит демо-ключа (1000 запросов)

app = Flask(__name__)
CORS(app)

# rubric_id найдены эмпирически через Categories API 2GIS (см. pm_learning.md /
# план — сделан разовый разведочный запрос по каждой категории)
CATEGORIES = {
    "cheap": [
        {"rubric_id": "162", "label": "Кофейня"},
        {"rubric_id": "170", "label": "Боулинг"},
        {"rubric_id": "169", "label": "Бильярд"},
        {"rubric_id": "11974", "label": "Каток"},
    ],
    "medium": [
        {"rubric_id": "192", "label": "Кино"},
        {"rubric_id": "537", "label": "Аквапарк"},
        {"rubric_id": "110300", "label": "Квест"},
        {"rubric_id": "21387", "label": "Караоке"},
        {"rubric_id": "516", "label": "Мастер-класс"},
    ],
}

FREE_IDEAS = [
    "Устроить пикник в парке — еда вскладчину, каждый несёт что-то своё",
    "Сходить в музей в день бесплатного входа (уточните афишу города)",
    "Вечер настолок дома — каждый приносит свою любимую игру",
    "Прогуляться по району города, где никто из вас толком не был",
    "Киновечер дома с самодельным попкорном",
    "Покататься на роликах, самокатах или велосипедах в парке (свои)",
    "Фотопрогулка — искать необычные ракурсы города, потом сравнить кадры",
    "Заглянуть на бесплатную городскую ярмарку или выставку",
    "Вечер игр в стиле «Правда или действие» / «20 вопросов»",
    "Посидеть в библиотеке, почитать вместе, обсудить прочитанное",
    "Устроить своп — каждый приносит ненужные вещи, остальные выбирают",
    "Сходить на набережную или смотровую площадку встретить закат",
]

_cache = {}  # rubric_id -> (timestamp, [places])


def fetch_places(rubric_id):
    now = time.time()
    cached = _cache.get(rubric_id)
    if cached and now - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    resp = requests.get(
        CATALOG_URL,
        params={
            "rubric_id": rubric_id,
            "city_id": MOSCOW_CITY_ID,
            "sort": "rating",
            "fields": "items.reviews,items.point,items.address_name",
            "page_size": 10,  # максимум для демо-ключа 2GIS
            "key": TWOGIS_API_KEY,
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    # 2GIS иногда возвращает ошибку с HTTP 200 и кодом внутри meta — raise_for_status() это не ловит
    if data.get("meta", {}).get("code") != 200:
        raise requests.RequestException(f"2GIS API error: {data.get('meta', {}).get('error')}")
    items = data.get("result", {}).get("items", [])

    places = []
    for item in items:
        reviews = item.get("reviews") or {}
        rating = reviews.get("org_rating") or reviews.get("general_rating")
        if not rating or rating < 4.0:
            continue
        places.append({
            "id": item["id"],
            "name": item.get("name", "Без названия"),
            "address": item.get("address_name", ""),
            "rating": rating,
            "review_count": reviews.get("org_review_count") or reviews.get("general_review_count") or 0,
            "url": f"https://2gis.ru/moscow/firm/{item['id']}",
        })

    _cache[rubric_id] = (now, places)
    return places


# ── /api/idea ──────────────────────────────────────────────────────────────────
@app.route("/api/idea")
def get_idea():
    budget = request.args.get("budget", "free")

    if budget == "free":
        return jsonify({"type": "text", "budget": budget, "text": random.choice(FREE_IDEAS)})

    categories = CATEGORIES.get(budget)
    if not categories:
        return jsonify({"error": "unknown budget"}), 400

    category = random.choice(categories)
    try:
        places = fetch_places(category["rubric_id"])
    except requests.RequestException as e:
        return jsonify({"error": "2gis request failed", "detail": str(e)}), 502

    if not places:
        return jsonify({
            "type": "text",
            "budget": budget,
            "text": f"{category['label']} — не нашлось мест с хорошим рейтингом, попробуй ещё раз",
        })

    place = random.choice(places)
    return jsonify({
        "type": "place",
        "budget": budget,
        "category": category["label"],
        "place": place,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
