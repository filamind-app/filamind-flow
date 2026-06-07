"""DB-2 linking backbone — a precomputed cross-entity graph over the hardware DB.

The reference DB's relationships were islands: ``manufacturer`` was free-text (only
~73 % of entity rows matched the directory exactly), the MCU lived as free text inside
a board's ``specs``, and board↔driver compatibility was buried in a ``Supported drivers``
spec string. This module turns those into a real graph, built once at load:

* **Manufacturer canonicalisation** — every directory entry gets a stable ``manufacturer_id``
  slug plus auto-derived aliases (parenthetical acronyms, ``/``-separated brands, token
  fallbacks); recurring real brands missing from the directory are derived as entities. Each
  entity's free-text ``manufacturer`` resolves to an id (or ``None`` for junk / one-offs).
* **MCU as a first-class entity** — board ``specs.MCU`` strings are parsed with a *whitelist*
  of chip-family rules (so package fragments / host SoCs / noise never become fake MCUs) and
  normalised to a canonical part (e.g. ``STM32F407VET6`` → ``stm32f407``).
* **Edges** use composite keys ``"<type>:<id>"`` (ids are not globally unique across types —
  ``sovol-sv08`` is both a board and a host) and are stored as an in-memory adjacency map for
  O(1) :func:`related` lookups.

Pure: every function takes its data as arguments, so it is unit-testable in isolation and
imported by ``reference_data`` (which owns the single load) without a cycle.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

# ── slug / manufacturer normalisation ─────────────────────────────────────────
_REPL = "�"  # the unicode replacement char that leaks in from bad source encodings

#: Generic corporate / descriptor tokens dropped when comparing brand names.
_MAN_STOP = {
    "motors",
    "motor",
    "industries",
    "industrial",
    "technology",
    "technologies",
    "tech",
    "devices",
    "device",
    "electronics",
    "electronic",
    "inc",
    "incorporated",
    "ltd",
    "limited",
    "llc",
    "gmbh",
    "co",
    "company",
    "corp",
    "corporation",
    "international",
    "intl",
    "lab",
    "labs",
    "laboratory",
    "semi",
    "semiconductor",
    "project",
    "denki",
    "class",
    "generic",
    "open",
    "clone",
}


#: Common English / product-line words that, even when they happen to be a single-token directory
#: candidate (e.g. MatterHackers' "PRO" / "Build" lines), must never become an unambiguous brand
#: token — too many unrelated free-text manufacturers contain them.
_GENERIC_FALLBACK_BLOCK = {
    "pro",
    "build",
    "plus",
    "mini",
    "max",
    "lite",
    "smart",
    "power",
    "plastic",
    "module",
    "pcb",
    "micro",
    "nano",
    "one",
    "core",
    "flex",
    "prime",
    "ultra",
    "base",
    "kit",
    "board",
    "motor",
}


def slugify(text: str) -> str:
    """A stable lowercase ``a-z0-9-`` id slug from the primary part of a name."""
    base = re.sub(r"\(.*?\)", "", str(text)).split("/")[0].strip().lower()
    base = base.replace(_REPL, "")
    slug = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
    return slug or "unknown"


def manufacturer_candidates(name: str) -> list[str]:
    """Normalised brand-candidate strings for a manufacturer name.

    Splits parentheticals and ``/``-separated co-brands into separate candidates, drops
    generic corporate tokens, and collapses punctuation — so ``"OMC / StepperOnline"``
    yields ``["omc", "stepperonline"]`` and ``"BIGTREETECH (BTT)"`` yields
    ``["bigtreetech", "btt"]``.
    """
    s = str(name).lower().replace(_REPL, "")
    parentheticals = re.findall(r"\((.*?)\)", s)
    base = re.sub(r"\(.*?\)", "", s)
    out: list[str] = []
    for chunk in [base, *parentheticals]:
        for piece in chunk.split("/"):
            piece = piece.replace("&", " and ")
            piece = re.sub(r"[^a-z0-9 ]+", " ", piece)
            toks = [t for t in piece.split() if t and t not in _MAN_STOP]
            if toks:
                out.append(" ".join(toks))
    return out


class ManufacturerResolver:
    """Resolves a free-text manufacturer string to a canonical ``manufacturer_id``.

    Built from the directory: an exact alias index (full normalised brand candidates, also keyed
    space-collapsed so ``MeanWell`` finds ``Mean Well``) plus an *unambiguous single-token-brand*
    fallback. Only a candidate that is **itself a single token** seeds that fallback — descriptor
    words buried inside a multi-word brand name (``module`` in "Toshiba-class (module brand)",
    ``smart`` in "Smart Materials 3D") must never be promoted to a brand identifier, or unrelated
    parts whose free-text manufacturer merely *contains* that word would link to the wrong brand.
    Junk and one-off strings resolve to ``None`` — they keep their free-text label but gain no link.
    """

    def __init__(self, directory: list[dict[str, Any]]) -> None:
        self._id_to_name: dict[str, str] = {}
        self._alias_to_id: dict[str, str] = {}
        token_owner: dict[str, set[str]] = {}
        used_slugs: set[str] = set()
        for row in directory:
            name = str(row.get("name", "")).strip()
            if not name:
                continue
            mid = slugify(name)
            while mid in used_slugs and self._id_to_name.get(mid) != name:
                mid = f"{mid}-x"
            used_slugs.add(mid)
            self._id_to_name.setdefault(mid, name)
            for cand in manufacturer_candidates(name):
                self._alias_to_id.setdefault(cand, mid)
                self._alias_to_id.setdefault(cand.replace(" ", ""), mid)
                # only single-token brand candidates (and not generic words) seed the fallback
                if " " not in cand and len(cand) >= 3 and cand not in _GENERIC_FALLBACK_BLOCK:
                    token_owner.setdefault(cand, set()).add(mid)
        # a token is a usable fallback only if it points at a single directory id
        self._uniq_token: dict[str, str] = {
            tok: next(iter(ids)) for tok, ids in token_owner.items() if len(ids) == 1
        }

    def id_name(self, manufacturer_id: str) -> str | None:
        return self._id_to_name.get(manufacturer_id)

    def resolve(self, text: str) -> str | None:
        cands = manufacturer_candidates(text)
        for cand in cands:
            hit = self._alias_to_id.get(cand) or self._alias_to_id.get(cand.replace(" ", ""))
            if hit:
                return hit
        for cand in cands:
            for tok in cand.split():
                if tok in self._alias_to_id:
                    return self._alias_to_id[tok]
                if tok in self._uniq_token:
                    return self._uniq_token[tok]
        return None


#: Strings that denote "no single maker" (community / open / generic / clone). These must never
#: become a manufacturer link-hub — neither when derived from usage nor from the directory. All
#: alternatives are word-bounded so a real brand like ``ReprapWorld`` is NOT caught by ``reprap``.
_PLACEHOLDER_RE = re.compile(
    r"\bgeneric\b|\bvarious\b|\bunknown\b|\bdiy\b|\bcustom\b|\breprap\b|\baliexpress\b|"
    r"\bcommunity\b|open[- ]?source|open hardware|\bclone\b|many vendors",
    re.I,
)


def _is_placeholder_manufacturer(name: str) -> bool:
    """True if a manufacturer name is a 'no single maker' placeholder, not a real brand.

    Only the **primary** brand chunk (first ``/``-separated, paren-stripped part — the part the
    slug is built from) is tested, so a real brand with a placeholder-ish *co-brand* survives
    (e.g. "Aus3D / Reprapworld" → primary "Aus3D" → not a placeholder)."""
    primary = re.sub(r"\(.*?\)", "", str(name).replace(_REPL, "")).split("/")[0]
    return _PLACEHOLDER_RE.search(primary) is not None


def _is_plausible_brand(text: str) -> bool:
    """True if a residual (directory-unmatched) string looks like a real brand worth deriving
    an entity for — filters out numeric junk, spec fragments and encoding noise."""
    s = str(text).replace(_REPL, "").strip()
    if not s or s.isdigit():
        return False
    if not [t for t in re.findall(r"[A-Za-z]+", s) if len(t) >= 3]:
        return False
    if re.search(r"stallguard|sg2|sg4|tstep|compute|simulator|onboard|socketed", s, re.I):
        return False
    return not _is_placeholder_manufacturer(s)


# ── MCU canonicalisation (whitelist of chip-family rules) ──────────────────────
#: Ordered ``(compiled regex, family-builder)``. A board MCU token becomes an entity only if
#: it matches a rule — so package fragments (``ZGT6``), host SoCs (``RK3566``, ``CB1``) and
#: stray tokens (``NEMA23``, ``DDR3``) never create phantom MCUs. The regex's group(1) is the
#: canonical core (→ lowercase ``mcu_id`` + uppercase display name).
def _stm_family(core: str) -> str:
    # core like STM32F407 / STM32G0B1 / STM32H743 → "STM32F4" / "STM32G0" / "STM32H7"
    return core[:7].upper()


#: Each rule's capture group(1) is already the exact canonical core (incl. any meaningful
#: prefix such as ``AT`` for AVR; the optional ``(?:AT)?`` on SAM strips the redundant Atmel
#: prefix). ``family`` is a coarse grouping label.
_MCU_RULES: list[tuple[re.Pattern[str], Any]] = [
    (re.compile(r"^(RP\d{4})$"), lambda m: "RP2xxx"),
    (re.compile(r"^(STM32[FGHL][0-9A-Z]{2}[0-9])"), lambda m: _stm_family(m.group(1))),
    (re.compile(r"^(GD32[A-Z][0-9A-Z]{2}[0-9])"), lambda m: "GD32"),
    (re.compile(r"^(APM32[A-Z][0-9A-Z]{2}[0-9])"), lambda m: "APM32"),
    (re.compile(r"^(LPC\d{4})$"), lambda m: "LPC17xx"),
    (re.compile(r"^(HC32[A-Z]\d{3})"), lambda m: "HC32"),
    (re.compile(r"^(AT(?:MEGA|90USB)\w+)"), lambda m: "AVR"),
    (re.compile(r"^(?:AT)?(SAM[CDESV]\d{2})"), lambda m: "SAM"),
    (re.compile(r"^(?:AT)?(SAM\d[A-Z]\d[A-Z])"), lambda m: "SAM"),
    (re.compile(r"^(ESP32)"), lambda m: "ESP32"),
]


def normalize_mcu(token: str) -> tuple[str, str, str] | None:
    """``(mcu_id, display, family)`` for a raw chip token, or ``None`` if it is not a
    recognised MCU family (noise / host SoC / package fragment)."""
    t = str(token).upper().strip()
    for rgx, fam in _MCU_RULES:
        m = rgx.match(t)
        if m:
            core = m.group(1).upper()
            return core.lower(), core, fam(m)
    return None


def board_mcu_ids(board: dict[str, Any]) -> list[tuple[str, str, str]]:
    """Distinct ``(mcu_id, display, family)`` tuples a board's ``specs.MCU`` references."""
    spec = board.get("specs", {})
    raw = str(spec.get("MCU", "")) if isinstance(spec, dict) else ""
    seen: dict[str, tuple[str, str, str]] = {}
    for tok in re.findall(r"[A-Za-z]{2,}[0-9][0-9A-Za-z]*", raw):
        norm = normalize_mcu(tok)
        if norm and norm[0] not in seen:
            seen[norm[0]] = norm
    return list(seen.values())


# ── the graph ─────────────────────────────────────────────────────────────────
@dataclass
class LinkGraph:
    """The fully built, immutable link graph (composite-key adjacency + canonical entities)."""

    manufacturers: list[dict[str, Any]] = field(default_factory=list)
    manufacturer_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    mcus: list[dict[str, Any]] = field(default_factory=list)
    mcu_by_id: dict[str, dict[str, Any]] = field(default_factory=dict)
    summaries: dict[str, dict[str, Any]] = field(default_factory=dict)
    adjacency: dict[str, list[dict[str, str]]] = field(default_factory=dict)
    entity_manufacturer_id: dict[str, str] = field(default_factory=dict)


_ENTITY_TYPES = ("board", "driver", "motor", "host", "catalog")
#: Maps the plural path segment used by the routes to the singular graph type.
PLURAL_TO_TYPE = {
    "boards": "board",
    "drivers": "driver",
    "motors": "motor",
    "hosts": "host",
    "catalog": "catalog",
    "manufacturers": "manufacturer",
    "mcus": "mcu",
}


def _id_field(etype: str) -> str:
    return "catalog_id" if etype == "catalog" else f"{etype}_id"


def _summary(etype: str, row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "type": etype,
        "id": str(row.get(_id_field(etype), "")),
        "name": str(row.get("display_name") or row.get("name") or row.get("model") or "") or None,
        "manufacturer": row.get("manufacturer") or None,
    }
    for extra in ("boardClass", "interface", "nema", "kind", "category"):
        if row.get(extra):
            out[extra] = row[extra]
    return out


def build_links(
    *,
    boards: list[dict[str, Any]],
    drivers: list[dict[str, Any]],
    motors: list[dict[str, Any]],
    hosts: list[dict[str, Any]],
    catalog: dict[str, list[dict[str, Any]]],
    manufacturers: list[dict[str, Any]],
) -> LinkGraph:
    """Build the canonical manufacturer + MCU entities and the cross-entity edge graph."""
    g = LinkGraph()
    resolver = ManufacturerResolver(manufacturers)

    grouped: dict[str, list[dict[str, Any]]] = {
        "board": boards,
        "driver": drivers,
        "motor": motors,
        "host": hosts,
        "catalog": [e for rows in catalog.values() for e in rows],
    }

    # entity summaries + composite keys
    entity_keys: dict[str, str] = {}  # composite key -> manufacturer free-text (for derive pass)
    for etype, rows in grouped.items():
        for row in rows:
            eid = str(row.get(_id_field(etype), ""))
            if not eid:
                continue
            key = f"{etype}:{eid}"
            g.summaries[key] = _summary(etype, row)
            g.adjacency.setdefault(key, [])
            entity_keys[key] = str(row.get("manufacturer", "")).strip()

    # ── manufacturers: directory FIRST, then resolution, then derived recurring brands ──
    # canonical entities from the directory (skipping 'no single maker' placeholders)
    member_counts: Counter[str] = Counter()
    for row in manufacturers:
        name = str(row.get("name", "")).strip()
        if not name or _is_placeholder_manufacturer(name):
            continue
        mid = resolver.resolve(name) or slugify(name)
        if mid in g.manufacturer_by_id:
            continue
        ent = {
            "manufacturer_id": mid,
            "name": name,
            "country": row.get("country") or "",
            "website": row.get("website") or "",
            "specialty": row.get("specialty") or "",
            "categories": row.get("categories") or "",
            "aliases": sorted({c for c in manufacturer_candidates(name) if c != mid}),
            "origin": "directory",
            "memberCount": 0,
        }
        g.manufacturer_by_id[mid] = ent

    # resolution pass: an entity is "resolved" only if it maps to an id that actually MATERIALISED
    # as a manufacturer entity (a hit on an excluded placeholder / never-built id counts as a miss,
    # so a plausible brand can still be derived below instead of the link being silently dropped).
    residual: Counter[str] = Counter()
    resolved_for: dict[str, str | None] = {}
    for key, mfr in entity_keys.items():
        raw_mid = resolver.resolve(mfr) if mfr else None
        eff_mid = raw_mid if raw_mid in g.manufacturer_by_id else None
        resolved_for[key] = eff_mid
        if mfr and eff_mid is None and _is_plausible_brand(mfr):
            residual[mfr] += 1

    # derive entities for recurring real brands missing from the directory (count >= 2)
    derived_id: dict[str, str] = {}
    for brand, count in residual.items():
        if count < 2:
            continue
        mid = slugify(brand)
        while mid in g.manufacturer_by_id and g.manufacturer_by_id[mid]["name"] != brand:
            mid = f"{mid}-alt"
        derived_id[brand] = mid
        g.manufacturer_by_id.setdefault(
            mid,
            {
                "manufacturer_id": mid,
                "name": brand,
                "country": "",
                "website": "",
                "specialty": "",
                "categories": "",
                "aliases": sorted({c for c in manufacturer_candidates(brand) if c != mid}),
                "origin": "derived",
                "memberCount": 0,
            },
        )

    # ── MCU entities (from boards) ──
    mcu_archs: dict[str, Counter[str]] = {}
    for board in boards:
        spec = board.get("specs", {})
        arch = str(spec.get("Arch", "")).strip() if isinstance(spec, dict) else ""
        for mcu_id, display, family in board_mcu_ids(board):
            if mcu_id not in g.mcu_by_id:
                g.mcu_by_id[mcu_id] = {
                    "mcu_id": mcu_id,
                    "name": display,
                    "family": family,
                    "arch": None,
                    "boardCount": 0,
                }
            # only count clean, parenthetical-free arch strings as candidates
            if arch and "(" not in arch and len(arch) <= 40:
                mcu_archs.setdefault(mcu_id, Counter())[arch] += 1
    # pick each MCU's most-common clean arch (tie-break: shortest)
    for mcu_id, counts in mcu_archs.items():
        best = sorted(counts.items(), key=lambda kv: (-kv[1], len(kv[0])))
        if best:
            g.mcu_by_id[mcu_id]["arch"] = best[0][0]

    # mcu / manufacturer summaries
    for mid, ent in g.manufacturer_by_id.items():
        key = f"manufacturer:{mid}"
        g.summaries[key] = {"type": "manufacturer", "id": mid, "name": ent["name"]}
        g.adjacency.setdefault(key, [])
    for mcu_id, ent in g.mcu_by_id.items():
        key = f"mcu:{mcu_id}"
        g.summaries[key] = {
            "type": "mcu",
            "id": mcu_id,
            "name": ent["name"],
            "family": ent["family"],
        }
        g.adjacency.setdefault(key, [])

    # ── edges ──
    def link(a: str, b: str, rel_ab: str, rel_ba: str) -> None:
        g.adjacency.setdefault(a, []).append({"key": b, "rel": rel_ab})
        g.adjacency.setdefault(b, []).append({"key": a, "rel": rel_ba})

    type_plural = {
        "board": "boards",
        "driver": "drivers",
        "motor": "motors",
        "host": "hosts",
        "catalog": "catalog",
    }

    # entity ↔ manufacturer
    for key, mfr in entity_keys.items():
        etype = key.split(":", 1)[0]
        link_mid = resolved_for.get(key) or derived_id.get(mfr)
        if not link_mid or link_mid not in g.manufacturer_by_id:
            continue
        g.entity_manufacturer_id[key] = link_mid
        member_counts[link_mid] += 1
        link(key, f"manufacturer:{link_mid}", "manufacturer", type_plural[etype])
    for mid, ent in g.manufacturer_by_id.items():
        ent["memberCount"] = member_counts.get(mid, 0)

    # board ↔ mcu
    for board in boards:
        bid = str(board.get("board_id", ""))
        if not bid:
            continue
        bkey = f"board:{bid}"
        for mcu_id, _disp, _fam in board_mcu_ids(board):
            g.mcu_by_id[mcu_id]["boardCount"] += 1
            link(bkey, f"mcu:{mcu_id}", "mcus", "boards")

    # board ↔ driver (onboard / supported), matched by driver chip & aliases
    driver_lookup: list[tuple[str, list[str]]] = []
    for drv in drivers:
        did = str(drv.get("driver_id", ""))
        if not did:
            continue
        raw_terms = {str(drv.get("chip") or ""), str(drv.get("name") or "")}
        raw_terms |= {str(a) for a in (drv.get("aliases") or [])}
        norm_terms = sorted(
            {re.sub(r"[^a-z0-9]", "", t.lower()) for t in raw_terms if t and len(t) >= 5},
            key=len,
            reverse=True,
        )
        if norm_terms:
            driver_lookup.append((did, norm_terms))

    for board in boards:
        bid = str(board.get("board_id", ""))
        spec = board.get("specs", {})
        if not bid or not isinstance(spec, dict):
            continue
        bkey = f"board:{bid}"
        # tokenise the spec into DISCRETE driver entries — matching a term against a
        # punctuation-stripped concatenation bled across boundaries (driver "TMC5160T" falsely
        # matched "TMC5160/TMC5161" because the joined "...tmc5160tmc5161..." contains "tmc5160t").
        onboard = set(re.findall(r"[a-z0-9]+", str(spec.get("Onboard drivers", "")).lower()))
        supported = set(re.findall(r"[a-z0-9]+", str(spec.get("Supported drivers", "")).lower()))
        for did, terms in driver_lookup:
            dkey = f"driver:{did}"
            if any(t in onboard for t in terms):
                link(bkey, dkey, "onboardDrivers", "boards")
            elif any(t in supported for t in terms):
                link(bkey, dkey, "supportedDrivers", "boards")

    # stable, deduped manufacturer list (most-connected first)
    g.manufacturers = sorted(
        g.manufacturer_by_id.values(),
        key=lambda m: (-int(m["memberCount"]), str(m["name"]).lower()),
    )
    g.mcus = sorted(g.mcu_by_id.values(), key=lambda m: (-int(m["boardCount"]), str(m["name"])))
    return g


_MAX_RELATED = 200


def related(graph: LinkGraph, plural_type: str, entity_id: str) -> dict[str, Any] | None:
    """Grouped related entities for one node, keyed by relation (O(1) adjacency walk).

    ``plural_type`` is the route path segment (``boards`` / ``mcus`` / …). Returns ``None`` if
    the node is unknown so the route can 404; otherwise ``{"id", "type", "groups", "counts"}``.
    """
    etype = PLURAL_TO_TYPE.get(plural_type)
    if etype is None:
        return None
    key = f"{etype}:{entity_id}"
    if key not in graph.summaries:
        return None
    groups: dict[str, list[dict[str, Any]]] = {}
    counts: dict[str, int] = {}
    seen: set[tuple[str, str]] = set()
    for edge in graph.adjacency.get(key, []):
        rel = edge["rel"]
        nbr = edge["key"]
        dedup = (rel, nbr)
        if dedup in seen:
            continue
        seen.add(dedup)
        summary = graph.summaries.get(nbr)
        if summary is None:
            continue
        counts[rel] = counts.get(rel, 0) + 1
        bucket = groups.setdefault(rel, [])
        if len(bucket) < _MAX_RELATED:
            bucket.append(summary)
    for bucket in groups.values():
        bucket.sort(key=lambda s: str(s.get("name") or s.get("id")).lower())
    return {"type": etype, "id": entity_id, "groups": groups, "counts": counts}
