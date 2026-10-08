# backend/jumuiya/community/discovery.py
"""
Jumuiya Community — discovery and Pulse ranking engine.

This module intentionally contains NO database operations.

The Community Hub is not a chronological social-media feed.

Instead, discovery tries to answer:

    PULSE
        What is useful to me right now?

    DISCOVERY
        Who / what / where can I connect with?

The ranking model deliberately balances:

    - personal relevance
    - usefulness
    - freshness
    - trust
    - locality
    - actionability
    - meaningful engagement
    - relationship/context
    - novelty
    - diversity

Popularity is NOT the primary ranking signal.

A candidate may be surfaced even with very little engagement when it is
highly relevant, useful, local, trusted or actionable.

This module receives already-fetched candidates from services.py and returns
ranked/enriched candidates.
"""


from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence

from backend.jumuiya.core.errors import APIError

from .constants import (
    ACTIONABLE_POST_TYPES,
    DISCOVERABLE_HUBS,
    DISCOVERY_ENTITY_TYPES,
    DISCOVERY_INTENTS,
    SORT_ACTIONABLE,
    SORT_DISCOVERY,
    SORT_NEARBY,
    SORT_RECENT,
    SORT_RELEVANT,
    SORT_TRUSTED,
)
from .policy import (
    actionability_score,
    discovery_score,
    engagement_score,
    freshness_score,
    hub_relevance_score,
    intent_matches_post,
    location_relevance_score,
    personalization_score,
    pulse_score,
    quality_score,
    reputation_score,
    trust_score,
)


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    return str(value).strip()


def _lower(value: Any) -> str:
    return _text(value).lower()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default

    if value < 0:
        return default

    return value


def _bounded(
    value: float,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    return max(minimum, min(maximum, value))


def _as_set(value: Any) -> set[str]:
    if value is None:
        return set()

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, (list, tuple, set, frozenset)):
        return set()

    result: set[str] = set()

    for item in value:
        normalized = _lower(item)
        if normalized:
            result.add(normalized)

    return result


def _first(
    mapping: Mapping[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        value = mapping.get(key)

        if value not in (None, "", [], {}, ()):
            return value

    return None


# ============================================================================
# CANDIDATE IDENTITY
# ============================================================================


def candidate_identity(candidate: Mapping[str, Any]) -> str:
    """
    Build a stable identity for a discovery candidate.

    Existing Community posts use the post ID. Cross-hub candidates can use
    their source reference or entity ID.

    The identity is only used for ranking/deduplication and is never trusted
    for authorization.
    """
    candidate_id = _first(
        candidate,
        "_id",
        "id",
        "post_id",
        "entity_id",
    )

    if candidate_id not in (None, ""):
        return str(candidate_id)

    source = candidate.get("source")

    if isinstance(source, Mapping):
        hub = _lower(source.get("hub"))
        entity_type = _lower(
            _first(source, "type", "entity_type")
        )
        entity_id = _text(
            _first(source, "id", "entity_id")
        )

        if hub and entity_type and entity_id:
            return f"{hub}:{entity_type}:{entity_id}"

    return repr(sorted(candidate.items(), key=lambda pair: str(pair[0])))


def candidate_entity_type(
    candidate: Mapping[str, Any],
) -> str:
    """
    Determine what Discovery is ranking.
    """
    explicit = _lower(
        _first(
            candidate,
            "entity_type",
            "entityType",
            "result_type",
            "resultType",
        )
    )

    if explicit:
        return explicit

    post_type = _lower(
        _first(candidate, "post_type", "type")
    )

    if post_type:
        return "post"

    source = candidate.get("source")

    if isinstance(source, Mapping):
        source_type = _lower(
            _first(source, "type", "entity_type")
        )

        if source_type:
            return source_type

    return "post"


def candidate_hub(
    candidate: Mapping[str, Any],
) -> str:
    hub = _lower(candidate.get("hub"))

    if hub:
        return hub

    source = candidate.get("source")

    if isinstance(source, Mapping):
        return _lower(source.get("hub"))

    return ""


# ============================================================================
# CONTENT / CONTEXT EXTRACTION
# ============================================================================


def candidate_topics(
    candidate: Mapping[str, Any],
) -> set[str]:
    values: set[str] = set()

    values.update(_as_set(candidate.get("tags")))

    category = _lower(candidate.get("category"))
    if category:
        values.add(category)

    post_type = _lower(
        _first(candidate, "post_type", "type")
    )

    if post_type:
        values.add(post_type)

    for key in (
        "topics",
        "interests",
        "skills",
        "keywords",
    ):
        values.update(_as_set(candidate.get(key)))

    return values


def candidate_location(
    candidate: Mapping[str, Any],
) -> str:
    return _lower(
        _first(
            candidate,
            "location",
            "town",
            "county",
            "area",
            "place",
        )
    )


def is_candidate_visible(
    candidate: Mapping[str, Any],
) -> bool:
    """
    Discovery should not resurrect deleted/hidden/archived content.

    Authorization and visibility semantics still belong to policy/services.
    This is an additional ranking safeguard.
    """
    state = _lower(
        _first(
            candidate,
            "status",
            "state",
            "content_state",
        )
    )

    if state in {
        "deleted",
        "hidden",
        "archived",
        "blocked",
        "suspended",
    }:
        return False

    if candidate.get("is_deleted") is True:
        return False

    if candidate.get("is_hidden") is True:
        return False

    return True


def is_candidate_excluded(
    candidate: Mapping[str, Any],
    user_context: Mapping[str, Any] | None = None,
) -> bool:
    """
    Apply user-specific exclusions supplied by the trusted backend context.

    Example context:

        {
            "blocked_users": ["..."],
            "muted_users": ["..."],
            "hidden_items": ["..."],
            "reported_items": ["..."]
        }

    These values MUST come from backend state, not directly from the
    untrusted client.
    """
    if not is_candidate_visible(candidate):
        return True

    if not isinstance(user_context, Mapping):
        return False

    identity = candidate_identity(candidate)

    author_id = _text(
        _first(
            candidate,
            "author_user_id",
            "user_id",
            "owner_user_id",
        )
    )

    blocked_users = _as_set(
        user_context.get("blocked_users")
    )

    muted_users = _as_set(
        user_context.get("muted_users")
    )

    hidden_items = _as_set(
        user_context.get("hidden_items")
    )

    reported_items = _as_set(
        user_context.get("reported_items")
    )

    if author_id and author_id.lower() in blocked_users:
        return True

    if author_id and author_id.lower() in muted_users:
        return True

    if identity.lower() in hidden_items:
        return True

    if identity.lower() in reported_items:
        return True

    return False


# ============================================================================
# RELATIONSHIP SIGNALS
# ============================================================================


def relationship_score(
    candidate: Mapping[str, Any],
    user_context: Mapping[str, Any] | None = None,
) -> float:
    """
    Reward meaningful existing relationships without turning Community into
    a follower-only network.
    """
    if not isinstance(user_context, Mapping):
        return 0.0

    relationship = _lower(
        _first(
            candidate,
            "relationship",
            "relationship_type",
        )
    )

    connected_user_ids = _as_set(
        user_context.get("connected_user_ids")
    )

    author_id = _text(
        _first(
            candidate,
            "author_user_id",
            "user_id",
            "owner_user_id",
        )
    )

    if author_id and author_id.lower() in connected_user_ids:
        return 1.0

    weights = {
        "owner": 1.0,
        "member": 0.90,
        "participant": 0.85,
        "collaborator": 0.90,
        "teacher": 0.75,
        "student": 0.75,
        "customer": 0.65,
        "following": 0.60,
        "community_contributor": 0.55,
        "business_owner": 0.50,
        "farmer": 0.50,
    }

    return weights.get(relationship, 0.0)


# ============================================================================
# NOVELTY
# ============================================================================


def novelty_score(
    candidate: Mapping[str, Any],
    user_context: Mapping[str, Any] | None = None,
) -> float:
    """
    Reward material the user has not already consumed.

    A trusted backend can provide:

        viewed_items
        interacted_items
        saved_items

    Discovery uses these only as contextual signals.
    """
    if not isinstance(user_context, Mapping):
        return 1.0

    identity = candidate_identity(candidate)

    consumed = (
        _as_set(user_context.get("viewed_items"))
        | _as_set(user_context.get("interacted_items"))
        | _as_set(user_context.get("opened_items"))
    )

    if identity.lower() in consumed:
        return 0.0

    return 1.0


# ============================================================================
# ACTION / INTENT FIT
# ============================================================================


def explicit_intent_score(
    candidate: Mapping[str, Any],
    user_context: Mapping[str, Any] | None = None,
) -> float:
    """
    Explicit user intent gets stronger weight than inferred intent.

    Example:
        user_context = {"discovery_intent": "buy"}

    The candidate then receives a strong boost when it represents something
    useful for buying.
    """
    if not isinstance(user_context, Mapping):
        return 0.0

    intent = _lower(
        _first(
            user_context,
            "discovery_intent",
            "intent",
            "current_intent",
        )
    )

    if not intent:
        return 0.0

    try:
        if intent_matches_post(intent, candidate):
            return 1.0
    except APIError:
        # A malformed context value must not crash discovery. It simply
        # contributes no intent signal.
        return 0.0

    return 0.0


# ============================================================================
# CROSS-HUB VALUE
# ============================================================================


def cross_hub_value_score(
    candidate: Mapping[str, Any],
    user_context: Mapping[str, Any] | None = None,
) -> float:
    """
    Reward useful cross-hub connections.

    Example:
        A Community post linking to a legitimate Biashara opportunity or
        Shamba resource can be more useful than an isolated conversation.

    This does NOT grant access. services.py must already have established
    that the source is valid and accessible.
    """
    hub = candidate_hub(candidate)

    if not hub:
        return 0.0

    source = candidate.get("source")

    if not isinstance(source, Mapping):
        return 0.0

    source_hub = _lower(source.get("hub"))

    if not source_hub or source_hub == "community":
        return 0.0

    active_hubs = set()

    if isinstance(user_context, Mapping):
        active_hubs = _as_set(
            _first(
                user_context,
                "active_hubs",
                "hubs",
                "preferred_hubs",
            )
        )

    if source_hub in active_hubs:
        return 1.0

    return 0.60


# ============================================================================
# DISCOVERY SIGNAL BREAKDOWN
# ============================================================================


def score_signals(
    candidate: Mapping[str, Any],
    *,
    user_context: Mapping[str, Any] | None = None,
) -> dict[str, float]:
    """
    Calculate all useful discovery signals independently.

    Returning the individual signals is intentional: the frontend/debugging
    layer can eventually explain why something was surfaced without exposing
    the raw internal algorithm.
    """
    author_profile = candidate.get("author_profile")

    if not isinstance(author_profile, Mapping):
        author_profile = None

    trust = trust_score(
        profile=author_profile,
        trust_level=candidate.get("trust_level"),
    )

    return {
        "personalization": _bounded(
            personalization_score(
                candidate,
                user_context,
            )
        ),
        "freshness": _bounded(
            freshness_score(candidate)
        ),
        "quality": _bounded(
            quality_score(candidate)
        ),
        "trust": _bounded(trust),
        "actionability": _bounded(
            actionability_score(candidate)
        ),
        "engagement": _bounded(
            engagement_score(candidate)
        ),
        "locality": _bounded(
            location_relevance_score(
                candidate,
                user_context,
            )
        ),
        "hub_relevance": _bounded(
            hub_relevance_score(
                candidate,
                user_context,
            )
        ),
        "relationship": _bounded(
            relationship_score(
                candidate,
                user_context,
            )
        ),
        "novelty": _bounded(
            novelty_score(
                candidate,
                user_context,
            )
        ),
        "explicit_intent": _bounded(
            explicit_intent_score(
                candidate,
                user_context,
            )
        ),
        "cross_hub_value": _bounded(
            cross_hub_value_score(
                candidate,
                user_context,
            )
        ),
    }


# ============================================================================
# PRIMARY CANDIDATE SCORE
# ============================================================================


def candidate_score(
    candidate: Mapping[str, Any],
    *,
    user_context: Mapping[str, Any] | None = None,
    mode: str = SORT_RELEVANT,
) -> float:
    """
    Calculate the final candidate ranking score.

    The model intentionally gives more weight to context and usefulness than
    raw popularity.

    Base model:

        personalization    22%
        quality            14%
        trust              13%
        freshness          12%
        actionability      10%
        locality            8%
        relationship        7%
        novelty             5%
        explicit intent     5%
        cross-hub value     2%
        engagement          2%

    Then mode-specific adjustments are applied.
    """
    signals = score_signals(
        candidate,
        user_context=user_context,
    )

    mode = _lower(mode) or SORT_RELEVANT

    base = (
        signals["personalization"] * 0.22
        + signals["quality"] * 0.14
        + signals["trust"] * 0.13
        + signals["freshness"] * 0.12
        + signals["actionability"] * 0.10
        + signals["locality"] * 0.08
        + signals["relationship"] * 0.07
        + signals["novelty"] * 0.05
        + signals["explicit_intent"] * 0.05
        + signals["cross_hub_value"] * 0.02
        + signals["engagement"] * 0.02
    )

    if mode == SORT_RECENT:
        base = (
            signals["freshness"] * 0.55
            + signals["quality"] * 0.15
            + signals["personalization"] * 0.10
            + signals["trust"] * 0.10
            + signals["actionability"] * 0.05
            + signals["novelty"] * 0.05
        )

    elif mode == SORT_NEARBY:
        base = (
            signals["locality"] * 0.40
            + signals["personalization"] * 0.18
            + signals["freshness"] * 0.14
            + signals["trust"] * 0.12
            + signals["quality"] * 0.08
            + signals["actionability"] * 0.05
            + signals["novelty"] * 0.03
        )

    elif mode == SORT_ACTIONABLE:
        base = (
            signals["actionability"] * 0.35
            + signals["explicit_intent"] * 0.20
            + signals["personalization"] * 0.15
            + signals["quality"] * 0.10
            + signals["freshness"] * 0.08
            + signals["trust"] * 0.07
            + signals["locality"] * 0.03
            + signals["novelty"] * 0.02
        )

    elif mode == SORT_TRUSTED:
        base = (
            signals["trust"] * 0.40
            + signals["quality"] * 0.20
            + signals["personalization"] * 0.15
            + signals["freshness"] * 0.10
            + signals["actionability"] * 0.08
            + signals["relationship"] * 0.05
            + signals["novelty"] * 0.02
        )

    elif mode == SORT_DISCOVERY:
        base = (
            signals["personalization"] * 0.18
            + signals["cross_hub_value"] * 0.16
            + signals["novelty"] * 0.14
            + signals["quality"] * 0.12
            + signals["trust"] * 0.11
            + signals["actionability"] * 0.10
            + signals["freshness"] * 0.08
            + signals["locality"] * 0.05
            + signals["relationship"] * 0.04
            + signals["engagement"] * 0.02
        )

    # A small explicit-intent boost applies to every mode.
    base += signals["explicit_intent"] * 0.03

    return round(_bounded(base) * 100.0, 6)


# ============================================================================
# DISCOVERY EXPLANATION
# ============================================================================


def discovery_reason(
    candidate: Mapping[str, Any],
    *,
    user_context: Mapping[str, Any] | None = None,
) -> str:
    """
    Produce a human-readable reason for surfacing a candidate.

    The wording is deliberately contextual rather than:
        "Trending because 4,000 likes."
    """
    signals = score_signals(
        candidate,
        user_context=user_context,
    )

    reasons: list[tuple[float, str]] = [
        (
            signals["explicit_intent"],
            "matches what you are looking for",
        ),
        (
            signals["personalization"],
            "matches your interests",
        ),
        (
            signals["locality"],
            "relevant to your area",
        ),
        (
            signals["cross_hub_value"],
            "connects with another Jumuiya hub",
        ),
        (
            signals["actionability"],
            "offers something you can act on",
        ),
        (
            signals["trust"],
            "comes from a trusted source",
        ),
        (
            signals["freshness"],
            "is recent",
        ),
        (
            signals["novelty"],
            "you have not interacted with it yet",
        ),
        (
            signals["quality"],
            "contains useful context",
        ),
        (
            signals["relationship"],
            "comes from a meaningful connection",
        ),
    ]

    reasons.sort(key=lambda item: item[0], reverse=True)

    for signal, reason in reasons:
        if signal >= 0.55:
            return reason

    return "relevant to your Community"


# ============================================================================
# DIVERSITY
# ============================================================================


def diversity_key(
    candidate: Mapping[str, Any],
) -> tuple[str, str, str]:
    """
    Group candidates for diversity control.

    Prevents a feed from becoming:

        same author × 20
        same hub × 20
        same category × 20
    """
    author = _text(
        _first(
            candidate,
            "author_user_id",
            "user_id",
            "owner_user_id",
        )
    ).lower()

    hub = candidate_hub(candidate)

    category = _lower(candidate.get("category"))

    return (
        author,
        hub,
        category,
    )


def diversify_candidates(
    ranked_candidates: Sequence[Mapping[str, Any]],
    *,
    limit: int,
    max_same_author: int = 3,
    max_same_hub: int = 8,
    max_same_category: int = 5,
) -> list[dict[str, Any]]:
    """
    Select a ranked but diverse set.

    We do not simply take the first N results.

    The algorithm makes room for different useful sources while preserving
    ranking order as much as possible.
    """
    if limit <= 0:
        return []

    selected: list[dict[str, Any]] = []

    seen_ids: set[str] = set()
    author_counts: defaultdict[str, int] = defaultdict(int)
    hub_counts: defaultdict[str, int] = defaultdict(int)
    category_counts: defaultdict[str, int] = defaultdict(int)

    deferred: list[dict[str, Any]] = []

    for candidate in ranked_candidates:
        identity = candidate_identity(candidate)

        if identity in seen_ids:
            continue

        author, hub, category = diversity_key(candidate)

        author_limit_hit = (
            bool(author)
            and author_counts[author] >= max_same_author
        )

        hub_limit_hit = (
            bool(hub)
            and hub_counts[hub] >= max_same_hub
        )

        category_limit_hit = (
            bool(category)
            and category_counts[category] >= max_same_category
        )

        if (
            author_limit_hit
            or hub_limit_hit
            or category_limit_hit
        ):
            deferred.append(dict(candidate))
            continue

        item = dict(candidate)

        seen_ids.add(identity)
        selected.append(item)

        if author:
            author_counts[author] += 1

        if hub:
            hub_counts[hub] += 1

        if category:
            category_counts[category] += 1

        if len(selected) >= limit:
            return selected

    # Fill remaining places with deferred items. We still deduplicate.
    for candidate in deferred:
        identity = candidate_identity(candidate)

        if identity in seen_ids:
            continue

        seen_ids.add(identity)
        selected.append(dict(candidate))

        if len(selected) >= limit:
            break

    return selected


# ============================================================================
# RANKING
# ============================================================================


def rank_candidates(
    candidates: Iterable[Mapping[str, Any]],
    *,
    user_context: Mapping[str, Any] | None = None,
    mode: str = SORT_RELEVANT,
    limit: int = 20,
    diversify: bool = True,
) -> list[dict[str, Any]]:
    """
    Rank candidates and return enriched results.

    Every returned candidate receives private/internal discovery metadata
    prefixed with "_discovery_".

    A route/service layer may choose which metadata is safe to expose
    publicly.
    """
    if limit <= 0:
        return []

    if limit > 50:
        limit = 50

    normalized_mode = _lower(mode) or SORT_RELEVANT

    if normalized_mode not in {
        SORT_RELEVANT,
        SORT_RECENT,
        SORT_NEARBY,
        SORT_ACTIONABLE,
        SORT_TRUSTED,
        SORT_DISCOVERY,
    }:
        raise APIError(
            400,
            "invalid_discovery_mode",
            "Unsupported Community discovery mode.",
        )

    prepared: list[dict[str, Any]] = []

    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue

        item = dict(candidate)

        if is_candidate_excluded(
            item,
            user_context,
        ):
            continue

        score = candidate_score(
            item,
            user_context=user_context,
            mode=normalized_mode,
        )

        signals = score_signals(
            item,
            user_context=user_context,
        )

        item["_discovery_score"] = score
        item["_discovery_reason"] = discovery_reason(
            item,
            user_context=user_context,
        )
        item["_discovery_entity_type"] = candidate_entity_type(
            item
        )
        item["_discovery_signals"] = signals

        prepared.append(item)

    # Highest score first.
    #
    # Identity gives us deterministic tie-breaking without random behavior.
    prepared.sort(
        key=lambda item: (
            -float(item.get("_discovery_score", 0.0)),
            candidate_identity(item),
        )
    )

    if not diversify:
        return prepared[:limit]

    return diversify_candidates(
        prepared,
        limit=limit,
    )


# ============================================================================
# PULSE
# ============================================================================


def build_pulse(
    candidates: Iterable[Mapping[str, Any]],
    *,
    user_context: Mapping[str, Any] | None = None,
    limit: int = 20,
    mode: str = SORT_RELEVANT,
) -> list[dict[str, Any]]:
    """
    Build the user's Pulse.

    Pulse is:
        "What is useful to me right now?"

    It is not:
        "What received the most likes?"
    """
    return rank_candidates(
        candidates,
        user_context=user_context,
        mode=mode,
        limit=limit,
        diversify=True,
    )


# ============================================================================
# DISCOVERY
# ============================================================================


def _matches_entity_type(
    candidate: Mapping[str, Any],
    requested_types: set[str],
) -> bool:
    if not requested_types:
        return True

    entity_type = candidate_entity_type(candidate)

    return entity_type in requested_types


def _matches_hub(
    candidate: Mapping[str, Any],
    requested_hubs: set[str],
) -> bool:
    if not requested_hubs:
        return True

    return candidate_hub(candidate) in requested_hubs


def _matches_query(
    candidate: Mapping[str, Any],
    query: str,
) -> bool:
    if not query:
        return True

    normalized_query = query.lower()

    searchable: list[str] = []

    for key in (
        "title",
        "body",
        "description",
        "name",
        "category",
        "location",
        "town",
        "county",
    ):
        value = candidate.get(key)

        if isinstance(value, str):
            searchable.append(value.lower())

    for key in (
        "tags",
        "topics",
        "keywords",
    ):
        searchable.extend(
            value.lower()
            for value in _as_set(candidate.get(key))
        )

    haystack = " ".join(searchable)

    return normalized_query in haystack


def build_discovery(
    candidates: Iterable[Mapping[str, Any]],
    *,
    user_context: Mapping[str, Any] | None = None,
    query: str | None = None,
    intent: str | None = None,
    entity_types: Sequence[str] | None = None,
    hubs: Sequence[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Build the Discovery surface.

    Discovery is broader than Pulse.

    Example:

        "Find a mathematics teacher"

    can discover:
        - education profiles
        - schools
        - opportunities
        - people
        - groups
        - relevant Community posts

    while:

        "buy tomatoes"

    can discover:
        - farmers
        - products
        - businesses
        - marketplace listings
        - offers
    """
    if limit <= 0:
        return []

    if limit > 50:
        limit = 50

    normalized_query = _text(query).lower()
    normalized_intent = _text(intent).lower()

    if normalized_intent:
        if normalized_intent not in {
            value.lower()
            for value in DISCOVERY_INTENTS
        }:
            raise APIError(
                400,
                "invalid_discovery_intent",
                "Unsupported Discovery intent.",
            )

    requested_types = {
        _lower(value)
        for value in (entity_types or [])
        if _text(value)
    }

    known_entity_types = {
        _lower(value)
        for value in DISCOVERY_ENTITY_TYPES
    }

    unsupported_types = requested_types - known_entity_types

    if unsupported_types:
        raise APIError(
            400,
            "invalid_entity_type",
            "Unsupported Discovery entity type.",
        )

    requested_hubs = {
        _lower(value)
        for value in (hubs or [])
        if _text(value)
    }

    known_hubs = {
        _lower(value)
        for value in DISCOVERABLE_HUBS
    }

    unsupported_hubs = requested_hubs - known_hubs

    if unsupported_hubs:
        raise APIError(
            400,
            "invalid_hub",
            "Unsupported Discovery hub.",
        )

    filtered: list[dict[str, Any]] = []

    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue

        item = dict(candidate)

        if is_candidate_excluded(
            item,
            user_context,
        ):
            continue

        if not _matches_query(
            item,
            normalized_query,
        ):
            continue

        if not _matches_entity_type(
            item,
            requested_types,
        ):
            continue

        if not _matches_hub(
            item,
            requested_hubs,
        ):
            continue

        if normalized_intent:
            try:
                intent_fit = intent_matches_post(
                    normalized_intent,
                    item,
                )
            except APIError:
                intent_fit = False

            # If the entity itself is not a post, explicit intent may be
            # represented by its own "intent_fit" supplied by services.py.
            if not intent_fit:
                supplied_fit = item.get("intent_fit")

                if supplied_fit is not True:
                    # Do not throw away useful non-post entities merely
                    # because the generic post policy does not know them.
                    entity_type = candidate_entity_type(item)

                    if entity_type == "post":
                        continue

        filtered.append(item)

    ranked = rank_candidates(
        filtered,
        user_context=user_context,
        mode=SORT_DISCOVERY,
        limit=limit,
        diversify=True,
    )

    return ranked


# ============================================================================
# SMART DISCOVERY MIX
# ============================================================================


def classify_candidate(
    candidate: Mapping[str, Any],
) -> str:
    """
    Classify a candidate into a useful Community discovery bucket.

    This powers diversity beyond simple author/category limits.
    """
    entity_type = candidate_entity_type(candidate)
    post_type = _lower(
        _first(candidate, "post_type", "type")
    )

    if entity_type in {
        "business",
        "product",
        "listing",
        "service",
    }:
        return "commerce"

    if entity_type in {
        "school",
        "lesson",
        "assignment",
        "education_profile",
    }:
        return "learning"

    if entity_type in {
        "farm",
        "farmer",
        "crop",
        "harvest",
    }:
        return "agriculture"

    if entity_type in {
        "person",
        "group",
        "thread",
    }:
        return "people"

    if post_type in {
        "opportunity",
        "offer",
        "request",
        "event",
        "help_request",
    }:
        return "action"

    if post_type in {
        "resource",
        "insight",
    }:
        return "knowledge"

    if post_type in ACTIONABLE_POST_TYPES:
        return "action"

    return "community"


def smart_mix(
    candidates: Sequence[Mapping[str, Any]],
    *,
    limit: int = 20,
    max_per_bucket: int = 6,
) -> list[dict[str, Any]]:
    """
    Produce a healthy mixture of Community content.

    Example mixture:

        useful discussion
        local opportunity
        learning resource
        business connection
        agriculture item
        event
        group/thread

    This prevents the home surface from accidentally becoming dominated by a
    single type of content.
    """
    if limit <= 0:
        return []

    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue

        bucket = classify_candidate(candidate)

        if len(buckets[bucket]) < max_per_bucket:
            buckets[bucket].append(dict(candidate))

    result: list[dict[str, Any]] = []

    # Round-robin across buckets.
    bucket_names = sorted(
        buckets.keys(),
        key=lambda bucket: (
            -len(buckets[bucket]),
            bucket,
        ),
    )

    cursor = 0

    while bucket_names and len(result) < limit:
        if cursor >= len(bucket_names):
            cursor = 0

        bucket = bucket_names[cursor]
        queue = buckets[bucket]

        if queue:
            result.append(
                queue.pop(0)
            )

        if not queue:
            bucket_names.pop(cursor)
            continue

        cursor += 1

    return result


# ============================================================================
# NEARBY DISCOVERY
# ============================================================================


def nearby(
    candidates: Iterable[Mapping[str, Any]],
    *,
    user_context: Mapping[str, Any] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Convenience surface for location-focused discovery.
    """
    return rank_candidates(
        candidates,
        user_context=user_context,
        mode=SORT_NEARBY,
        limit=limit,
        diversify=True,
    )


# ============================================================================
# ACTION-ORIENTED DISCOVERY
# ============================================================================


def opportunities(
    candidates: Iterable[Mapping[str, Any]],
    *,
    user_context: Mapping[str, Any] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Find content that can lead to a real action.
    """
    prepared: list[dict[str, Any]] = []

    actionable_types = {
        value.lower()
        for value in ACTIONABLE_POST_TYPES
    }

    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue

        post_type = _lower(
            _first(candidate, "post_type", "type")
        )

        action = candidate.get("action")

        if post_type not in actionable_types and not action:
            continue

        prepared.append(dict(candidate))

    return rank_candidates(
        prepared,
        user_context=user_context,
        mode=SORT_ACTIONABLE,
        limit=limit,
        diversify=True,
    )


# ============================================================================
# TRUSTED DISCOVERY
# ============================================================================


def trusted(
    candidates: Iterable[Mapping[str, Any]],
    *,
    user_context: Mapping[str, Any] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Surface higher-trust information and entities.
    """
    return rank_candidates(
        candidates,
        user_context=user_context,
        mode=SORT_TRUSTED,
        limit=limit,
        diversify=True,
    )


# ============================================================================
# EXPLORATION
# ============================================================================


def exploration(
    candidates: Iterable[Mapping[str, Any]],
    *,
    user_context: Mapping[str, Any] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    Produce a more exploratory Discovery surface.

    Unlike Pulse, this intentionally gives more weight to novelty and
    cross-hub discovery so a user can encounter something outside their
    normal routine.
    """
    prepared: list[dict[str, Any]] = []

    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue

        if is_candidate_excluded(
            candidate,
            user_context,
        ):
            continue

        item = dict(candidate)

        signals = score_signals(
            item,
            user_context=user_context,
        )

        exploration_score = (
            signals["novelty"] * 0.28
            + signals["cross_hub_value"] * 0.18
            + signals["quality"] * 0.16
            + signals["trust"] * 0.14
            + signals["personalization"] * 0.10
            + signals["freshness"] * 0.08
            + signals["actionability"] * 0.06
        )

        item["_discovery_score"] = round(
            _bounded(exploration_score) * 100.0,
            6,
        )

        item["_discovery_reason"] = (
            "something useful you may not have discovered yet"
        )

        item["_discovery_entity_type"] = candidate_entity_type(
            item
        )

        item["_discovery_signals"] = signals

        prepared.append(item)

    prepared.sort(
        key=lambda item: (
            -float(item.get("_discovery_score", 0.0)),
            candidate_identity(item),
        )
    )

    return diversify_candidates(
        prepared,
        limit=limit,
    )


# ============================================================================
# DISCOVERY RESPONSE
# ============================================================================


def public_discovery_metadata(
    candidate: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Convert internal discovery information into frontend-safe metadata.

    Internal signal values can remain server-side if desired.
    """
    return {
        "score": round(
            _number(candidate.get("_discovery_score")),
            2,
        ),
        "reason": _text(
            candidate.get("_discovery_reason")
        ),
        "entity_type": _text(
            candidate.get("_discovery_entity_type")
        ),
    }


def attach_public_discovery_metadata(
    candidates: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """
    Add frontend-safe discovery metadata without exposing the complete
    internal scoring model.
    """
    result: list[dict[str, Any]] = []

    for candidate in candidates:
        item = dict(candidate)

        item["discovery"] = public_discovery_metadata(
            item
        )

        # Remove internal model data from the public representation.
        item.pop("_discovery_score", None)
        item.pop("_discovery_reason", None)
        item.pop("_discovery_entity_type", None)
        item.pop("_discovery_signals", None)

        result.append(item)

    return result


# ============================================================================
# COMPLETE COMMUNITY INTELLIGENCE PIPELINE
# ============================================================================


def build_community_surface(
    candidates: Iterable[Mapping[str, Any]],
    *,
    surface: str = "pulse",
    user_context: Mapping[str, Any] | None = None,
    query: str | None = None,
    intent: str | None = None,
    entity_types: Sequence[str] | None = None,
    hubs: Sequence[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """
    One public orchestration function for services/routes.

    Supported surfaces:

        pulse
        discovery
        nearby
        opportunities
        trusted
        exploration
    """
    normalized_surface = _lower(surface) or "pulse"

    if normalized_surface == "pulse":
        results = build_pulse(
            candidates,
            user_context=user_context,
            limit=limit,
        )

    elif normalized_surface == "discovery":
        results = build_discovery(
            candidates,
            user_context=user_context,
            query=query,
            intent=intent,
            entity_types=entity_types,
            hubs=hubs,
            limit=limit,
        )

    elif normalized_surface == "nearby":
        results = nearby(
            candidates,
            user_context=user_context,
            limit=limit,
        )

    elif normalized_surface == "opportunities":
        results = opportunities(
            candidates,
            user_context=user_context,
            limit=limit,
        )

    elif normalized_surface == "trusted":
        results = trusted(
            candidates,
            user_context=user_context,
            limit=limit,
        )

    elif normalized_surface == "exploration":
        results = exploration(
            candidates,
            user_context=user_context,
            limit=limit,
        )

    else:
        raise APIError(
            400,
            "invalid_community_surface",
            "Unsupported Community surface.",
        )

    return attach_public_discovery_metadata(
        results
    )


__all__ = [
    # Identity / extraction
    "candidate_identity",
    "candidate_entity_type",
    "candidate_hub",
    "candidate_topics",
    "candidate_location",

    # Filtering
    "is_candidate_visible",
    "is_candidate_excluded",

    # Signals
    "relationship_score",
    "novelty_score",
    "explicit_intent_score",
    "cross_hub_value_score",
    "score_signals",

    # Ranking
    "candidate_score",
    "discovery_reason",
    "diversity_key",
    "diversify_candidates",
    "rank_candidates",

    # Main surfaces
    "build_pulse",
    "build_discovery",
    "nearby",
    "opportunities",
    "trusted",
    "exploration",

    # Mixing / presentation
    "classify_candidate",
    "smart_mix",
    "public_discovery_metadata",
    "attach_public_discovery_metadata",

    # Orchestration
    "build_community_surface",
]