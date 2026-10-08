# backend/jumuiya/community/constants.py
"""
Jumuiya Community — shared constants and vocabulary.

Community is intentionally NOT designed as a generic social-media feed.

The Community Hub is organized around six ideas:

    PULSE
        What is useful to me right now?

    DISCOVERY
        Who / what / where can I connect with?

    GROUPS
        Persistent communities around real interests.

    THREADS
        Structured conversations around one matter.

    ACTIONS
        Move from conversation to something useful.

    TRUST
        Identity, ownership, reports, moderation and reputation.

This module contains vocabulary and immutable configuration only.
Decision-making belongs in policy.py.
Ranking/discovery logic belongs in discovery.py.
Database mutation/query logic remains in services.py.
"""

from __future__ import annotations


# ============================================================================
# CORE COMMUNITY IDENTITY
# ============================================================================

COMMUNITY_HUB = "community"

COMMUNITY_NAME = "Jumuiya Community"
COMMUNITY_VERSION = "2.0"

# Existing Jumuiya hubs that Community may discover content from.
DISCOVERABLE_HUBS = (
    "community",
    "biashara",
    "shamba",
    "elimu",
)

# Marketplace is treated as a connected action/discovery surface rather than
# as the primary Community social space.
CONNECTED_SURFACES = (
    "marketplace",
    "biashara",
    "shamba",
    "elimu",
    "community",
)


# ============================================================================
# COMMUNITY PILLARS
# ============================================================================

PULSE = "pulse"
DISCOVERY = "discovery"
GROUPS = "groups"
THREADS = "threads"
ACTIONS = "actions"
TRUST = "trust"

COMMUNITY_PILLARS = (
    PULSE,
    DISCOVERY,
    GROUPS,
    THREADS,
    ACTIONS,
    TRUST,
)


# ============================================================================
# PULSE
# ============================================================================
# Pulse answers:
# "What is useful to me right now?"
#
# It is NOT simply a chronological home feed.

PULSE_SURFACE = PULSE

PULSE_SIGNALS = (
    "relevance",
    "recency",
    "location",
    "interest",
    "activity",
    "need",
    "opportunity",
    "trust",
    "connection",
)

# High-value content should be capable of appearing in Pulse even when it
# has low engagement. This prevents a popularity-only algorithm.
PULSE_PRIORITY_SIGNALS = (
    "relevance",
    "usefulness",
    "freshness",
    "trust",
    "locality",
    "actionability",
)

# Pulse modes can later be exposed in the frontend without changing the
# underlying post model.
PULSE_MODES = (
    "for_you",
    "near_you",
    "following",
    "new",
    "opportunities",
)


# ============================================================================
# DISCOVERY
# ============================================================================
# Discovery answers:
# "Who / what / where can I connect with?"

DISCOVERY_SURFACE = DISCOVERY

DISCOVERY_ENTITY_TYPES = (
    "person",
    "business",
    "farmer",
    "school",
    "group",
    "thread",
    "post",
    "opportunity",
    "service",
    "product",
    "event",
    "resource",
    "project",
)

DISCOVERY_INTENTS = (
    "learn",
    "find",
    "connect",
    "buy",
    "sell",
    "hire",
    "work",
    "help",
    "join",
    "attend",
    "collaborate",
    "support",
)

DISCOVERY_SIGNALS = (
    "text_match",
    "topic_match",
    "interest_match",
    "hub_match",
    "location_match",
    "relationship",
    "recent_activity",
    "trust",
    "quality",
    "actionability",
)


# ============================================================================
# GROUPS
# ============================================================================
# Groups represent persistent communities around real interests, projects,
# places, professions, learning and shared objectives.

GROUPS_SURFACE = GROUPS

GROUP_TYPES = (
    "interest",
    "professional",
    "learning",
    "local",
    "institution",
    "project",
    "business",
    "agriculture",
    "support",
    "initiative",
)

GROUP_VISIBILITIES = (
    "public",
    "discoverable",
    "private",
)

GROUP_MEMBER_ROLES = (
    "owner",
    "admin",
    "moderator",
    "member",
)

GROUP_JOIN_MODES = (
    "open",
    "request",
    "invite_only",
)


# ============================================================================
# THREADS
# ============================================================================
# Threads are structured conversations around ONE matter.
#
# Unlike ordinary comments, a thread can represent a question, decision,
# help request, project discussion, or other focused matter.

THREADS_SURFACE = THREADS

THREAD_TYPES = (
    "discussion",
    "question",
    "help",
    "decision",
    "idea",
    "project",
    "announcement",
    "review",
)

THREAD_STATES = (
    "open",
    "active",
    "resolved",
    "closed",
)

THREAD_INTERACTION_TYPES = (
    "reply",
    "support",
    "agree",
    "disagree",
    "answer",
    "suggest",
    "follow",
)


# ============================================================================
# ACTIONS
# ============================================================================
# Actions are where Community moves beyond engagement.
#
# Example:
#   "School needs a mathematics teacher"
# is more useful when a user can:
#   APPLY
#   ENQUIRE
#   RESPOND
# rather than merely "Like" the post.

ACTIONS_SURFACE = ACTIONS

ACTION_TYPES = (
    "apply",
    "respond",
    "enquire",
    "join",
    "buy",
    "help",
    "attend",
)

# Optional utility actions that do not represent the primary business/action
# intent of a post.
SECONDARY_ACTION_TYPES = (
    "save",
    "follow",
    "share",
    "report",
)

ALL_ACTION_TYPES = ACTION_TYPES + SECONDARY_ACTION_TYPES

# Actions which should normally require an authenticated user.
AUTHENTICATED_ACTION_TYPES = (
    "apply",
    "respond",
    "enquire",
    "join",
    "buy",
    "help",
    "attend",
    "save",
    "follow",
    "report",
)


# ============================================================================
# POST TYPES
# ============================================================================
# These are intentionally semantic rather than generic social-media labels.

POST_TYPES = (
    "discussion",
    "question",
    "help_request",
    "opportunity",
    "offer",
    "request",
    "event",
    "announcement",
    "resource",
    "insight",
    "project",
    "update",
)

# Post types with an obvious action-oriented nature.
ACTIONABLE_POST_TYPES = (
    "opportunity",
    "offer",
    "request",
    "event",
    "help_request",
    "project",
)

# Post types that commonly benefit from structured conversation.
DISCUSSION_POST_TYPES = (
    "discussion",
    "question",
    "help_request",
    "insight",
    "project",
)


# ============================================================================
# CONTENT CATEGORIES
# ============================================================================
# Categories are deliberately broad. A future taxonomy/service can evolve
# without forcing the frontend to depend on hard-coded social-media concepts.

COMMUNITY_CATEGORIES = (
    "community",
    "business",
    "agriculture",
    "education",
    "technology",
    "career",
    "skills",
    "opportunities",
    "events",
    "projects",
    "local",
    "knowledge",
    "support",
    "ideas",
    "services",
)

# Topics can be user-defined through tags, but these represent useful
# high-level discovery dimensions.
DISCOVERY_CATEGORIES = (
    "people",
    "businesses",
    "services",
    "products",
    "opportunities",
    "events",
    "learning",
    "projects",
    "resources",
    "groups",
)


# ============================================================================
# VISIBILITY
# ============================================================================

VISIBILITY_PUBLIC = "public"
VISIBILITY_COMMUNITY = "community"
VISIBILITY_GROUP = "group"
VISIBILITY_PRIVATE = "private"

VISIBILITY_VALUES = (
    VISIBILITY_PUBLIC,
    VISIBILITY_COMMUNITY,
    VISIBILITY_GROUP,
    VISIBILITY_PRIVATE,
)


# ============================================================================
# TRUST
# ============================================================================
# Trust is a first-class Community concept.
#
# It should eventually combine identity verification, resource ownership,
# behavior, reporting, moderation and reputation.

TRUST_SURFACE = TRUST

TRUST_SIGNALS = (
    "identity",
    "ownership",
    "verification",
    "activity",
    "history",
    "reports",
    "moderation",
    "reputation",
)

TRUST_LEVELS = (
    "unknown",
    "basic",
    "established",
    "trusted",
    "verified",
)

REPORT_TYPES = (
    "spam",
    "fraud",
    "harassment",
    "hate",
    "misinformation",
    "impersonation",
    "unsafe",
    "copyright",
    "other",
)

REPORT_STATES = (
    "open",
    "reviewing",
    "resolved",
    "dismissed",
)

MODERATION_ACTIONS = (
    "warn",
    "limit",
    "hide",
    "remove",
    "lock",
    "suspend",
)


# ============================================================================
# REPUTATION
# ============================================================================
# Reputation must NOT simply mean "number of likes".
#
# The future policy/discovery engine can combine these signals into a trust
# score without exposing the raw formula to clients.

REPUTATION_SIGNALS = (
    "successful_actions",
    "helpful_contributions",
    "verified_identity",
    "verified_ownership",
    "quality_history",
    "positive_feedback",
    "community_contributions",
    "moderation_history",
)

REPUTATION_NEGATIVE_SIGNALS = (
    "confirmed_reports",
    "spam_activity",
    "fraud_activity",
    "abusive_behavior",
    "moderation_violations",
)


# ============================================================================
# CONTENT STATES
# ============================================================================

CONTENT_ACTIVE = "active"
CONTENT_DELETED = "deleted"
CONTENT_HIDDEN = "hidden"
CONTENT_ARCHIVED = "archived"
CONTENT_REPORTED = "reported"

CONTENT_STATES = (
    CONTENT_ACTIVE,
    CONTENT_DELETED,
    CONTENT_HIDDEN,
    CONTENT_ARCHIVED,
    CONTENT_REPORTED,
)


# ============================================================================
# DISCOVERY RESULT STATES
# ============================================================================

DISCOVERY_ACTIVE = "active"
DISCOVERY_RELEVANT = "relevant"
DISCOVERY_RECOMMENDED = "recommended"
DISCOVERY_TRENDING = "trending"
DISCOVERY_NEARBY = "nearby"


# ============================================================================
# RELATIONSHIPS
# ============================================================================
# These relationships are intentionally broader than "friend/follower".

RELATIONSHIP_TYPES = (
    "following",
    "member",
    "participant",
    "owner",
    "collaborator",
    "customer",
    "teacher",
    "student",
    "farmer",
    "business_owner",
    "community_contributor",
)


# ============================================================================
# SOURCE TYPES
# ============================================================================
# Existing services.py already supports cross-hub source entities.
# Keep the vocabulary centralized for policy.py/discovery.py.

SOURCE_HUBS = (
    "community",
    "biashara",
    "shamba",
    "elimu",
    "marketplace",
)

SOURCE_ENTITY_TYPES = (
    "community_post",
    "business",
    "product",
    "farmer",
    "farm",
    "crop",
    "harvest",
    "education_profile",
    "school",
    "lesson",
    "assignment",
    "cbc_project",
    "listing",
)


# ============================================================================
# SORT / FEED STRATEGIES
# ============================================================================

SORT_RECENT = "recent"
SORT_RELEVANT = "relevant"
SORT_NEARBY = "nearby"
SORT_ACTIONABLE = "actionable"
SORT_TRUSTED = "trusted"
SORT_DISCOVERY = "discovery"

SORT_MODES = (
    SORT_RELEVANT,
    SORT_RECENT,
    SORT_NEARBY,
    SORT_ACTIONABLE,
    SORT_TRUSTED,
    SORT_DISCOVERY,
)


# ============================================================================
# LINK / ACTION TARGET POLICY
# ============================================================================
# policy.py will enforce these rather than services.py trusting arbitrary
# client-provided values.

ALLOWED_ACTION_TARGET_SCHEMES = (
    "https",
)

# Relative application paths are preferred for internal actions.
ALLOW_RELATIVE_ACTION_TARGETS = True

# Internal paths that Community may safely reference.
# This is deliberately a prefix vocabulary, not an exact route list; policy.py
# should still validate the final target.
ALLOWED_INTERNAL_TARGET_PREFIXES = (
    "/community",
    "/jumuiya",
    "/biashara",
    "/shamba",
    "/elimu",
    "/marketplace",
)


# ============================================================================
# DEFAULTS / LIMITS
# ============================================================================
# These are shared values for future policy/discovery logic.
# services.py remains responsible for enforcing its existing operational
# limits until we wire these constants into it.

DEFAULT_PULSE_LIMIT = 20
DEFAULT_DISCOVERY_LIMIT = 20

MAX_PULSE_LIMIT = 50
MAX_DISCOVERY_LIMIT = 50

DEFAULT_SEARCH_LENGTH = 100

MAX_GROUP_NAME_LENGTH = 120
MAX_THREAD_TITLE_LENGTH = 200
MAX_ACTION_LABEL_LENGTH = 80


# ============================================================================
# HELPER SETS
# ============================================================================
# Frozensets make membership checks cheap and communicate immutability.

POST_TYPE_SET = frozenset(POST_TYPES)
ACTION_TYPE_SET = frozenset(ACTION_TYPES)
ALL_ACTION_TYPE_SET = frozenset(ALL_ACTION_TYPES)
VISIBILITY_SET = frozenset(VISIBILITY_VALUES)
HUB_SET = frozenset(DISCOVERABLE_HUBS)
SOURCE_HUB_SET = frozenset(SOURCE_HUBS)
SOURCE_ENTITY_TYPE_SET = frozenset(SOURCE_ENTITY_TYPES)
TRUST_LEVEL_SET = frozenset(TRUST_LEVELS)
GROUP_TYPE_SET = frozenset(GROUP_TYPES)
THREAD_TYPE_SET = frozenset(THREAD_TYPES)


__all__ = [
    # Core
    "COMMUNITY_HUB",
    "COMMUNITY_NAME",
    "COMMUNITY_VERSION",
    "DISCOVERABLE_HUBS",
    "CONNECTED_SURFACES",

    # Pillars
    "PULSE",
    "DISCOVERY",
    "GROUPS",
    "THREADS",
    "ACTIONS",
    "TRUST",
    "COMMUNITY_PILLARS",

    # Pulse
    "PULSE_SURFACE",
    "PULSE_SIGNALS",
    "PULSE_PRIORITY_SIGNALS",
    "PULSE_MODES",

    # Discovery
    "DISCOVERY_SURFACE",
    "DISCOVERY_ENTITY_TYPES",
    "DISCOVERY_INTENTS",
    "DISCOVERY_SIGNALS",

    # Groups
    "GROUPS_SURFACE",
    "GROUP_TYPES",
    "GROUP_VISIBILITIES",
    "GROUP_MEMBER_ROLES",
    "GROUP_JOIN_MODES",

    # Threads
    "THREADS_SURFACE",
    "THREAD_TYPES",
    "THREAD_STATES",
    "THREAD_INTERACTION_TYPES",

    # Actions
    "ACTIONS_SURFACE",
    "ACTION_TYPES",
    "SECONDARY_ACTION_TYPES",
    "ALL_ACTION_TYPES",
    "AUTHENTICATED_ACTION_TYPES",

    # Posts
    "POST_TYPES",
    "ACTIONABLE_POST_TYPES",
    "DISCUSSION_POST_TYPES",

    # Categories
    "COMMUNITY_CATEGORIES",
    "DISCOVERY_CATEGORIES",

    # Visibility
    "VISIBILITY_PUBLIC",
    "VISIBILITY_COMMUNITY",
    "VISIBILITY_GROUP",
    "VISIBILITY_PRIVATE",
    "VISIBILITY_VALUES",

    # Trust
    "TRUST_SURFACE",
    "TRUST_SIGNALS",
    "TRUST_LEVELS",
    "REPORT_TYPES",
    "REPORT_STATES",
    "MODERATION_ACTIONS",

    # Reputation
    "REPUTATION_SIGNALS",
    "REPUTATION_NEGATIVE_SIGNALS",

    # Content states
    "CONTENT_ACTIVE",
    "CONTENT_DELETED",
    "CONTENT_HIDDEN",
    "CONTENT_ARCHIVED",
    "CONTENT_REPORTED",
    "CONTENT_STATES",

    # Discovery states
    "DISCOVERY_ACTIVE",
    "DISCOVERY_RELEVANT",
    "DISCOVERY_RECOMMENDED",
    "DISCOVERY_TRENDING",
    "DISCOVERY_NEARBY",

    # Relationships
    "RELATIONSHIP_TYPES",

    # Sources
    "SOURCE_HUBS",
    "SOURCE_ENTITY_TYPES",

    # Sorting
    "SORT_RECENT",
    "SORT_RELEVANT",
    "SORT_NEARBY",
    "SORT_ACTIONABLE",
    "SORT_TRUSTED",
    "SORT_DISCOVERY",
    "SORT_MODES",

    # Target security
    "ALLOWED_ACTION_TARGET_SCHEMES",
    "ALLOW_RELATIVE_ACTION_TARGETS",
    "ALLOWED_INTERNAL_TARGET_PREFIXES",

    # Limits
    "DEFAULT_PULSE_LIMIT",
    "DEFAULT_DISCOVERY_LIMIT",
    "MAX_PULSE_LIMIT",
    "MAX_DISCOVERY_LIMIT",
    "DEFAULT_SEARCH_LENGTH",
    "MAX_GROUP_NAME_LENGTH",
    "MAX_THREAD_TITLE_LENGTH",
    "MAX_ACTION_LABEL_LENGTH",

    # Sets
    "POST_TYPE_SET",
    "ACTION_TYPE_SET",
    "ALL_ACTION_TYPE_SET",
    "VISIBILITY_SET",
    "HUB_SET",
    "SOURCE_HUB_SET",
    "SOURCE_ENTITY_TYPE_SET",
    "TRUST_LEVEL_SET",
    "GROUP_TYPE_SET",
    "THREAD_TYPE_SET",
]