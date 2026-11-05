from backend.revenue.subscriptions import HUB_PLAN_FEATURES


def test_smart_ai_plus_gets_phase_one_productivity_entitlements():
    features = HUB_PLAN_FEATURES["smart_ai"]["ai_plus"]
    assert {"advanced_ai", "document_analysis", "advanced_reports"} <= features
    assert "advanced_analytics" not in features
    assert "automation" not in features


def test_smart_ai_pro_gets_advanced_productivity_entitlements():
    features = HUB_PLAN_FEATURES["smart_ai"]["ai_pro"]
    assert {
        "advanced_ai",
        "document_analysis",
        "advanced_reports",
        "advanced_analytics",
        "automation",
        "expanded_history",
        "image_generation",
        "voice_generation",
        "vision_analysis",
    } <= features
