# backend/jumuiya/community/policy.py
"""
Jumuiya Community — policy and decision engine.

This module intentionally contains NO database operations.

Its responsibility is to answer questions such as:

    - Is this Community content structurally valid?
    - What actions make sense for this content?
    - Can this content participate in Pulse?
    - How relevant is this content to a particular user?
    - How much should trust, usefulness, locality and freshness matter?
    - Which Community capabilities should be exposed to a user?

Community is NOT designed around:
    "most likes = most important"

Instead, Community favors:
    relevance
    usefulness
    actionability
    freshness
    trust
    local context
    meaningful participation

The actual persistence/query layer remains in services.py.
Discovery/ranking orchestration belongs in discovery.py.
"""


from __future__ import annotations

from datetime import datetime, timezone
from math import exp, log1p
from typing import Any, Mapping

from backend.jumuiya.core.errors import APIError

from .constants import (
    ACTIONABLE_POST_TYPES,
    ACTION_TYPES,
    ACTION_TYPE_SET,
    ALLOWED_ACTION_TARGET_SCHEMES,
    ALLOWED_INTERNAL_TARGET_PREFIXES,
    ALLOW_RELATIVE_ACTION_TARGETS,
    COMMUNITY_CATEGORIES,
    DISCOVERABLE_HUBS,
    DISCOVERY_INTENTS,
    DISCUSSION_POST_TYPES,
    GROUP_TYPES,
    GROUP_TYPE_SET,
    GROUP_VISIBILITIES,
    HUB_SET,
    POST_TYPES,
    POST_TYPE_SET,
    REPUTATION_NEGATIVE_SIGNALS,
    REPUTATION_SIGNALS,
    SORT_ACTIONABLE,
    SORT_DISCOVERY,
    SORT_MODES,
    SORT_NEARBY,
    SORT_RECENT,
    SORT_RELEVANT,
    SORT_TRUSTED,
    SOURCE_ENTITY_TYPES,
    SOURCE_ENTITY_TYPE_SET,
    SOURCE_HUBS,
    SOURCE_HUB_SET,
    THREAD_STATES,
    THREAD_TYPES,
    THREAD_TYPE_SET,
    TRUST_LEVELS,
    TRUST_LEVEL_SET,
    VISIBILITY_PRIVATE,
    VISIBILITY_PUBLIC,
    VISIBILITY_SET,
)


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _text(value: Any) -> str:
    """
    Convert an arbitrary value into a safe, trimmed string for policy checks.

    Policy never mutates the original payload.
    """
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    return str(value).strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _number(value: Any, default: float = 0.0) -> float:
    """
    Safely coerce numeric policy inputs.

    Policy must not crash because a client supplied a malformed metric.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if number < 0:
        return default

    return number


def _bounded(value: Any, minimum: float = 0.0, maximum: float = 1.0) -> float:
    """
    Normalize a numeric value into [minimum, maximum].
    """
    value = _number(value, minimum)

    if value < minimum:
        return minimum

    if value > maximum:
        return maximum

    return value


def _as_set(value: Any) -> set[str]:
    """
    Normalize tags/interests/categories into a set of lowercase strings.
    """
    if value is None:
        return set()

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, (list, tuple, set, frozenset)):
        return set()

    result: set[str] = set()

    for item in value:
        item = _lower(item)
        if item:
            result.add(item)

    return result


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _datetime(value: Any) -> datetime | None:
    """
    Normalize datetime-like values used by freshness calculations.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)

        return value.astimezone(timezone.utc)

    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed.astimezone(timezone.utc)
        except ValueError:
            return None

    return None


def _first_non_empty(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}, ()):
            return value

    return None


# ============================================================================
# STRUCTURAL POLICY
# ============================================================================


def validate_hub(hub: Any) -> str:
    """
    Validate a Community source hub.

    Ownership/access checks remain in services.py because they require DB
    state. This function only validates the vocabulary.
    """
    value = _lower(hub)

    if value not in HUB_SET:
        raise APIError(
            "Unsupported Community hub.",
            400,
            "invalid_hub",
        )

    return value


def validate_post_type(post_type: Any) -> str:
    value = _lower(post_type)

    if value not in POST_TYPE_SET:
        raise APIError(
            "Unsupported Community post type.",
            400,
            "invalid_post_type",
        )

    return value


def validate_visibility(visibility: Any) -> str:
    value = _lower(visibility)

    if value not in VISIBILITY_SET:
        raise APIError(
            "Unsupported Community visibility.",
            400,
            "invalid_visibility",
        )

    return value


def validate_category(category: Any) -> str:
    value = _lower(category)

    if not value:
        return ""

    if value not in {item.lower() for item in COMMUNITY_CATEGORIES}:
        raise APIError(
            "Unsupported Community category.",
            400,
            "invalid_category",
        )

    return value


def validate_sort_mode(sort_mode: Any) -> str:
    value = _lower(sort_mode)

    if not value:
        return SORT_RELEVANT

    if value not in SORT_MODES:
        raise APIError(
            "Unsupported Community sorting mode.",
            400,
            "invalid_sort_mode",
        )

    return value


# ============================================================================
# CONTENT POLICY
# ============================================================================


def validate_post_shape(payload: Mapping[str, Any]) -> dict[str, Any]:
    """
    Validate policy-level post fields.

    This intentionally does not replace services.py validation.

    It creates a normalized policy representation that services.py can use
    before persistence.
    """
    if not isinstance(payload, Mapping):
        raise APIError(
            "Community payload must be an object.",
            400,
            "invalid_payload",
        )

    normalized: dict[str, Any] = dict(payload)

    post_type = _first_non_empty(payload, "type", "post_type")

    if post_type is not None:
        normalized["type"] = validate_post_type(post_type)

    hub = payload.get("hub")

    if hub is not None:
        normalized["hub"] = validate_hub(hub)

    visibility = payload.get("visibility")

    if visibility is not None:
        normalized["visibility"] = validate_visibility(visibility)

    category = payload.get("category")

    if category is not None:
        normalized["category"] = validate_category(category)

    return normalized


def is_actionable_post(post: Mapping[str, Any]) -> bool:
    """
    Whether this content represents something a user can meaningfully act on.
    """
    post_type = _lower(
        _first_non_empty(post, "type", "post_type")
    )

    return post_type in {value.lower() for value in ACTIONABLE_POST_TYPES}


def is_discussion_post(post: Mapping[str, Any]) -> bool:
    """
    Whether this content naturally supports structured conversation.
    """
    post_type = _lower(
        _first_non_empty(post, "type", "post_type")
    )

    return post_type in {value.lower() for value in DISCUSSION_POST_TYPES}


def is_question_post(post: Mapping[str, Any]) -> bool:
    return _lower(
        _first_non_empty(post, "type", "post_type")
    ) == "question"


def is_help_request(post: Mapping[str, Any]) -> bool:
    return _lower(
        _first_non_empty(post, "type", "post_type")
    ) == "help_request"


def is_opportunity_post(post: Mapping[str, Any]) -> bool:
    return _lower(
        _first_non_empty(post, "type", "post_type")
    ) == "opportunity"


# ============================================================================
# ACTION POLICY
# ============================================================================


def validate_action(action: Any) -> dict[str, Any] | None:
    """
    Validate a post action without making database decisions.

    Supported shape:

        {
            "type": "apply",
            "label": "Apply now",
            "target": "/community/..."
        }

    The target policy rejects dangerous URL schemes and permits internal
    relative paths. Absolute HTTPS URLs may also be permitted.

    The returned object is a new dict; the caller's original action is not
    mutated.
    """
    if action in (None, ""):
        return None

    if not isinstance(action, Mapping):
        raise APIError(
            "Community action must be an object.",
            400,
            "invalid_action",
        )

    action_type = _lower(action.get("type"))
    label = _text(action.get("label"))
    target = _text(action.get("target"))

    if action_type not in ACTION_TYPE_SET:
        raise APIError(
            "Unsupported Community action.",
            400,
            "invalid_action_type",
        )

    if not label:
        raise APIError(
            "Community action requires a label.",
            400,
            "invalid_action_label",
        )

    if len(label) > 80:
        raise APIError(
            "Community action label is too long.",
            400,
            "invalid_action_label",
        )

    validate_action_target(target)

    return {
        "type": action_type,
        "label": label,
        "target": target,
    }


def validate_action_target(target: Any) -> str:
    """
    Validate an action destination.

    Dangerous schemes such as javascript:, data:, file:, and vbscript:
    are deliberately rejected.

    Internal relative paths are preferred.

    Absolute targets are restricted to HTTPS.
    """
    value = _text(target)

    if not value:
        raise APIError(
            "Community action requires a target.",
            400,
            "invalid_action_target",
        )

    lowered = value.lower()

    # Never allow control characters in navigation targets.
    if any(ord(char) < 32 for char in value):
        raise APIError(
            "Community action target contains invalid characters.",
            400,
            "invalid_action_target",
        )

    # Explicitly reject known dangerous URL schemes.
    dangerous_prefixes = (
        "javascript:",
        "data:",
        "vbscript:",
        "file:",
        "about:",
    )

    if lowered.startswith(dangerous_prefixes):
        raise APIError(
            "Unsupported Community action target.",
            400,
            "invalid_action_target",
        )

    if value.startswith("/"):
        if not ALLOW_RELATIVE_ACTION_TARGETS:
            raise APIError(
            "Relative Community action targets are disabled.",
            400,
            "invalid_action_target",
        )

        # Reject protocol-relative URLs such as //evil.example.
        if value.startswith("//"):
            raise APIError(
            "Protocol-relative action targets are not allowed.",
            400,
            "invalid_action_target",
        )

        # Internal application paths are safest. We still allow a normal
        # relative path so long as it is rooted in the application.
        if not value.startswith(ALLOWED_INTERNAL_TARGET_PREFIXES):
            raise APIError(
            "Community action target is outside the application.",
            400,
            "invalid_action_target",
        )

        return value

    # Anything containing a scheme should be HTTPS.
    if ":" in value:
        if not lowered.startswith("https://"):
            raise APIError(
            "Only HTTPS external Community action targets are allowed.",
            400,
            "invalid_action_target",
        )

        return value

    # Bare external domains / hostnames are ambiguous and can become
    # open-redirect vectors. Force explicit https://.
    raise APIError(
            "External Community targets must use HTTPS.",
            400,
            "invalid_action_target",
        )


def allowed_actions_for_post(post: Mapping[str, Any]) -> tuple[str, ...]:
    """
    Return the actions that make semantic sense for a piece of content.

    This is deliberately more expressive than "like/comment/share".
    """
    post_type = _lower(
        _first_non_empty(post, "type", "post_type")
    )

    if post_type == "opportunity":
        return (
            "apply",
            "respond",
            "enquire",
            "save",
            "follow",
            "report",
        )

    if post_type == "offer":
        return (
            "enquire",
            "buy",
            "respond",
            "save",
            "follow",
            "report",
        )

    if post_type == "request":
        return (
            "respond",
            "help",
            "enquire",
            "save",
            "follow",
            "report",
        )

    if post_type == "event":
        return (
            "attend",
            "enquire",
            "save",
            "follow",
            "report",
        )

    if post_type == "help_request":
        return (
            "help",
            "respond",
            "enquire",
            "save",
            "follow",
            "report",
        )

    if post_type == "project":
        return (
            "join",
            "respond",
            "enquire",
            "support",
            "save",
            "follow",
            "report",
        )

    if post_type == "question":
        return (
            "respond",
            "save",
            "follow",
            "report",
        )

    if post_type == "resource":
        return (
            "save",
            "follow",
            "report",
        )

    # Generic Community content.
    return (
        "respond",
        "save",
        "follow",
        "report",
    )


def action_is_allowed_for_post(
    post: Mapping[str, Any],
    action_type: Any,
) -> bool:
    value = _lower(action_type)

    return value in {
        item.lower()
        for item in allowed_actions_for_post(post)
    }


# ============================================================================
# VISIBILITY POLICY
# ============================================================================


def visibility_allows(
    post: Mapping[str, Any],
    *,
    authenticated: bool,
    is_owner: bool = False,
    is_group_member: bool = False,
) -> bool:
    """
    Decide whether a viewer may see a post.

    Ownership/access to source entities must still be established by the
    service layer.

    This function handles Community visibility semantics only.
    """
    visibility = _lower(post.get("visibility")) or VISIBILITY_PUBLIC

    if visibility == VISIBILITY_PUBLIC:
        return True

    if not authenticated:
        return False

    if visibility == "community":
        return True

    if visibility == "group":
        return is_group_member or is_owner

    if visibility == VISIBILITY_PRIVATE:
        return is_owner

    return False


# ============================================================================
# SOURCE POLICY
# ============================================================================


def source_is_supported(source: Any) -> bool:
    """
    Policy-level source vocabulary check.

    Ownership and actual entity existence belong to services.py.
    """
    if source in (None, ""):
        return True

    if not isinstance(source, Mapping):
        return False

    hub = _lower(source.get("hub"))
    entity_type = _lower(
        _first_non_empty(source, "type", "entity_type")
    )

    return (
        hub in SOURCE_HUB_SET
        and entity_type in SOURCE_ENTITY_TYPE_SET
    )


def validate_source_shape(source: Any) -> dict[str, Any] | None:
    """
    Validate the structure of a cross-hub source reference.

    This does NOT establish ownership. services.py must still verify that
    the authenticated user owns or can reference the entity.
    """
    if source in (None, ""):
        return None

    if not isinstance(source, Mapping):
        raise APIError(
            "Community source must be an object.",
            400,
            "invalid_source",
        )

    hub = _lower(source.get("hub"))
    entity_type = _lower(
        _first_non_empty(source, "type", "entity_type")
    )
    entity_id = _text(
        _first_non_empty(source, "id", "entity_id")
    )

    if hub not in SOURCE_HUB_SET:
        raise APIError(
            "Unsupported Community source hub.",
            400,
            "invalid_source_hub",
        )

    if entity_type not in SOURCE_ENTITY_TYPE_SET:
        raise APIError(
            "Unsupported Community source type.",
            400,
            "invalid_source_type",
        )

    if not entity_id:
        raise APIError(
            "Community source requires an entity id.",
            400,
            "invalid_source_id",
        )

    # Prevent obviously absurd IDs from creating pathological requests.
    if len(entity_id) > 128:
        raise APIError(
            "Community source id is too long.",
            400,
            "invalid_source_id",
        )

    return {
        "hub": hub,
        "type": entity_type,
        "id": entity_id,
    }


# ============================================================================
# TRUST POLICY
# ============================================================================


def normalize_trust_level(value: Any) -> str:
    level = _lower(value)

    if level not in TRUST_LEVEL_SET:
        return "unknown"

    return level


def trust_level_score(value: Any) -> float:
    """
    Convert trust level into a bounded policy signal.

    Trust is a multiplier, not a replacement for relevance.
    """
    level = normalize_trust_level(value)

    scores = {
        "unknown": 0.20,
        "basic": 0.40,
        "established": 0.65,
        "trusted": 0.85,
        "verified": 1.00,
    }

    return scores[level]


def reputation_score(profile: Mapping[str, Any] | None) -> float:
    """
    Produce a conservative reputation signal.

    The client cannot directly provide this as authority. Discovery should
    obtain it from trusted backend state.
    """
    if not isinstance(profile, Mapping):
        return 0.20

    positive = 0.0

    for signal in REPUTATION_SIGNALS:
        positive += _number(profile.get(signal), 0.0)

    negative = 0.0

    for signal in REPUTATION_NEGATIVE_SIGNALS:
        negative += _number(profile.get(signal), 0.0)

    # log1p prevents a very active account from becoming disproportionately
    # powerful just because it has large raw counts.
    positive_score = min(1.0, log1p(positive) / 8.0)
    negative_penalty = min(0.75, log1p(negative) / 6.0)

    return _bounded(
        0.20 + (positive_score * 0.80) - negative_penalty,
        0.0,
        1.0,
    )


def trust_score(
    *,
    profile: Mapping[str, Any] | None = None,
    trust_level: Any = None,
) -> float:
    """
    Combine explicit trust level and reputation into one bounded signal.
    """
    level_score = trust_level_score(trust_level)

    profile_score = reputation_score(profile)

    return _bounded(
        (level_score * 0.60) + (profile_score * 0.40)
    )


# ============================================================================
# RELEVANCE POLICY
# ============================================================================


def set_overlap_score(
    left: Any,
    right: Any,
) -> float:
    """
    Compute normalized overlap for interests, tags, categories or topics.
    """
    left_set = _as_set(left)
    right_set = _as_set(right)

    if not left_set or not right_set:
        return 0.0

    intersection = left_set.intersection(right_set)

    return _bounded(
        len(intersection) / max(1, len(left_set))
    )


def topic_relevance_score(
    post: Mapping[str, Any],
    user_context: Mapping[str, Any] | None = None,
) -> float:
    """
    Measure semantic-context overlap using fields that may already exist in
    Jumuiya profiles.

    Supported user context examples:

        {
            "interests": [...],
            "categories": [...],
            "hubs": [...],
            "topics": [...]
        }
    """
    if not isinstance(user_context, Mapping):
        return 0.0

    post_values: set[str] = set()

    post_values.update(_as_set(post.get("tags")))

    category = _lower(post.get("category"))
    if category:
        post_values.add(category)

    post_type = _lower(
        _first_non_empty(post, "type", "post_type")
    )
    if post_type:
        post_values.add(post_type)

    if not post_values:
        return 0.0

    user_values: set[str] = set()

    for key in (
        "interests",
        "categories",
        "topics",
        "preferred_categories",
        "skills",
    ):
        user_values.update(_as_set(user_context.get(key)))

    return set_overlap_score(post_values, user_values)


def hub_relevance_score(
    post: Mapping[str, Any],
    user_context: Mapping[str, Any] | None = None,
) -> float:
    if not isinstance(user_context, Mapping):
        return 0.0

    post_hub = _lower(post.get("hub"))

    if not post_hub:
        return 0.0

    user_hubs = _as_set(
        _first_non_empty(
            user_context,
            "hubs",
            "preferred_hubs",
            "active_hubs",
        )
    )

    if not user_hubs:
        return 0.0

    return 1.0 if post_hub in user_hubs else 0.0


def location_relevance_score(
    post: Mapping[str, Any],
    user_context: Mapping[str, Any] | None = None,
) -> float:
    """
    Conservative location matching.

    Exact coordinates/location intelligence can later be supplied by
    discovery.py. This policy layer supports broad geographic context now.
    """
    if not isinstance(user_context, Mapping):
        return 0.0

    post_location = _lower(
        _first_non_empty(
            post,
            "location",
            "town",
            "county",
            "area",
        )
    )

    user_location = _lower(
        _first_non_empty(
            user_context,
            "location",
            "town",
            "county",
            "area",
        )
    )

    if not post_location or not user_location:
        return 0.0

    if post_location == user_location:
        return 1.0

    # Broad geographic containment is useful for values such as:
    # "Mombasa" vs "Mombasa, Kenya".
    if (
        post_location in user_location
        or user_location in post_location
    ):
        return 0.75

    return 0.0


# ============================================================================
# FRESHNESS POLICY
# ============================================================================


def freshness_score(
    post: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> float:
    """
    Convert content age into a 0..1 freshness score.

    Freshness decays smoothly instead of disappearing abruptly.
    """
    created_at = _datetime(
        _first_non_empty(
            post,
            "created_at",
            "published_at",
            "updated_at",
        )
    )

    if created_at is None:
        return 0.20

    reference = now or _now()

    age_seconds = max(
        0.0,
        (reference - created_at).total_seconds(),
    )

    age_hours = age_seconds / 3600.0

    # Half-life is approximately 48 hours.
    decay = exp(-age_hours / 69.25)

    return _bounded(decay)


# ============================================================================
# USEFULNESS / ACTIONABILITY POLICY
# ============================================================================


def actionability_score(post: Mapping[str, Any]) -> float:
    """
    Estimate whether the content can move someone toward a real-world action.
    """
    score = 0.0

    if is_actionable_post(post):
        score += 0.50

    if post.get("action"):
        score += 0.30

    if post.get("source"):
        score += 0.10

    if post.get("location"):
        score += 0.05

    if post.get("category"):
        score += 0.05

    return _bounded(score)


def completeness_score(post: Mapping[str, Any]) -> float:
    """
    Reward useful, understandable content without requiring every optional
    field.
    """
    score = 0.0

    title = _text(post.get("title"))
    body = _text(post.get("body"))
    category = _text(post.get("category"))
    tags = _as_set(post.get("tags"))
    location = _text(post.get("location"))
    source = post.get("source")
    action = post.get("action")

    if title:
        score += 0.15

    if len(body) >= 80:
        score += 0.25
    elif len(body) >= 20:
        score += 0.15
    elif body:
        score += 0.05

    if category:
        score += 0.15

    if tags:
        score += 0.10

    if location:
        score += 0.10

    if source:
        score += 0.10

    if action:
        score += 0.15

    return _bounded(score)


def quality_score(post: Mapping[str, Any]) -> float:
    """
    Content quality signal.

    This deliberately avoids making engagement the main quality indicator.
    """
    return _bounded(
        (completeness_score(post) * 0.55)
        + (actionability_score(post) * 0.30)
        + (1.0 if is_discussion_post(post) else 0.0) * 0.15
    )


# ============================================================================
# ENGAGEMENT POLICY
# ============================================================================


def engagement_score(post: Mapping[str, Any]) -> float:
    """
    Convert raw engagement into a bounded signal.

    Engagement is intentionally logarithmic and low-weighted.

    10,000 likes should NOT automatically bury a highly relevant but new
    opportunity with 5 useful interactions.
    """
    likes = _number(
        _first_non_empty(post, "likes_count", "reactions_count"),
        0.0,
    )
    comments = _number(post.get("comments_count"), 0.0)

    # Comments are slightly more meaningful than passive reactions.
    weighted_interactions = likes + (comments * 1.75)

    return _bounded(
        log1p(weighted_interactions) / log1p(500.0)
    )


# ============================================================================
# LOCALITY / PERSONALIZATION POLICY
# ============================================================================


def personalization_score(
    post: Mapping[str, Any],
    user_context: Mapping[str, Any] | None = None,
) -> float:
    """
    Combine user context into a single relevance signal.
    """
    if not isinstance(user_context, Mapping):
        return 0.0

    topic = topic_relevance_score(post, user_context)
    hub = hub_relevance_score(post, user_context)
    location = location_relevance_score(post, user_context)

    return _bounded(
        (topic * 0.50)
        + (hub * 0.20)
        + (location * 0.30)
    )


# ============================================================================
# PULSE POLICY
# ============================================================================


def pulse_score(
    post: Mapping[str, Any],
    *,
    user_context: Mapping[str, Any] | None = None,
    author_profile: Mapping[str, Any] | None = None,
    author_trust_level: Any = None,
    now: datetime | None = None,
) -> float:
    """
    Calculate the primary Community Pulse score.

    The weighting is intentional:

        personalization   30%
        usefulness        20%
        freshness         15%
        trust             15%
        locality          10%
        actionability      5%
        engagement         5%

    This creates a feed that asks:

        "Why is this useful to THIS person?"

    instead of:

        "How many people already clicked it?"
    """
    personalization = personalization_score(
        post,
        user_context,
    )

    usefulness = quality_score(post)

    freshness = freshness_score(
        post,
        now=now,
    )

    trust = trust_score(
        profile=author_profile,
        trust_level=author_trust_level,
    )

    locality = location_relevance_score(
        post,
        user_context,
    )

    actionability = actionability_score(post)

    engagement = engagement_score(post)

    score = (
        personalization * 0.30
        + usefulness * 0.20
        + freshness * 0.15
        + trust * 0.15
        + locality * 0.10
        + actionability * 0.05
        + engagement * 0.05
    )

    return round(_bounded(score) * 100.0, 4)


def should_surface_in_pulse(
    post: Mapping[str, Any],
    *,
    user_context: Mapping[str, Any] | None = None,
) -> bool:
    """
    Decide whether content has enough value to enter Pulse.

    We intentionally do not require high engagement.
    """
    state = _lower(post.get("status"))

    if state in {"deleted", "hidden", "archived"}:
        return False

    visibility = _lower(post.get("visibility")) or VISIBILITY_PUBLIC

    if visibility == VISIBILITY_PRIVATE:
        return False

    score = pulse_score(
        post,
        user_context=user_context,
    )

    # Content with a meaningful action, question or help request can surface
    # at a lower score because usefulness may matter more than popularity.
    if (
        is_actionable_post(post)
        or is_question_post(post)
        or is_help_request(post)
    ):
        return score >= 22.0

    return score >= 30.0


# ============================================================================
# DISCOVERY POLICY
# ============================================================================


def discovery_score(
    item: Mapping[str, Any],
    *,
    user_context: Mapping[str, Any] | None = None,
    trust: float | None = None,
    now: datetime | None = None,
) -> float:
    """
    Generic discovery score.

    Discovery can rank people, businesses, farms, schools, products,
    opportunities, groups, threads or resources.

    Unlike Pulse, Discovery is intentionally entity-oriented.
    """
    personalization = personalization_score(
        item,
        user_context,
    )

    freshness = freshness_score(
        item,
        now=now,
    )

    quality = quality_score(item)

    trust_value = (
        _bounded(trust)
        if trust is not None
        else trust_score(
            profile=item.get("author_profile")
            if isinstance(item.get("author_profile"), Mapping)
            else None,
            trust_level=item.get("trust_level"),
        )
    )

    actionability = actionability_score(item)

    engagement = engagement_score(item)

    score = (
        personalization * 0.30
        + quality * 0.20
        + trust_value * 0.20
        + freshness * 0.10
        + actionability * 0.15
        + engagement * 0.05
    )

    return round(_bounded(score) * 100.0, 4)


# ============================================================================
# FEED MODE POLICY
# ============================================================================


def mode_score(
    post: Mapping[str, Any],
    *,
    mode: Any,
    user_context: Mapping[str, Any] | None = None,
) -> float:
    """
    Calculate score for a specific Pulse/discovery viewing mode.
    """
    normalized_mode = validate_sort_mode(mode)

    base = pulse_score(
        post,
        user_context=user_context,
    )

    if normalized_mode == SORT_RELEVANT:
        return base

    if normalized_mode == SORT_RECENT:
        return freshness_score(post) * 100.0

    if normalized_mode == SORT_NEARBY:
        locality = location_relevance_score(
            post,
            user_context,
        )

        return (
            locality * 70.0
            + freshness_score(post) * 20.0
            + actionability_score(post) * 10.0
        )

    if normalized_mode == SORT_ACTIONABLE:
        return (
            actionability_score(post) * 60.0
            + personalization_score(post, user_context) * 25.0
            + freshness_score(post) * 15.0
        ) * 100.0

    if normalized_mode == SORT_TRUSTED:
        return (
            trust_score(
                profile=post.get("author_profile")
                if isinstance(post.get("author_profile"), Mapping)
                else None,
                trust_level=post.get("trust_level"),
            ) * 60.0
            + quality_score(post) * 25.0
            + personalization_score(post, user_context) * 15.0
        ) * 100.0

    if normalized_mode == SORT_DISCOVERY:
        return discovery_score(
            post,
            user_context=user_context,
        )

    return base


# ============================================================================
# USER / CONTENT CAPABILITIES
# ============================================================================


def user_can_interact(
    *,
    authenticated: bool,
    post: Mapping[str, Any],
    is_owner: bool = False,
    is_group_member: bool = False,
) -> bool:
    """
    Basic policy for whether a user can interact with content.

    Fine-grained authorization remains in the service layer.
    """
    if not authenticated:
        return False

    visibility = _lower(post.get("visibility")) or VISIBILITY_PUBLIC

    return visibility_allows(
        post,
        authenticated=authenticated,
        is_owner=is_owner,
        is_group_member=is_group_member,
    )


def available_capabilities(
    *,
    authenticated: bool,
    post: Mapping[str, Any],
    is_owner: bool = False,
    is_group_member: bool = False,
    already_liked: bool = False,
) -> dict[str, bool]:
    """
    Return frontend-friendly capabilities.

    This prevents the frontend from having to guess which actions make sense.
    The backend must still enforce every action independently.
    """
    visible = visibility_allows(
        post,
        authenticated=authenticated,
        is_owner=is_owner,
        is_group_member=is_group_member,
    )

    interaction_allowed = user_can_interact(
        authenticated=authenticated,
        post=post,
        is_owner=is_owner,
        is_group_member=is_group_member,
    )

    allowed_actions = set(
        allowed_actions_for_post(post)
    )

    return {
        "can_view": visible,
        "can_respond": interaction_allowed and "respond" in allowed_actions,
        "can_apply": interaction_allowed and "apply" in allowed_actions,
        "can_enquire": interaction_allowed and "enquire" in allowed_actions,
        "can_join": interaction_allowed and "join" in allowed_actions,
        "can_buy": interaction_allowed and "buy" in allowed_actions,
        "can_help": interaction_allowed and "help" in allowed_actions,
        "can_attend": interaction_allowed and "attend" in allowed_actions,
        "can_save": interaction_allowed and "save" in allowed_actions,
        "can_follow": interaction_allowed and "follow" in allowed_actions,
        "can_report": interaction_allowed and "report" in allowed_actions,
        "can_like": interaction_allowed,
        "liked_by_me": already_liked if authenticated else False,
        "can_edit": authenticated and is_owner,
        "can_delete": authenticated and is_owner,
    }


# ============================================================================
# GROUP POLICY
# ============================================================================


def validate_group_shape(group: Mapping[str, Any]) -> dict[str, Any]:
    """
    Validate policy-level Group fields.

    Persistence, uniqueness and membership checks remain in services.py.
    """
    if not isinstance(group, Mapping):
        raise APIError(
            "Community group must be an object.",
            400,
            "invalid_group",
        )

    name = _text(group.get("name"))
    group_type = _lower(group.get("type"))
    visibility = _lower(group.get("visibility"))

    if not name:
        raise APIError(
            "Group name is required.",
            400,
            "invalid_group_name",
        )

    if len(name) > 120:
        raise APIError(
            "Group name is too long.",
            400,
            "invalid_group_name",
        )

    if group_type not in GROUP_TYPE_SET:
        raise APIError(
            "Unsupported Community group type.",
            400,
            "invalid_group_type",
        )

    if visibility not in {
        value.lower()
        for value in GROUP_VISIBILITIES
    }:
        raise APIError(
            "Unsupported Community group visibility.",
            400,
            "invalid_group_visibility",
        )

    return {
        **dict(group),
        "name": name,
        "type": group_type,
        "visibility": visibility,
    }


def group_join_requires_approval(
    group: Mapping[str, Any],
) -> bool:
    join_mode = _lower(group.get("join_mode"))

    return join_mode == "request"


# ============================================================================
# THREAD POLICY
# ============================================================================


def validate_thread_shape(thread: Mapping[str, Any]) -> dict[str, Any]:
    """
    Validate a structured conversation/thread.
    """
    if not isinstance(thread, Mapping):
        raise APIError(
            "Community thread must be an object.",
            400,
            "invalid_thread",
        )

    title = _text(thread.get("title"))
    thread_type = _lower(thread.get("type"))
    state = _lower(thread.get("state")) or "open"

    if not title:
        raise APIError(
            "Thread title is required.",
            400,
            "invalid_thread_title",
        )

    if len(title) > 200:
        raise APIError(
            "Thread title is too long.",
            400,
            "invalid_thread_title",
        )

    if thread_type not in THREAD_TYPE_SET:
        raise APIError(
            "Unsupported Community thread type.",
            400,
            "invalid_thread_type",
        )

    if state not in {
        value.lower()
        for value in THREAD_STATES
    }:
        raise APIError(
            "Unsupported Community thread state.",
            400,
            "invalid_thread_state",
        )

    return {
        **dict(thread),
        "title": title,
        "type": thread_type,
        "state": state,
    }


def thread_accepts_response(thread: Mapping[str, Any]) -> bool:
    state = _lower(thread.get("state"))

    return state in {"open", "active"}


# ============================================================================
# INTENT POLICY
# ============================================================================


def validate_discovery_intent(intent: Any) -> str:
    value = _lower(intent)

    if value not in {
        item.lower()
        for item in DISCOVERY_INTENTS
    }:
        raise APIError(
            "Unsupported Discovery intent.",
            400,
            "invalid_discovery_intent",
        )

    return value


def intent_matches_post(
    intent: Any,
    post: Mapping[str, Any],
) -> bool:
    """
    Determine whether a post can satisfy a user's explicit discovery intent.
    """
    normalized = validate_discovery_intent(intent)

    post_type = _lower(
        _first_non_empty(post, "type", "post_type")
    )

    mapping = {
        "learn": {
            "resource",
            "discussion",
            "insight",
            "question",
        },
        "find": {
            "offer",
            "request",
            "opportunity",
            "resource",
        },
        "connect": {
            "discussion",
            "project",
            "opportunity",
        },
        "buy": {
            "offer",
        },
        "sell": {
            "offer",
        },
        "hire": {
            "opportunity",
            "request",
        },
        "work": {
            "opportunity",
            "project",
        },
        "help": {
            "help_request",
            "request",
        },
        "join": {
            "project",
            "event",
            "announcement",
        },
        "attend": {
            "event",
        },
        "collaborate": {
            "project",
            "discussion",
            "opportunity",
        },
        "support": {
            "request",
            "help_request",
            "project",
        },
    }

    return post_type in mapping.get(normalized, set())


# ============================================================================
# SECURITY-ORIENTED POLICY CHECKS
# ============================================================================


def reject_client_supplied_authority(
    payload: Mapping[str, Any],
) -> None:
    """
    Detect fields that SHOULD NEVER determine backend authorization.

    The frontend may send these fields accidentally, but services should never
    use them as authority.

    This helper is intentionally advisory: callers may choose to strip these
    fields or reject the request.
    """
    forbidden_authority_fields = {
        "is_admin",
        "is_owner",
        "role",
        "permissions",
        "trust_level",
        "reputation_score",
        "verified",
        "verified_owner",
        "account_status",
    }

    supplied = forbidden_authority_fields.intersection(payload.keys())

    if supplied:
        raise APIError(
            "Client-supplied authority fields are not accepted.",
            400,
            "forbidden_authority_fields",
        )


def validate_no_unsupported_source_hub(source: Mapping[str, Any]) -> None:
    """
    Make the cross-hub boundary explicit.

    A source may come from an approved Jumuiya surface, but services.py must
    still independently verify ownership/access.
    """
    hub = _lower(source.get("hub"))

    if hub not in SOURCE_HUB_SET:
        raise APIError(
            "Unsupported Community source hub.",
            400,
            "invalid_source_hub",
        )


# ============================================================================
# POLICY SUMMARY
# ============================================================================


def summarize_content_policy(
    post: Mapping[str, Any],
    *,
    user_context: Mapping[str, Any] | None = None,
    author_profile: Mapping[str, Any] | None = None,
    author_trust_level: Any = None,
) -> dict[str, Any]:
    """
    Produce one consistent policy snapshot.

    This is useful for services.py, discovery.py and eventually the frontend
    API representation.

    It does not authorize database operations.
    """
    post_type = _lower(
        _first_non_empty(post, "type", "post_type")
    )

    trust = trust_score(
        profile=author_profile,
        trust_level=author_trust_level,
    )

    pulse = pulse_score(
        post,
        user_context=user_context,
        author_profile=author_profile,
        author_trust_level=author_trust_level,
    )

    return {
        "post_type": post_type,
        "is_actionable": is_actionable_post(post),
        "is_discussion": is_discussion_post(post),
        "is_question": is_question_post(post),
        "is_help_request": is_help_request(post),
        "is_opportunity": is_opportunity_post(post),
        "allowed_actions": list(
            allowed_actions_for_post(post)
        ),
        "trust_score": round(trust * 100.0, 4),
        "quality_score": round(
            quality_score(post) * 100.0,
            4,
        ),
        "freshness_score": round(
            freshness_score(post) * 100.0,
            4,
        ),
        "actionability_score": round(
            actionability_score(post) * 100.0,
            4,
        ),
        "personalization_score": round(
            personalization_score(
                post,
                user_context,
            ) * 100.0,
            4,
        ),
        "pulse_score": pulse,
        "should_surface_in_pulse": should_surface_in_pulse(
            post,
            user_context=user_context,
        ),
    }


__all__ = [
    # Structural
    "validate_hub",
    "validate_post_type",
    "validate_visibility",
    "validate_category",
    "validate_sort_mode",
    "validate_post_shape",

    # Content
    "is_actionable_post",
    "is_discussion_post",
    "is_question_post",
    "is_help_request",
    "is_opportunity_post",

    # Actions
    "validate_action",
    "validate_action_target",
    "allowed_actions_for_post",
    "action_is_allowed_for_post",

    # Visibility
    "visibility_allows",

    # Sources
    "source_is_supported",
    "validate_source_shape",

    # Trust
    "normalize_trust_level",
    "trust_level_score",
    "reputation_score",
    "trust_score",

    # Relevance
    "set_overlap_score",
    "topic_relevance_score",
    "hub_relevance_score",
    "location_relevance_score",
    "freshness_score",
    "actionability_score",
    "completeness_score",
    "quality_score",
    "engagement_score",
    "personalization_score",

    # Pulse / discovery
    "pulse_score",
    "should_surface_in_pulse",
    "discovery_score",
    "mode_score",

    # Capabilities
    "user_can_interact",
    "available_capabilities",

    # Groups
    "validate_group_shape",
    "group_join_requires_approval",

    # Threads
    "validate_thread_shape",
    "thread_accepts_response",

    # Intent
    "validate_discovery_intent",
    "intent_matches_post",

    # Security
    "reject_client_supplied_authority",
    "validate_no_unsupported_source_hub",

    # Summary
    "summarize_content_policy",
]