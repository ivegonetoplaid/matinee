"""The page's mechanical design rules (DESIGN_STANDARDS.md section 9), read from the stylesheet and the page scripts.

These tests read the source as text: there is no browser here. Each finds the things its rule is about and
fails when it finds too few of them, so a rule can never pass by matching nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "src" / "matinee" / "web" / "static"
CSS = (STATIC / "css" / "matinee.css").read_text(encoding="utf-8")
SCRIPTS = {p.name: p.read_text(encoding="utf-8") for p in sorted((STATIC / "js").glob("*.js"))}
PHONE = "@media (max-width: 600px)"
ACCENTS = {"gold", "rose", "petrol", "cream"}

# The artwork keeps its own colours (DESIGN_STANDARDS.md 3.1), named by the class its rule styles: the marquee
# (crown, sign, bulbs, letter board), the locked door's scene, the wall's tiles and the scorch.
ARTWORK = {
    "tile",
    "marquee",
    "marquee-glow",
    "crown",
    "step",
    "sunburst",
    "sun-core",
    "spire",
    "sign",
    "sign-frame",
    "sign-rule",
    "sign-name",
    "bulb",
    "letterboard",
    "subway",
    "door-frame",
    "doorway",
    "locked-door",
    "door-step",
    "slot-word",
    "slot-cover",
    "peek",
    "scorch",
}
ARTWORK_KEYFRAMES = {"burn", "chase"}  # the fuse's burn on Matinee's line, the bulbs' chase

# Text buttons and links that are not actions or letterboxes: the foot band's crumbs, About link and credits,
# About's own prose, the wordmark, and controls that are pictures or menu rows. Each names its element's tag,
# script, building function and classes, never a line.
PERMITTED = {
    ("a", "about.js", "link", frozenset()),
    ("a", "credits.js", "tmdbLogo", frozenset()),
    ("a", "credits.js", "dtddCredit", frozenset()),
    ("a", "main.js", "wordmark", frozenset({"wordmark"})),
    ("button", "main.js", "trail", frozenset({"crumb"})),
    ("button", "credits.js", "aboutLink", frozenset({"inline-link", "about-link"})),
    ("button", "door.js", "tile", frozenset({"seat"})),
    ("button", "door.js", "newTile", frozenset({"seat", "new"})),
    ("button", "main.js", "answerButton", frozenset({"pail"})),
    ("button", "mark.js", "avatarChoices", frozenset({"avatar-choice"})),
    ("button", "viewer.js", "viewerTag", frozenset({"viewer-button"})),
    ("button", "viewer.js", "item", frozenset({"viewer-item", "danger"})),
    ("button", "locked.js", "show", frozenset({"peek"})),
}

# Every CSS named colour.
NAMED = [
    "aliceblue",
    "antiquewhite",
    "aqua",
    "aquamarine",
    "azure",
    "beige",
    "bisque",
    "black",
    "blanchedalmond",
    "blue",
    "blueviolet",
    "brown",
    "burlywood",
    "cadetblue",
    "chartreuse",
    "chocolate",
    "coral",
    "cornflowerblue",
    "cornsilk",
    "crimson",
    "cyan",
    "darkblue",
    "darkcyan",
    "darkgoldenrod",
    "darkgray",
    "darkgreen",
    "darkgrey",
    "darkkhaki",
    "darkmagenta",
    "darkolivegreen",
    "darkorange",
    "darkorchid",
    "darkred",
    "darksalmon",
    "darkseagreen",
    "darkslateblue",
    "darkslategray",
    "darkslategrey",
    "darkturquoise",
    "darkviolet",
    "deeppink",
    "deepskyblue",
    "dimgray",
    "dimgrey",
    "dodgerblue",
    "firebrick",
    "floralwhite",
    "forestgreen",
    "fuchsia",
    "gainsboro",
    "ghostwhite",
    "gold",
    "goldenrod",
    "gray",
    "green",
    "greenyellow",
    "grey",
    "honeydew",
    "hotpink",
    "indianred",
    "indigo",
    "ivory",
    "khaki",
    "lavender",
    "lavenderblush",
    "lawngreen",
    "lemonchiffon",
    "lightblue",
    "lightcoral",
    "lightcyan",
    "lightgoldenrodyellow",
    "lightgray",
    "lightgreen",
    "lightgrey",
    "lightpink",
    "lightsalmon",
    "lightseagreen",
    "lightskyblue",
    "lightslategray",
    "lightslategrey",
    "lightsteelblue",
    "lightyellow",
    "lime",
    "limegreen",
    "linen",
    "magenta",
    "maroon",
    "mediumaquamarine",
    "mediumblue",
    "mediumorchid",
    "mediumpurple",
    "mediumseagreen",
    "mediumslateblue",
    "mediumspringgreen",
    "mediumturquoise",
    "mediumvioletred",
    "midnightblue",
    "mintcream",
    "mistyrose",
    "moccasin",
    "navajowhite",
    "navy",
    "oldlace",
    "olive",
    "olivedrab",
    "orange",
    "orangered",
    "orchid",
    "palegoldenrod",
    "palegreen",
    "paleturquoise",
    "palevioletred",
    "papayawhip",
    "peachpuff",
    "peru",
    "pink",
    "plum",
    "powderblue",
    "purple",
    "rebeccapurple",
    "red",
    "rosybrown",
    "royalblue",
    "saddlebrown",
    "salmon",
    "sandybrown",
    "seagreen",
    "seashell",
    "sienna",
    "silver",
    "skyblue",
    "slateblue",
    "slategray",
    "slategrey",
    "snow",
    "springgreen",
    "steelblue",
    "tan",
    "teal",
    "thistle",
    "tomato",
    "turquoise",
    "violet",
    "wheat",
    "white",
    "whitesmoke",
    "yellow",
    "yellowgreen",
]
COLOUR = re.compile(
    rf"#[0-9a-f]{{3,8}}\b|\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(|(?<![\w-])(?:{'|'.join(NAMED)})(?![\w-])",
    re.I,
)


@dataclass(frozen=True)
class Decl:
    context: tuple[str, ...]  # the enclosing at-rules, outermost first
    selectors: tuple[str, ...]
    prop: str
    value: str


def declarations(css: str) -> list[Decl]:
    """Every declaration with its selector list and enclosing at-rules. Comments are dropped first."""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    out: list[Decl] = []
    stack: list[str] = []
    pos = 0
    for m in re.finditer(r"[{};]", css):
        text = css[pos : m.start()].strip()
        pos = m.end()
        if m.group() == "{":
            stack.append(" ".join(text.split()))
        elif m.group() == "}":
            if stack:
                stack.pop()
        elif ":" in text and stack and not stack[-1].startswith("@"):
            prop, value = text.split(":", 1)
            ats = tuple(s for s in stack[:-1] if s.startswith("@"))
            out.append(Decl(ats, tuple(s.strip() for s in stack[-1].split(",")), prop.strip(), value.strip()))
    return out


DECLS = declarations(CSS)


def subject(selector: str) -> str:
    """The compound selector a rule styles: the last after any combinator, with pseudo-classes dropped."""
    last = re.split(r"\s*[ >+~]\s*", selector.strip())[-1]
    return re.sub(r"::?[\w-]+(\([^)]*\))?", "", last)


def classes(compound: str) -> set[str]:
    return set(re.findall(r"\.([\w-]+)", compound))


def is_artwork(d: Decl) -> bool:
    if any(re.fullmatch(rf"@keyframes ({'|'.join(ARTWORK_KEYFRAMES)})", a) for a in d.context):
        return True
    return all(classes(subject(s)) & ARTWORK for s in d.selectors)


@dataclass(frozen=True)
class Built:
    script: str
    function: str
    tag: str
    classes: frozenset[str]
    props: str
    first_child: str | None


def balanced(text: str, start: int) -> str:
    """The `{...}` starting at `start`, braces balanced."""
    depth = 0
    for i in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[start : i + 1]
    raise ValueError("unbalanced braces")


FUNCTION = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?"
    r"(?:function\s+(\w+)|(\w+)\([^)]*\)\s*\{\s*$|const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*\{)",
    re.M,
)


def enclosing(source: str, at: int) -> str:
    """The innermost function, method or arrow function whose body holds `at`; "" at the top level."""
    name = ""
    for m in FUNCTION.finditer(source, 0, at):
        body = source.find("{", m.end() - 1)
        if body != -1 and body < at < body + len(balanced(source, body)):
            name = m.group(1) or m.group(2) or m.group(3)
    return name


def built(tag: str) -> list[Built]:
    """Every element the page scripts build with `h(tag, {props}, ...)`."""
    found = []
    for script, source in SCRIPTS.items():
        for m in re.finditer(rf'\bh\(\s*"{tag}"\s*,\s*', source):
            props = balanced(source, m.end()) if source[m.end()] == "{" else ""
            after = source[m.end() + len(props) :]
            child = re.match(r'\s*,\s*"([^"]*)"', after)
            cls = re.search(r"class:\s*([^,\n]+)", props)
            names = frozenset(w for s in re.findall(r'"([^"]*)"', cls.group(1) if cls else "") for w in s.split())
            found.append(
                Built(script, enclosing(source, m.start()), tag, names, props, child.group(1) if child else None)
            )
    return found


ANCHORS = built("a")
BUTTONS = built("button")
ACTIONS = [b for b in ANCHORS + BUTTONS if "action" in b.classes]


def companions(family: str) -> set[str]:
    """Every class the page scripts apply together with `family` (`action` or `letterbox`), itself included."""
    return set().union(*(b.classes for b in ANCHORS + BUTTONS if family in b.classes))


def naming(family: str) -> list[Decl]:
    """The declarations whose selectors name a class the scripts apply together with `family`."""
    near = companions(family)
    return [d for d in DECLS if any(classes(s) & near for s in d.selectors)]


def test_the_readers_find_what_the_rules_are_about() -> None:
    assert len(DECLS) > 500 and len(ANCHORS) >= 6 and len(BUTTONS) >= 25 and len(ACTIONS) >= 15


def test_links_and_buttons_are_built_only_through_h_and_carry_no_inline_style() -> None:
    """The other rules read what `h()` builds and the stylesheet, so nothing else may build or style a control."""
    pattern = r"createElement\(\s*[\"'`](a|button)[\"'`]"
    assert [n for n, s in SCRIPTS.items() if n != "dom.js" and re.search(pattern, s)] == []
    assert [b for b in ANCHORS + BUTTONS if b.classes & {"action", "letterbox"} and "style:" in b.props] == []


def test_every_colour_on_a_control_text_band_or_scrim_reads_from_a_token() -> None:
    checked = [d for d in DECLS if ":root" not in d.selectors and not d.prop.endswith("mask-image")]
    assert len(checked) > 400
    stray = [
        f"{', '.join(d.selectors)} {{ {d.prop}: {d.value} }}"
        for d in checked
        if not is_artwork(d) and COLOUR.search(re.sub(r"var\(--[\w-]+\)", "", d.value))
    ]
    assert stray == []


def test_no_control_is_a_pill_or_wears_a_filled_accent() -> None:
    pills = [d for d in DECLS if d.prop == "border-radius" and "999" in d.value and not is_artwork(d)]
    assert pills == []
    for family, corner in (("action", "10px"), ("letterbox", "4px")):
        corners = [d.value for d in naming(family) if d.prop == "border-radius"]
        assert corners and set(corners) == {corner}, (family, corners)
    fills = {"background", "background-color", "background-image", "--action"}
    bodies = [d for d in naming("action") if d.prop in fills]
    assert bodies and all(d.value == "var(--action)" for d in bodies), [(d.selectors, d.prop, d.value) for d in bodies]


def test_every_action_wears_one_accent_and_a_petrol_one_ends_with_the_arrow() -> None:
    assert all(len(a.classes & ACCENTS) == 1 for a in ACTIONS), [sorted(a.classes) for a in ACTIONS]
    petrol = [a for a in ACTIONS if "petrol" in a.classes]
    assert len(petrol) == sum(s.count('"action petrol"') for s in SCRIPTS.values()) >= 3
    assert all(a.first_child and a.first_child.endswith("↗") for a in petrol), [a.first_child for a in petrol]


def test_bare_links_and_text_buttons_stand_only_where_the_standard_permits() -> None:
    loose = {
        (b.tag, b.script, b.function, b.classes) for b in ANCHORS + BUTTONS if not b.classes & {"action", "letterbox"}
    }
    assert not loose - PERMITTED, sorted(loose - PERMITTED, key=str)
    assert not PERMITTED - loose, f"permitted but not found: {sorted(PERMITTED - loose, key=str)}"


def test_every_link_but_the_wordmark_opens_a_new_tab_with_noopener() -> None:
    leaving = [a for a in ANCHORS if "wordmark" not in a.classes]
    assert len(leaving) >= 5
    for a in leaving:
        assert re.search(r'target:\s*"_blank"', a.props) and re.search(r'rel:\s*"noopener noreferrer"', a.props), a


def font_size(d: Decl) -> str | None:
    if d.prop == "font-size":
        return d.value
    if d.prop == "font":
        size = re.search(r"(?<![\w.-])(\d*\.?\d+(?:px|r?em|%|vw|vh|pt))", d.value)
        return size.group(1) if size else None
    return None


def test_letterboxes_and_actions_have_the_standards_sizes_and_no_override() -> None:
    sizes = {(d.selectors, d.context): font_size(d) for d in DECLS if font_size(d)}
    assert sizes[((".action",), ())] == "18px" and sizes[((".action",), (PHONE,))] == "16px"
    assert sizes[((".letterbox",), ())] == "24px" and sizes[((".letterbox",), (PHONE,))] == "19px"
    near = companions("action") | companions("letterbox")
    assert {"action", "letterbox", "just-pick", "topic", "danger"} <= near
    pinned = {((".action",), ()), ((".action",), (PHONE,)), ((".letterbox",), ()), ((".letterbox",), (PHONE,))}
    overrides = [
        (sel, ctx, size)
        for (sel, ctx), size in sizes.items()
        if (sel, ctx) not in pinned and any(classes(s) & near for s in sel)
    ]
    assert overrides == []
    # A bare button or link reached through an ancestor outranks the letterbox's own rule.
    bare = [
        (sel, size)
        for (sel, _), size in sizes.items()
        if size != "inherit" and any(re.fullmatch(r"a|button", subject(s)) and subject(s) != s.strip() for s in sel)
    ]
    assert bare == []
    assert all(is_artwork(d) for d in DECLS if d.prop == "zoom")  # zoom shrinks every control it holds
