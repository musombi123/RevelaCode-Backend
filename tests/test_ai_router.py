from backend.services import ai_router


def test_ask_ai_uses_revelaai_native_ai_endpoint_contract(monkeypatch):
    captured = {}

    class Response:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "success", "data": {"content": "Soil guidance"}}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(ai_router, "REVELA_AI_URL", "https://ai.example.test/ai")
    monkeypatch.setattr(ai_router.requests, "post", fake_post)

    result = ai_router.ask_ai(
        "What should I do next?",
        domain="shamba",
        context={"farm": {"county": "Busia"}},
    )

    assert result["data"]["content"] == "Soil guidance"
    assert captured["url"] == "https://ai.example.test/ai"
    assert captured["json"]["message"] == "What should I do next?"
    assert captured["json"]["hub"] == "shamba"
    assert captured["json"]["context"][0]["role"] == "system"
    assert "Busia" in captured["json"]["context"][0]["content"]


def test_ask_ai_has_a_production_revelaai_default():
    assert ai_router.DEFAULT_REVELAAI_URL == "https://revelaai.onrender.com/ai"
    assert ai_router.REVELA_AI_URL
