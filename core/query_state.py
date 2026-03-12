"""
core/query_state.py
Canonical query state — the authoritative representation of accumulated user intent.

Architectural invariants (all enforced by tests in tests/test_query_state.py):
  - QueryState is the single source of truth.
    accumulated_params is derived output only. No business logic may mutate it directly.
  - turn is monotonic across the full chat session. It NEVER resets.
  - search_id is the boundary between searches. Minted once per start_new_search().
  - broaden_geo() NEVER mutates original_anchor.
  - replace_geo() ALWAYS resets broadening_history.
  - pending_action is cleared after ACCEPT and REJECT.
  - to_cssl_params() is an internal CSSL adapter, not the general output of QueryState.
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict  # type: ignore


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Provenance(Enum):
    EXPLICIT         = "explicit"          # user stated directly this turn
    INFERRED         = "inferred"          # extracted by intent parser
    SYSTEM_BROADENED = "system_broadened"  # set by a geo/category broadening action
    CARRIED          = "carried"           # interpretation: field.turn < current_turn
    DEFAULT          = "default"           # system-applied default


class PendingActionType(Enum):
    GEO_BROADEN_PROVINCE = "geo_broaden_province"
    GEO_BROADEN_RADIUS   = "geo_broaden_radius"
    GEO_BROADEN          = "geo_broaden"
    ADD_FILTER           = "add_filter"
    REMOVE_FILTER        = "remove_filter"
    CLARIFY              = "clarify"


class ActionResolution(Enum):
    ACCEPT    = "accept"     # execute mutation, clear pending_action
    REJECT    = "reject"     # clear pending_action only
    MODIFY    = "modify"     # clear old action, treat turn as normal intent
    UNRELATED = "unrelated"  # keep action one more turn unless expired


# ---------------------------------------------------------------------------
# GeoScope — documents the shape contract for geo state dicts.
# Both original_anchor and current_scope use this shape.
# ---------------------------------------------------------------------------

class GeoScope(TypedDict, total=False):
    city:             str
    cities:           list
    province:         str
    lat:              float
    lon:              float
    radius_km:        int
    normalized_label: str    # display label, e.g. "Toronto area"


# ---------------------------------------------------------------------------
# FieldValue
# Wraps every accumulated scalar/list field with provenance metadata.
# Written once when set. "Is this being carried?" is derived: field.turn < current_turn.
# Do not eagerly rewrite fields with CARRIED provenance on every turn.
# ---------------------------------------------------------------------------

@dataclass
class FieldValue:
    value:      Any
    provenance: Provenance
    turn:       int
    confidence: float | None = None   # populated where meaningful (e.g. inferred geo)
    source:     str          = ""     # e.g. "fuzzy_preprocessor", "intent_parser"


# ---------------------------------------------------------------------------
# GeoState — structured geographic context.
# ---------------------------------------------------------------------------

@dataclass
class GeoState:
    # First location the user gave — set once by replace_geo(), never touched by broaden_geo().
    # Reset only by start_new_search() or replace_geo().
    original_anchor: GeoScope | None = None

    # Effective search area CSSL uses right now.
    current_scope: GeoScope = field(default_factory=dict)  # type: ignore[arg-type]

    # Ordered history of broadening steps applied this search.
    # Each entry: {"type": str, "from": GeoScope, "to": GeoScope,
    #              "turn": int, "action_id": str}
    broadening_history: list[dict] = field(default_factory=list)

    # How current_scope came to be set.
    scope_provenance: Provenance = Provenance.EXPLICIT


# ---------------------------------------------------------------------------
# PendingAction — replaces the loose pending_suggestion dict.
# ---------------------------------------------------------------------------

@dataclass
class PendingAction:
    type:               PendingActionType
    parameters:         dict                        # type-specific payload
    suggested_at_turn:  int
    action_id:          str                         = field(
                            default_factory=lambda: uuid.uuid4().hex[:8])
    message_shown:      str                         = ""
    resolution:         ActionResolution | None     = None
    expires_after_turn: int | None                  = None  # auto-clear if unresolved


# ---------------------------------------------------------------------------
# QueryState — canonical accumulated user intent.
# ---------------------------------------------------------------------------

def _new_search_id() -> str:
    return uuid.uuid4().hex[:8]


# All FieldValue fields on QueryState — used by start_new_search() and from_flat_dict().
_CLEARABLE_FIELDS = (
    "tags", "exclude_tags", "traits", "type",
    "age_from", "age_to", "gender",
    "cost_max", "cost_sensitive", "is_special_needs",
    "is_virtual", "language_immersion",
    "date_from", "date_to",
)


@dataclass
class QueryState:
    # --- Activity ---
    tags:               FieldValue | None = None   # list[str] — activity tag slugs
    exclude_tags:       FieldValue | None = None   # list[str]
    traits:             FieldValue | None = None   # list[str]
    type:               FieldValue | None = None   # "Day" | "Overnight"

    # --- Demographics ---
    age_from:           FieldValue | None = None   # int
    age_to:             FieldValue | None = None   # int
    gender:             FieldValue | None = None   # "Boys" | "Girls" | "Coed"

    # --- Cost / flags ---
    cost_max:           FieldValue | None = None   # int (CAD)
    cost_sensitive:     FieldValue | None = None   # bool
    is_special_needs:   FieldValue | None = None   # bool
    is_virtual:         FieldValue | None = None   # bool
    language_immersion: FieldValue | None = None   # str

    # --- Dates ---
    date_from:          FieldValue | None = None   # "YYYY-MM-DD"
    date_to:            FieldValue | None = None   # "YYYY-MM-DD"

    # --- Geography (structured sub-object) ---
    geo: GeoState = field(default_factory=GeoState)

    # --- Pending action ---
    pending_action: PendingAction | None = None

    # --- Session identity ---
    search_id: str = field(default_factory=_new_search_id)
    turn: int = 0   # monotonic across full chat session — NEVER reset

    # --- Mutation audit trail (developer-only, capped at 50 entries) ---
    _audit: deque = field(default_factory=lambda: deque(maxlen=50))

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _log(self, method: str, field_name: str, old: Any, new: Any,
             provenance: Provenance | None = None) -> None:
        """Append an entry to the mutation audit trail."""
        self._audit.append({
            "turn":       self.turn,
            "method":     method,
            "field":      field_name,
            "old":        old,
            "new":        new,
            "provenance": provenance.value if provenance else None,
        })

    # -----------------------------------------------------------------------
    # Mutation methods — ALL state changes go through these.
    # Do not set fields directly from outside this class.
    # -----------------------------------------------------------------------

    def apply_inferred_update(self, field_name: str, value: Any,
                               confidence: float | None = None,
                               source: str = "intent_parser") -> None:
        """
        Set a field from intent parser extraction.
        Provenance = INFERRED.
        """
        old = getattr(self, field_name)
        old_val = old.value if old is not None else None
        fv = FieldValue(
            value=value,
            provenance=Provenance.INFERRED,
            turn=self.turn,
            confidence=confidence,
            source=source,
        )
        setattr(self, field_name, fv)
        self._log("apply_inferred_update", field_name, old_val, value, Provenance.INFERRED)

    def apply_explicit_update(self, field_name: str, value: Any,
                               source: str = "") -> None:
        """
        Set a field from an explicit user action (e.g. filter sidebar, button click).
        Provenance = EXPLICIT.
        """
        old = getattr(self, field_name)
        old_val = old.value if old is not None else None
        fv = FieldValue(
            value=value,
            provenance=Provenance.EXPLICIT,
            turn=self.turn,
            confidence=1.0,
            source=source,
        )
        setattr(self, field_name, fv)
        self._log("apply_explicit_update", field_name, old_val, value, Provenance.EXPLICIT)

    def clear_field(self, field_name: str) -> None:
        """
        Clear a single FieldValue field to None.
        This is the only correct path for clearing a field.
        Do not set fields to None directly from outside this class.
        """
        old = getattr(self, field_name)
        old_val = old.value if old is not None else None
        setattr(self, field_name, None)
        self._log("clear_field", field_name, old_val, None)

    def clear_activity(self) -> None:
        """
        Clear activity-related fields while preserving geo context.
        Use when the user starts a new activity search in the same location.
        """
        for f in ("tags", "exclude_tags", "type", "date_from", "date_to"):
            if getattr(self, f) is not None:
                self.clear_field(f)
        self._log("clear_activity", "activity_group", None, None)

    def clear_geo(self) -> None:
        """
        Clear geographic current_scope. Preserves original_anchor.
        Used internally; prefer replace_geo() or broaden_geo() for explicit changes.
        """
        old_scope = dict(self.geo.current_scope)
        self.geo.current_scope = {}  # type: ignore[assignment]
        self.geo.scope_provenance = Provenance.DEFAULT
        self._log("clear_geo", "geo.current_scope", old_scope, None)

    def replace_geo(self, scope: GeoScope,
                    provenance: Provenance = Provenance.INFERRED,
                    confidence: float | None = None) -> None:
        """
        Explicit location replacement — direct geo change from the intent parser.

        - Replaces both original_anchor and current_scope.
        - ALWAYS resets broadening_history (invariant).

        Call from merge_intent() for direct geo changes.
        NEVER call from pending action acceptance — use broaden_geo() instead.
        """
        old_anchor = dict(self.geo.original_anchor) if self.geo.original_anchor else None
        old_scope = dict(self.geo.current_scope)
        old_history_len = len(self.geo.broadening_history)

        self.geo.original_anchor = dict(scope) | {"turn": self.turn}  # type: ignore
        self.geo.current_scope = scope
        self.geo.broadening_history = []   # invariant: always reset
        self.geo.scope_provenance = provenance

        self._log("replace_geo", "geo.original_anchor", old_anchor,
                  dict(self.geo.original_anchor), provenance)
        self._log("replace_geo", "geo.current_scope", old_scope, dict(scope), provenance)
        if old_history_len:
            self._log("replace_geo", "geo.broadening_history",
                      f"{old_history_len} entries", "cleared", provenance)

    def broaden_geo(self, action: PendingAction) -> None:
        """
        Apply a geo broadening from a pending action acceptance.

        - Appends to broadening_history.
        - Updates current_scope with the broader scope.
        - NEVER touches original_anchor (invariant).

        Call ONLY from _apply_pending_action() on ACCEPT. Never from merge_intent().
        """
        if action.type not in (
            PendingActionType.GEO_BROADEN,
            PendingActionType.GEO_BROADEN_PROVINCE,
            PendingActionType.GEO_BROADEN_RADIUS,
        ):
            return

        prior_scope = dict(self.geo.current_scope)

        if action.type == PendingActionType.GEO_BROADEN_PROVINCE:
            new_scope: GeoScope = {"province": action.parameters.get("to_province")}
        elif action.type == PendingActionType.GEO_BROADEN:
            new_scope = {
                "city":     action.parameters.get("to_city"),
                "province": action.parameters.get("to_province"),
            }
        else:  # GEO_BROADEN_RADIUS
            new_scope = {
                "lat":       action.parameters.get("lat"),
                "lon":       action.parameters.get("lon"),
                "radius_km": action.parameters.get("radius_km"),
            }

        # Record history before mutating.
        self.geo.broadening_history.append({
            "type":      action.type.value,
            "from":      prior_scope,
            "to":        dict(new_scope),
            "turn":      self.turn,
            "action_id": action.action_id,
        })
        self.geo.current_scope = new_scope
        self.geo.scope_provenance = Provenance.SYSTEM_BROADENED

        # original_anchor is NOT touched — this is the core architectural invariant.
        self._log("broaden_geo", "geo.current_scope", prior_scope,
                  dict(new_scope), Provenance.SYSTEM_BROADENED)

    def set_pending_action(self, action: PendingAction) -> None:
        """Store a pending action for resolution on the next turn."""
        old_id = self.pending_action.action_id if self.pending_action else None
        self.pending_action = action
        self._log("set_pending_action", "pending_action", old_id, action.action_id)

    def clear_pending_action(self, resolution: ActionResolution) -> None:
        """Resolve and clear the pending action."""
        if self.pending_action:
            self.pending_action.resolution = resolution
            old_id = self.pending_action.action_id
            self.pending_action = None
            self._log("clear_pending_action", "pending_action",
                      old_id, f"cleared:{resolution.value}")

    def expire_pending_action_if_stale(self) -> None:
        """
        Auto-clear pending action if it has exceeded its expiry turn.
        Call at the start of each turn before action resolution.
        """
        if (self.pending_action
                and self.pending_action.expires_after_turn is not None
                and self.turn > self.pending_action.expires_after_turn):
            self._log("expire_pending_action", "pending_action",
                      self.pending_action.action_id, "expired")
            self.pending_action = None

    def start_new_search(self) -> None:
        """
        Reset to a fresh search state. Mints a new search_id.
        Clears all fields, geo, and pending action.

        DOES NOT reset turn — turn is monotonic across the full session.
        """
        old_search_id = self.search_id

        for f in _CLEARABLE_FIELDS:
            setattr(self, f, None)

        self.geo = GeoState()
        self.pending_action = None
        self.search_id = _new_search_id()

        self._log("start_new_search", "search_id", old_search_id, self.search_id)

    # -----------------------------------------------------------------------
    # Output methods
    # -----------------------------------------------------------------------

    def to_cssl_params(self) -> dict:
        """
        Produce a flat dict in the shape of the legacy accumulated_params.
        This is an INTERNAL CSSL ADAPTER — not the general output of QueryState.
        Phase 1: all downstream consumers receive this dict.
        Phase 2+: orchestration logic will consume QueryState directly.
        """
        p: dict = {}

        # Activity
        if self.tags is not None:
            p["tags"] = self.tags.value
        if self.exclude_tags is not None:
            p["exclude_tags"] = self.exclude_tags.value
        if self.traits is not None:
            p["traits"] = self.traits.value
        if self.type is not None:
            p["type"] = self.type.value

        # Demographics
        if self.age_from is not None:
            p["age_from"] = self.age_from.value
        if self.age_to is not None:
            p["age_to"] = self.age_to.value
        if self.gender is not None:
            p["gender"] = self.gender.value

        # Cost / flags
        if self.cost_max is not None:
            p["cost_max"] = self.cost_max.value
        if self.cost_sensitive is not None and self.cost_sensitive.value:
            p["cost_sensitive"] = self.cost_sensitive.value
        if self.is_special_needs is not None and self.is_special_needs.value:
            p["is_special_needs"] = self.is_special_needs.value
        if self.is_virtual is not None and self.is_virtual.value:
            p["is_virtual"] = self.is_virtual.value
        if self.language_immersion is not None:
            p["language_immersion"] = self.language_immersion.value

        # Dates
        if self.date_from is not None:
            p["date_from"] = self.date_from.value
        if self.date_to is not None:
            p["date_to"] = self.date_to.value

        # Geography — flatten current_scope respecting CSSL's priority chain.
        # Only emit keys with actual values. Never emit None-valued keys.
        scope = self.geo.current_scope
        if scope.get("lat") is not None and scope.get("lon") is not None:
            p["lat"] = scope["lat"]
            p["lon"] = scope["lon"]
            p["radius_km"] = scope.get("radius_km") or 25
        if scope.get("cities"):
            p["cities"] = scope["cities"]
        if scope.get("city"):
            p["city"] = scope["city"]
        if scope.get("province"):
            p["province"] = scope["province"]

        return p

    def to_session_context_dict(self) -> dict:
        """
        Clean flat dict of search dimensions for the intent parser SESSION_CONTEXT.
        No provenance metadata — keeps the prompt readable and unchanged from today.
        """
        return self.to_cssl_params()

    @classmethod
    def from_flat_dict(cls, d: dict, turn: int = 0) -> "QueryState":
        """
        Build a QueryState from a legacy accumulated_params flat dict.
        All fields get provenance=CARRIED since origin is unknown at migration time.
        Used for: disambiguation choice restoration, surprise-me reset, session migration.
        """
        qs = cls()
        qs.turn = turn

        scalar_fields = {
            "type", "gender", "language_immersion",
            "age_from", "age_to", "cost_max",
            "date_from", "date_to",
        }
        bool_fields = {"cost_sensitive", "is_special_needs", "is_virtual"}
        list_fields = {"tags", "exclude_tags", "traits"}
        geo_keys    = {"city", "cities", "province", "lat", "lon", "radius_km"}

        scope: dict = {}
        for key, val in d.items():
            if key in geo_keys:
                if val is not None and val != [] and val != 0:
                    scope[key] = val
            elif key in list_fields and val:
                setattr(qs, key, FieldValue(
                    value=val, provenance=Provenance.CARRIED, turn=turn))
            elif key in bool_fields and val:
                setattr(qs, key, FieldValue(
                    value=val, provenance=Provenance.CARRIED, turn=turn))
            elif key in scalar_fields and val is not None:
                setattr(qs, key, FieldValue(
                    value=val, provenance=Provenance.CARRIED, turn=turn))

        if scope:
            qs.geo.original_anchor = dict(scope) | {"turn": turn}  # type: ignore
            qs.geo.current_scope = scope  # type: ignore[assignment]

        return qs

    def get_audit_log(self) -> list[dict]:
        """Return the mutation audit trail as a list. Developer / trace use only."""
        return list(self._audit)
