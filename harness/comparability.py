"""What a pair of implementations may be compared FOR, and the flag their numbers earn.

Spec §5.5 and §7. Red is only ever assignable inside `same-estimator`: a difference in the
model equation cannot be fixed with a statistic, it can only be declared. So the class and
its human-readable cause live in comparability.yml, and no number is turned into a colour
without being read through one. The declared cause is rendered as visible text on the site
(spec §7.3), following the precedent of the "What did not run" list rather than a tooltip
— which is why a class meaning "expected to differ" cannot be declared without one.
"""
from __future__ import annotations

import dataclasses
import pathlib

import yaml

# Reused rather than subclassed: a malformed comparability.yml is the same failure as a
# malformed models/*.yml -- a declared configuration file the run cannot trust -- and it
# has to abort the run the same way instead of arriving as a second exception type that
# callers have to learn about (spec §10 allows exactly two run-aborting failures).
from harness.config import ConfigError

SAME_ESTIMATOR = "same-estimator"
RELATED_ESTIMATOR = "related-estimator"
INCOMPARABLE = "incomparable"
KNOWN_CLASSES = (SAME_ESTIMATOR, RELATED_ESTIMATOR, INCOMPARABLE)

# A class that means "expected to differ" or "do not run this" is a claim about the
# science, and the site prints the claim. Without the text it degrades to a bare colour a
# reader cannot check or argue with, which is the failure this requirement prevents.
CLASSES_REQUIRING_REASON = (RELATED_ESTIMATOR, INCOMPARABLE)

# Orthogonal to the estimator class, and deliberately not a fourth class (spec §7.3):
# `related-estimator` paints amber and means "expected to differ", which would UNDERSTATE
# a tool being fed data its documented model does not support.
SATISFIED = "satisfied"
VIOLATED = "violated"
KNOWN_INPUT_DOMAINS = (SATISFIED, VIOLATED)

GREEN, AMBER, RED = "green", "amber", "red"


@dataclasses.dataclass(frozen=True)
class Thresholds:
    """Where amber and red begin, inside `same-estimator` only.

    Spec §7 declares these per model in `models/*.yml` rather than in Python. They are a
    parameter here, defaulted to the spec's numbers, so that wiring the per-model
    declaration in later changes where the numbers come from and not what the rule is.
    """

    amber_rel_median_diff: float = 0.05
    red_rel_median_diff: float = 0.10
    amber_ccc: float = 0.95
    red_ccc: float = 0.90


DEFAULT_THRESHOLDS = Thresholds()


@dataclasses.dataclass(frozen=True)
class Comparability:
    """One declared (model, map, pair) verdict, or the undeclared default for one."""

    model: str
    map_name: str
    # Each member names either a software ('quit') or one specific target ('qmrlab@V1').
    # Sorted, because the class is a property of the two implementations and not of which
    # one analyze happened to pick as the reference -- spec §5.6 fixes the reference
    # orientation separately, and a declaration that had to be written in the right order
    # would be missed by a lookup that asked in the other one.
    members: tuple[str, str]
    estimator_class: str
    reason: str | None
    input_domain: str
    input_domain_reason: str | None

    @property
    def comparable(self) -> bool:
        """False means analyze must not build the pair at all (spec §5.5)."""
        return self.estimator_class != INCOMPARABLE


@dataclasses.dataclass(frozen=True)
class Flag:
    colour: str
    reason: str


def _require(doc: dict, key: str, where: str):
    """A local twin of config.py's, deliberately not imported from it.

    Three lines of duplication against coupling this module to another one's private
    helper. What must NOT diverge is the message shape -- both name the file and the
    field, because a schema violation aborts the run and has to say where.
    """
    if key not in doc:
        raise ConfigError(f"{where}: missing required field {key!r}")
    return doc[key]


def _reason(doc: dict, key: str, where: str) -> str | None:
    """A reason that is present but blank is worse than absent: it renders as nothing."""
    value = doc.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{where}: {key} must be non-empty text, got {value!r}")
    # Collapsed to one line because the site renders this inline beside a colour, and YAML
    # block scalars keep the newlines the file wrapped them at.
    return " ".join(value.split())


def _members(pair, where: str) -> tuple[str, str]:
    if not isinstance(pair, (list, tuple)) or len(pair) != 2:
        raise ConfigError(f"{where}: each pair must name exactly two sides, got {pair!r}")
    for side in pair:
        if not isinstance(side, str) or not side.strip():
            raise ConfigError(f"{where}: pair member must be a name, got {side!r}")
    if pair[0] == pair[1]:
        raise ConfigError(f"{where}: pair names {pair[0]!r} on both sides")
    return tuple(sorted(pair))  # type: ignore[return-value]


def load_comparability(root: pathlib.Path) -> tuple[Comparability, ...]:
    """Read comparability.yml into one entry per (model, map, pair) it declares.

    Absent file is an empty declaration, not an error: every pair then falls back to the
    undeclared default in `comparability_for`, which is what the fourteen qMRLab-versus-
    qMRLab pairs have always run as.
    """
    path = pathlib.Path(root) / "comparability.yml"
    where = str(path)
    if not path.exists():
        return ()
    doc = yaml.safe_load(path.read_text()) or {}

    entries: list[Comparability] = []
    seen: dict[tuple[str, str, tuple[str, str]], int] = {}
    for i, raw in enumerate(_require(doc, "entries", where)):
        at = f"{where}: entries[{i}]"
        model = _require(raw, "model", at)
        estimator_class = _require(raw, "class", at)
        if estimator_class not in KNOWN_CLASSES:
            raise ConfigError(
                f"{at}: class must be one of {KNOWN_CLASSES}, got {estimator_class!r}"
            )

        reason = _reason(raw, "reason", at)
        if estimator_class in CLASSES_REQUIRING_REASON and reason is None:
            raise ConfigError(
                f"{at}: class {estimator_class!r} requires a reason; it is rendered as "
                "visible text on the site, and without it the entry is a bare colour"
            )

        input_domain = raw.get("input_domain", SATISFIED)
        if input_domain not in KNOWN_INPUT_DOMAINS:
            raise ConfigError(
                f"{at}: input_domain must be one of {KNOWN_INPUT_DOMAINS}, "
                f"got {input_domain!r}"
            )
        input_domain_reason = _reason(raw, "input_domain_reason", at)
        if input_domain == VIOLATED:
            if input_domain_reason is None:
                raise ConfigError(
                    f"{at}: input_domain 'violated' requires an input_domain_reason "
                    "naming whose requirement is broken and how (spec §7.3)"
                )
            if estimator_class == INCOMPARABLE:
                # A contradiction, not a redundancy: 'incomparable' means the pair is
                # never built, so the red flag this field asks for could never be
                # rendered. One of the two lines is a mistake and the file must say which.
                raise ConfigError(
                    f"{at}: input_domain 'violated' cannot be declared on an "
                    "'incomparable' entry -- that pair never runs, so its red flag "
                    "would never be shown"
                )

        maps = _require(raw, "maps", at)
        if not maps:
            raise ConfigError(f"{at}: maps must name at least one map")
        pairs = _require(raw, "pairs", at)
        if not pairs:
            raise ConfigError(f"{at}: pairs must name at least one pair")

        # Expanded here rather than matched with a wildcard at lookup time: a map added to
        # a model later must not inherit an old entry's class silently. Naming the maps
        # means the declaration ages loudly.
        for map_name in maps:
            for pair in pairs:
                members = _members(pair, at)
                key = (model, map_name, members)
                if key in seen:
                    raise ConfigError(
                        f"{at}: duplicate declaration for {model}/{map_name} "
                        f"{members[0]} vs {members[1]}, already declared at "
                        f"{where}: entries[{seen[key]}]"
                    )
                seen[key] = i
                entries.append(
                    Comparability(
                        model=model,
                        map_name=map_name,
                        members=members,
                        estimator_class=estimator_class,
                        reason=reason,
                        input_domain=input_domain,
                        input_domain_reason=input_domain_reason,
                    )
                )
    return tuple(entries)


def _specificity(member: str, target: str, software: str) -> int | None:
    """How specifically one declared member names one target, or None if it does not.

    A member is a software name or a target id, because both are real declarations: the
    QUIT lineshape difference belongs to QUIT, while V1 ignoring the B1 map for Ramani
    belongs to `qmrlab@V1` alone and must not paint the other thirteen qMRLab targets
    (spec §2.2). The target id is checked against the target's DECLARED software rather
    than the text before its '@': target.yml owns that fact, and inferring it from an id
    would be a second source of truth for it.
    """
    if member == target:
        return 1
    if member == software:
        return 0
    return None


def comparability_for(
    entries: tuple[Comparability, ...],
    model: str,
    map_name: str,
    *,
    a_target: str,
    a_software: str,
    b_target: str,
    b_software: str,
) -> Comparability:
    """The declaration governing one pair, or the undeclared default.

    Undeclared is `same-estimator`: it is what every qMRLab-versus-qMRLab pair on the site
    already is, and making the safe-looking choice the default would silence red
    everywhere by saying nothing.
    """
    best: list[Comparability] = []
    best_specificity = -1
    for entry in entries:
        if entry.model != model or entry.map_name != map_name:
            continue
        m0, m1 = entry.members
        # Both assignments, because `members` is sorted and carries no orientation.
        scores = []
        for x, y in ((m0, m1), (m1, m0)):
            sa = _specificity(x, a_target, a_software)
            sb = _specificity(y, b_target, b_software)
            if sa is not None and sb is not None:
                scores.append(sa + sb)
        if not scores:
            continue
        specificity = max(scores)
        if specificity > best_specificity:
            best_specificity, best = specificity, [entry]
        elif specificity == best_specificity:
            best.append(entry)

    if len(best) > 1:
        # Picking one would make the site's flag depend on file order. The file has to say
        # which declaration wins.
        raise ConfigError(
            f"comparability.yml: {model}/{map_name} {a_target} vs {b_target} is matched "
            f"equally by "
            + " and ".join(f"{e.members[0]} vs {e.members[1]}" for e in best)
        )
    if best:
        return best[0]
    return Comparability(
        model=model,
        map_name=map_name,
        members=tuple(sorted((a_software, b_software))),  # type: ignore[arg-type]
        estimator_class=SAME_ESTIMATOR,
        reason=None,
        input_domain=SATISFIED,
        input_domain_reason=None,
    )


def _declared_text(entry: Comparability, field: str) -> str:
    """The declared text for a colour that is decided by declaration, not by numbers.

    load_comparability already refuses to build such an entry without it. Checked again
    here because the flag is the only place the omission would be survivable: it would
    reach the site as the bare colour the whole reason requirement exists to prevent.
    """
    text = getattr(entry, field)
    if not text:
        raise ValueError(
            f"{entry.model}/{entry.map_name} {entry.members[0]} vs {entry.members[1]}: "
            f"{field} is required to render this flag"
        )
    return text


def _percent(value: float, *, signed: bool = False) -> str:
    """A measured difference keeps its sign; a threshold has no direction to keep.

    Spec §7 wants the headline readable as a sentence -- "QUIT reads 3% lower T1" -- and
    an unsigned 3% next to a 5% threshold reads as a magnitude with the direction lost.
    """
    text = f"{100.0 * value:.3g}%"
    return "+" + text if signed and value > 0 else text


def flag_for(
    entry: Comparability,
    *,
    rel_median_diff: float | None,
    ccc: float | None,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> Flag:
    """The colour and the visible text for one pair's numbers.

    The order of the rules is the design (spec §7): the estimator class decides whether
    the numbers are allowed to speak at all, and the input domain overrules the class.
    """
    if entry.estimator_class == INCOMPARABLE:
        # Not a colour. `comparable` is false and analyze must not have built the pair, so
        # arriving here means a pair exists that the file says should not -- a caller bug,
        # and one that would otherwise reach the site as a plausible-looking flag.
        raise ValueError(
            f"{entry.model}/{entry.map_name} {entry.members[0]} vs {entry.members[1]} is "
            "declared incomparable: the pair must not be built, so it has no flag"
        )

    if entry.input_domain == VIOLATED:
        # Red REGARDLESS of class, and before the class is consulted, because this is the
        # one failure amber would understate: the tool was fed data outside its documented
        # input domain, so its numbers are not a disagreement about the model at all.
        # `qi irtse` on magnitude data is the worked case (spec §7.3).
        return Flag(RED, _declared_text(entry, "input_domain_reason"))

    if entry.estimator_class == RELATED_ESTIMATOR:
        # Never red, whatever the numbers say. A different estimator is EXPECTED to differ
        # and by an amount nobody has any right to threshold: red here would report a
        # modelling difference as an implementation defect, which spec §1 calls worse than
        # no benchmark.
        return Flag(AMBER, _declared_text(entry, "reason"))

    red: list[str] = []
    amber: list[str] = []

    if rel_median_diff is None:
        # Not green. Green is a measured agreement; an absent measure has measured
        # nothing, and painting it green publishes an unmeasured cell as a passing one.
        amber.append("relative median difference could not be computed")
    elif abs(rel_median_diff) > thresholds.red_rel_median_diff:
        red.append(
            f"relative median difference {_percent(rel_median_diff, signed=True)} "
            f"exceeds {_percent(thresholds.red_rel_median_diff)}"
        )
    elif abs(rel_median_diff) > thresholds.amber_rel_median_diff:
        amber.append(
            f"relative median difference {_percent(rel_median_diff, signed=True)} "
            f"exceeds {_percent(thresholds.amber_rel_median_diff)}"
        )

    if ccc is None:
        amber.append("CCC could not be computed")
    elif ccc < thresholds.red_ccc:
        red.append(f"CCC {ccc:.3f} is below {thresholds.red_ccc:.3g}")
    elif ccc < thresholds.amber_ccc:
        amber.append(f"CCC {ccc:.3f} is below {thresholds.amber_ccc:.3g}")

    # A declared reason on a same-estimator entry is context for a cell that is allowed to
    # go red -- "settings aligned this way" -- so it travels with whichever colour the
    # numbers earn instead of being dropped for the numeric text.
    suffix = f" ({entry.reason})" if entry.reason else ""
    if red:
        return Flag(RED, "; ".join(red) + suffix)
    if amber:
        return Flag(AMBER, "; ".join(amber) + suffix)
    return Flag(
        GREEN,
        f"relative median difference {_percent(rel_median_diff, signed=True)}, "
        f"CCC {ccc:.3f}: within "
        f"the same-estimator thresholds" + suffix,
    )
