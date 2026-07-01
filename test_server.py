"""
Стресс-тесты для server.py (не запускаются в проде — только для проверки).
Не бьют по реальному 2GIS API (кроме одного явного интеграционного теста в конце,
который пропускается если TWOGIS_API_KEY не задан) — используют unittest.mock,
чтобы не жечь лимит демо-ключа при каждом прогоне.

Запуск: python3 test_server.py
"""
import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

os.environ.setdefault("TWOGIS_API_KEY", "test-key-for-import-only")

sys.path.insert(0, os.path.dirname(__file__))
import server


def fake_2gis_response(items):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {"meta": {"code": 200}, "result": {"items": items}}
    return resp


class TestFetchPlaces(unittest.TestCase):
    def setUp(self):
        server._cache.clear()

    def test_filters_low_rating(self):
        items = [
            {"id": "1", "name": "Хорошее место", "reviews": {"org_rating": 4.5, "org_review_count": 10}},
            {"id": "2", "name": "Плохое место", "reviews": {"org_rating": 3.0, "org_review_count": 5}},
        ]
        with patch("server.requests.get", return_value=fake_2gis_response(items)):
            places = server.fetch_places("999")
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["name"], "Хорошее место")

    def test_missing_rating_excluded(self):
        items = [{"id": "1", "name": "Без рейтинга", "reviews": {}}]
        with patch("server.requests.get", return_value=fake_2gis_response(items)):
            places = server.fetch_places("999")
        self.assertEqual(places, [])

    def test_uses_general_rating_fallback(self):
        items = [{"id": "1", "name": "Место", "reviews": {"general_rating": 4.2, "general_review_count": 3}}]
        with patch("server.requests.get", return_value=fake_2gis_response(items)):
            places = server.fetch_places("999")
        self.assertEqual(len(places), 1)
        self.assertEqual(places[0]["rating"], 4.2)

    def test_builds_correct_url(self):
        items = [{"id": "12345", "name": "Место", "reviews": {"org_rating": 5, "org_review_count": 1}}]
        with patch("server.requests.get", return_value=fake_2gis_response(items)):
            places = server.fetch_places("999")
        self.assertEqual(places[0]["url"], "https://2gis.ru/moscow/firm/12345")

    def test_cache_avoids_second_api_call(self):
        items = [{"id": "1", "name": "Место", "reviews": {"org_rating": 5, "org_review_count": 1}}]
        with patch("server.requests.get", return_value=fake_2gis_response(items)) as mock_get:
            server.fetch_places("999")
            server.fetch_places("999")
        self.assertEqual(mock_get.call_count, 1, "второй вызов должен был взять данные из кэша")

    def test_cache_expires_after_ttl(self):
        items = [{"id": "1", "name": "Место", "reviews": {"org_rating": 5, "org_review_count": 1}}]
        with patch("server.requests.get", return_value=fake_2gis_response(items)) as mock_get:
            server.fetch_places("999")
            server._cache["999"] = (time.time() - server.CACHE_TTL_SECONDS - 1, server._cache["999"][1])
            server.fetch_places("999")
        self.assertEqual(mock_get.call_count, 2, "после истечения TTL должен быть новый запрос")

    def test_meta_error_with_http_200_raises(self):
        """2GIS иногда шлёт ошибку с HTTP 200 и кодом внутри meta - именно этот баг
        был реально найден и исправлен при тестировании с живым ключом."""
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"meta": {"code": 400, "error": {"message": "bad param"}}, "result": {}}
        with patch("server.requests.get", return_value=resp):
            with self.assertRaises(server.requests.RequestException):
                server.fetch_places("999")

    def test_http_error_propagates(self):
        with patch("server.requests.get", side_effect=server.requests.ConnectionError("network down")):
            with self.assertRaises(server.requests.RequestException):
                server.fetch_places("999")


class TestApiEndpoint(unittest.TestCase):
    def setUp(self):
        server._cache.clear()
        server.app.config["TESTING"] = True
        self.client = server.app.test_client()

    def test_free_budget_returns_text(self):
        resp = self.client.get("/api/idea?budget=free")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["type"], "text")
        self.assertIn(data["text"], server.FREE_IDEAS)

    def test_unknown_budget_returns_400(self):
        resp = self.client.get("/api/idea?budget=luxury")
        self.assertEqual(resp.status_code, 400)

    def test_missing_budget_defaults_to_free(self):
        resp = self.client.get("/api/idea")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["type"], "text")

    def test_cheap_budget_returns_place(self):
        items = [{"id": "1", "name": "Кафе", "reviews": {"org_rating": 4.7, "org_review_count": 20}}]
        with patch("server.requests.get", return_value=fake_2gis_response(items)):
            resp = self.client.get("/api/idea?budget=cheap")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["type"], "place")
        self.assertEqual(data["place"]["name"], "Кафе")

    def test_2gis_failure_returns_502_not_crash(self):
        with patch("server.requests.get", side_effect=server.requests.ConnectionError("down")):
            resp = self.client.get("/api/idea?budget=medium")
        self.assertEqual(resp.status_code, 502)
        self.assertIn("error", resp.get_json())

    def test_empty_places_falls_back_to_text(self):
        with patch("server.requests.get", return_value=fake_2gis_response([])):
            resp = self.client.get("/api/idea?budget=cheap")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["type"], "text")

    def test_cors_header_present(self):
        resp = self.client.get("/api/idea?budget=free")
        self.assertIn("Access-Control-Allow-Origin", resp.headers)


class TestLiveIntegration(unittest.TestCase):
    """Реальный запрос к 2GIS - только если явно передан TWOGIS_API_KEY_REAL
    (отдельная переменная, чтобы не путать с заглушкой TWOGIS_API_KEY, которую
    задаёт os.environ.setdefault выше для импорта модуля). Пропускается по
    умолчанию, чтобы не тратить лимит демо-ключа при каждом прогоне тестов.

    Запуск с реальной проверкой:
        TWOGIS_API_KEY_REAL=<ключ> python3 test_server.py
    """

    @unittest.skipUnless(
        os.environ.get("TWOGIS_API_KEY_REAL"),
        "задай TWOGIS_API_KEY_REAL=<реальный ключ>, чтобы включить этот тест",
    )
    def test_real_bowling_category_has_places(self):
        server._cache.clear()
        server.TWOGIS_API_KEY = os.environ["TWOGIS_API_KEY_REAL"]
        places = server.fetch_places("170")  # боулинг
        self.assertGreater(len(places), 0)
        self.assertIn("2gis.ru/moscow/firm/", places[0]["url"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
