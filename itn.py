"""Inverse text normalization: say it the spoken way, get it the written way.

"twenty five percent" -> "25%", "three thirty p.m." -> "3:30 PM",
"john dot smith at gmail dot com" -> "john.smith@gmail.com".

whisper already writes many of these itself, inconsistently: "5 dollars" one
day and "$5" the next, "3.30 p.m.", "twenty twenty six". This pass makes the
output consistent and fills in what whisper leaves as words.

English only -- the caller skips it for every other language, because number
words, date order and phone formats are exactly what varies by locale.

Each rule has a twin that must NOT fire, and the tests hold both:

  - Numbers one to nine stay words in prose ("one of them", "two options"),
    the AP convention, unless a unit, a currency, a clock or a month makes
    them a quantity. Ten and up become digits.
  - An email needs a reason to be one: "look at google dot com" is a URL,
    not look@google.com. See _email().
  - Commas group digits only from 10,000 up, so a year never gets one and
    "5000 people" reads the way most people type it.
"""
import re

from backtrack import is_common

_UNITS = {"zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4,
          "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
          "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
          "eighteen": 18, "nineteen": 19}
_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
         "seventy": 70, "eighty": 80, "ninety": 90}
_SCALES = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}

_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
             "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
             "eleventh": 11, "twelfth": 12, "thirteenth": 13,
             "fourteenth": 14, "fifteenth": 15, "sixteenth": 16,
             "seventeenth": 17, "eighteenth": 18, "nineteenth": 19,
             "twentieth": 20, "thirtieth": 30, "fortieth": 40,
             "fiftieth": 50, "sixtieth": 60, "seventieth": 70,
             "eightieth": 80, "ninetieth": 90}

MONTHS = ("January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December")

# Top-level domains Halo will build an address around. A closed list on
# purpose: "dot" followed by an arbitrary word is too often just speech.
_TLDS = ("com", "org", "net", "edu", "gov", "io", "co", "ai", "dev", "app",
         "me", "us", "uk", "ca", "de", "fr", "in", "info", "biz", "xyz",
         "tech", "sh", "gg", "tv", "fm", "ly", "so", "to", "cc", "eu", "au",
         "nz", "jp", "es", "it", "nl", "se", "ch", "be", "ie", "at", "br")

_NUM_WORD = "|".join(sorted(
    list(_UNITS) + list(_TEENS) + list(_TENS) + list(_SCALES) + ["hundred"],
    key=len, reverse=True))
# A maximal run of number words. "and" is allowed only inside a run
# ("one hundred and five"), never at either end.
_RUN = re.compile(
    r"(?<![\w'’.-])(?:" + _NUM_WORD + r")(?:(?:\s+|-)(?:and\s+)?(?:"
    + _NUM_WORD + r"))*(?![\w'’])",
    re.IGNORECASE)
_DECIMAL = re.compile(
    r"(?<![\w'’.])(\d+|(?:" + _NUM_WORD + r")(?:(?:\s+|-)(?:" + _NUM_WORD
    + r"))*)\s+point\s+((?:" + "|".join(_UNITS) + r")(?:\s+(?:"
    + "|".join(_UNITS) + r"))*|\d+)\b",
    re.IGNORECASE)


def parse_words(words: list[str]) -> tuple[int | None, int]:
    """Parse a cardinal from the front of `words`.

    Returns (value, words consumed). Stops at the first word that would make
    the grammar invalid, so "one two three" parses as 1 and leaves "two
    three" for the next call -- that is how digit sequences stay separate.
    """
    total, current, last, used = 0, 0, None, 0
    for i, raw in enumerate(words):
        w = raw.lower()
        if w == "and":
            if last in ("hundred", "scale") and i + 1 < len(words) and \
                    words[i + 1].lower() in {**_UNITS, **_TEENS, **_TENS}:
                continue
            break
        if w in _UNITS and w != "oh":
            if last in (None, "hundred", "scale") or (
                    last == "tens" and current % 10 == 0):
                if w == "zero" and last is not None:
                    break
                current += _UNITS[w]
                last = "unit"
            else:
                break
        elif w in _TEENS:
            if last in (None, "hundred", "scale"):
                current += _TEENS[w]
                last = "teen"
            else:
                break
        elif w in _TENS:
            if last in (None, "hundred", "scale"):
                current += _TENS[w]
                last = "tens"
            else:
                break
        elif w == "hundred":
            if last in ("unit", "teen", "tens") and 0 < current < 100:
                current *= 100
                last = "hundred"
            else:
                break
        elif w in _SCALES:
            if current > 0 and last != "scale" and (
                    total == 0 or total > _SCALES[w] * 999):
                total += current * _SCALES[w]
                current = 0
                last = "scale"
            else:
                break
        else:
            break
        used = i + 1
    if used == 0:
        return None, 0
    return total + current, used


def _fmt(n: int) -> str:
    return f"{n:,}" if n >= 10_000 else str(n)


def _ordinal_suffix(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return "th"
    return {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def _ordinal_value(text: str) -> int | None:
    """"twenty first" / "twenty-first" / "21st" / "fifth" -> int."""
    t = text.lower().strip()
    m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?", t)
    if m:
        return int(m.group(1))
    parts = re.split(r"[\s-]+", t)
    if len(parts) == 1:
        return _ORDINALS.get(parts[0])
    if len(parts) == 2 and parts[0] in _TENS and parts[1] in _ORDINALS \
            and _ORDINALS[parts[1]] < 10:
        return _TENS[parts[0]] + _ORDINALS[parts[1]]
    return None


_ORD_WORD = (r"(?:(?:" + "|".join(_TENS) + r")[\s-])?(?:"
             + "|".join(sorted(_ORDINALS, key=len, reverse=True)) + r")")


# --- emails and URLs ------------------------------------------------------

_TLD = "|".join(_TLDS)
_LABEL = r"[a-z0-9][a-z0-9-]*"
# "gmail dot com", "mail dot example dot co dot uk"
_SPOKEN_DOMAIN = (r"(?:" + _LABEL + r"\s+dot\s+)+(?:" + _TLD + r")(?![\w'])")
_EMAIL = re.compile(
    r"(?<![\w@.])(?P<local>" + _LABEL
    + r"(?:\s+(?:dot|underscore|dash|hyphen)\s+" + _LABEL + r")*)"
    r"\s+at\s+(?P<domain>" + _SPOKEN_DOMAIN + r"|"
    + _LABEL + r"(?:\." + _LABEL + r")*\.(?:" + _TLD + r")(?![\w']))",
    re.IGNORECASE)
_EMAIL_CUE = re.compile(
    r"\b(?:e-?mail|mail|address|contact|reach|write|cc|bcc|send)\b",
    re.IGNORECASE)

_URL = re.compile(
    r"(?<![\w@.])(?:(?P<scheme>https?)\s*(?:colon\s*)?(?:slash\s*slash|//)\s*)?"
    r"(?P<host>(?:www\s+dot\s+)?" + _SPOKEN_DOMAIN + r")"
    r"(?P<path>(?:\s+slash\s+[a-z0-9-]+)*)",
    re.IGNORECASE)


def _email(m: re.Match, text: str) -> str:
    local = m.group("local")
    words = local.split()
    # The local part is only as far back as the dotted chain goes, but the
    # regex can reach one plain word further ("email me at ..." would bind
    # "me"). Needs a reason to be an address:
    #   a cue word earlier in the sentence ("email", "address", "reach")
    #   a structured local part ("john dot smith", "j underscore doe", "jsmith2")
    #   a local part that is not an ordinary English word (a name, a handle)
    structured = len(words) > 1 or any(ch.isdigit() for ch in local)
    head = text[:m.start()]
    sentence = re.split(r"[.!?\n]", head)[-1]
    cue = bool(_EMAIL_CUE.search(sentence))
    ordinary = is_common(local)
    if not (structured or cue or not ordinary):
        return m.group(0)
    for spoken, mark in (("dot", "."), ("underscore", "_"), ("dash", "-"),
                         ("hyphen", "-")):
        local = re.sub(r"\s+" + spoken + r"\s+", mark, local, flags=re.IGNORECASE)
    domain = re.sub(r"\s+dot\s+", ".", m.group("domain"), flags=re.IGNORECASE)
    return f"{local}@{domain}".lower()


def _url(m: re.Match) -> str:
    host = re.sub(r"\s+dot\s+", ".", m.group("host"), flags=re.IGNORECASE).lower()
    path = re.sub(r"\s+slash\s+", "/", m.group("path") or "", flags=re.IGNORECASE)
    scheme = m.group("scheme")
    return (f"{scheme.lower()}://" if scheme else "") + host + path


# --- phone numbers --------------------------------------------------------

_DIGIT_WORD = r"(?:zero|oh|one|two|three|four|five|six|seven|eight|nine|\d)"
_PHONE = re.compile(
    r"(?<![\w'])(?P<plus>plus\s+)?(?P<digits>" + _DIGIT_WORD
    + r"(?:[\s,-]+" + _DIGIT_WORD + r"){6,11})(?![\w'])",
    re.IGNORECASE)
# whisper's own "555 123 4567" (space-separated groups).
_PHONE_GROUPS = re.compile(r"(?<![\w$.,-])(\d{3})\s(\d{3})\s(\d{4})(?![\w.,-]\d)")


def _phone(m: re.Match) -> str:
    tokens = re.split(r"[\s,-]+", m.group("digits").strip())
    # Every token must be ONE digit, spoken or written: "555 1234" is two
    # numbers whisper already grouped, handled by _PHONE_GROUPS instead.
    if not all(t.lower() in _UNITS or (t.isdigit() and len(t) == 1) for t in tokens):
        return m.group(0)
    digits = "".join(
        str(_UNITS[t.lower()]) if t.lower() in _UNITS else t for t in tokens)
    plus = bool(m.group("plus"))
    if len(digits) == 7:
        return f"{digits[:3]}-{digits[3:]}"
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    if plus and 8 <= len(digits) <= 12:
        return "+" + digits
    return m.group(0)


# --- times ----------------------------------------------------------------

_HOUR = r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|1[0-2]|0?[1-9])"
_MIN_WORDS = (r"(?:oh\s+(?:one|two|three|four|five|six|seven|eight|nine)"
              r"|(?:twenty|thirty|forty|fifty)(?:[\s-](?:one|two|three|four|five|six|seven|eight|nine))?"
              r"|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen)")
_MERIDIEM = r"(?P<ampm>[ap])\.?\s?m\b\.?"
_TIME = re.compile(
    r"(?<![\w'’:.])(?P<hour>" + _HOUR + r")(?:(?:\s+|[:.])(?P<min>"
    + _MIN_WORDS + r"|[0-5]\d))?\s*" + _MERIDIEM,
    re.IGNORECASE)
_OCLOCK = re.compile(r"(?<![\w'’])(?P<hour>" + _HOUR + r")\s+o'?clock\b",
                     re.IGNORECASE)


def _hour_value(word: str) -> int:
    return int(word) if word.isdigit() else parse_words([word])[0]


def _minute_value(text: str) -> int:
    if text.isdigit():
        return int(text)
    words = re.split(r"[\s-]+", text.lower())
    if words[0] == "oh":
        return _UNITS[words[1]]
    return parse_words(words)[0]


def _keep_stop(m: re.Match, rendered: str) -> str:
    """"p.m." at the end of a sentence carries the sentence's full stop too.
    Rewriting it as "PM" must not take the full stop with it."""
    if not m.group(0).endswith("."):
        return rendered
    rest = m.string[m.end():]
    if not rest.strip() or re.match(r"\s+[A-Z\n]", rest):
        return rendered + "."
    return rendered


def _time(m: re.Match) -> str:
    hour = _hour_value(m.group("hour").lower())
    minutes = m.group("min")
    ampm = "AM" if m.group("ampm").lower() == "a" else "PM"
    if minutes:
        return _keep_stop(m, f"{hour}:{_minute_value(minutes):02d} {ampm}")
    return _keep_stop(m, f"{hour} {ampm}")


# --- dates ----------------------------------------------------------------

_MONTH_RE = r"(?P<month>" + "|".join(MONTHS) + r")"
# Spoken years: "twenty twenty six", "nineteen ninety nine", "two thousand
# twenty". The two-group form is never a cardinal ("20 26" means nothing), so
# it is safe to read as a year anywhere.
_YEAR_SPOKEN = re.compile(
    r"(?<![\w'’])(?P<century>nineteen|twenty)\s+(?P<rest>"
    r"(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[\s-](?:one|two|three|four|five|six|seven|eight|nine))?"
    r"|oh\s+(?:one|two|three|four|five|six|seven|eight|nine)"
    r"|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
    r"|hundred)(?![\w'’])",
    re.IGNORECASE)
_DATE = re.compile(
    r"(?<![\w'’])" + _MONTH_RE + r"\s+(?:the\s+)?(?P<day>" + _ORD_WORD
    + r"|\d{1,2}(?:st|nd|rd|th)?)(?![\w'’])(?:,?\s+(?P<year>\d{4}))?")
_DATE_OF = re.compile(
    r"(?<![\w'’])the\s+(?P<day>" + _ORD_WORD + r"|\d{1,2}(?:st|nd|rd|th)?)\s+of\s+"
    + _MONTH_RE + r"(?![\w'’])(?:,?\s+(?P<year>\d{4}))?",
    re.IGNORECASE)


def _year(m: re.Match) -> str:
    century = 1900 if m.group("century").lower() == "nineteen" else 2000
    rest = m.group("rest").lower()
    if rest == "hundred":
        return str(century)
    return str(century + _minute_value(rest))


_day_first = False


def _date(m: re.Match) -> str:
    day = _ordinal_value(m.group("day"))
    if day is None or not 1 <= day <= 31:
        return m.group(0)
    month = m.group("month")
    month = month[0].upper() + month[1:].lower()
    year = m.group("year")
    if _day_first:
        # en-GB and friends: "5 January 2027", no comma.
        return f"{day} {month}" + (f" {year}" if year else "")
    return f"{month} {day}" + (f", {year}" if year else "")


# --- numbers --------------------------------------------------------------

# A number word under ten becomes a digit only next to one of these.
_UNIT_AFTER = re.compile(
    r"\s*(?:%|percent\b|per\s+cent\b|dollars?\b|euros?\b|cents?\b|"
    r"[ap]\.?\s?m\b|o'?clock\b|x\b|times\s+(?:faster|slower|more|less)\b|"
    r"(?:k|m|g|t)b\b|(?:kilo|mega|giga|tera)bytes?\b|ms\b|milliseconds?\b|"
    r"seconds?\b|minutes?\b|hours?\b|percentage\s+points?\b)",
    re.IGNORECASE)
_NUMBER_BEFORE = re.compile(
    r"(?:\$|€|£|#|\b(?:version|v|page|pages|chapter|line|room|gate|platform|"
    r"level|section|figure|table|step|number|no\.|item|floor|apartment|suite|"
    + "|".join(MONTHS) + r"))\s*$",
    re.IGNORECASE)


def _numbers(text: str) -> str:
    def decimal(m: re.Match) -> str:
        whole = m.group(1)
        value = int(whole) if whole.isdigit() else parse_words(
            re.split(r"[\s-]+", whole))[0]
        frac = m.group(2).strip()
        if not frac.isdigit():
            frac = "".join(str(_UNITS[w.lower()]) for w in frac.split())
        if value is None:
            return m.group(0)
        return f"{_fmt(value)}.{frac}"

    text = _DECIMAL.sub(decimal, text)

    out, pos = [], 0
    for m in _RUN.finditer(text):
        words = re.split(r"[\s-]+", m.group(0))
        start = m.start()
        # A run can hold several numbers ("one two three"); parse greedily.
        pieces, i = [], 0
        while i < len(words):
            value, used = parse_words(words[i:])
            if not used:
                pieces.append(words[i])
                i += 1
                continue
            pieces.append(value)
            i += used
        if len(pieces) != 1 or not isinstance(pieces[0], int):
            continue
        value = pieces[0]
        after = text[m.end():]
        before = text[:start]
        quantity = bool(_UNIT_AFTER.match(after)) or bool(_NUMBER_BEFORE.search(before))
        # "a million" / "one in a million" stay words; so does a bare scale.
        if value < 10 and not quantity:
            continue
        if re.fullmatch(r"(?:hundred|thousand|million|billion)", m.group(0), re.I):
            continue
        # "five million" reads better than 5000000.
        scale = re.search(r"\b(million|billion)$", m.group(0), re.IGNORECASE)
        if scale and value % _SCALES[scale.group(1).lower()] == 0:
            rendered = f"{_fmt(value // _SCALES[scale.group(1).lower()])} {scale.group(1).lower()}"
        else:
            rendered = _fmt(value)
        out.append(text[pos:start])
        out.append(rendered)
        pos = m.end()
    out.append(text[pos:])
    return "".join(out)


_ORDINAL_STANDALONE = re.compile(r"(?<![\w'’-])(" + _ORD_WORD + r")(?![\w'’-])",
                                 re.IGNORECASE)


def _ordinals(text: str) -> str:
    """Ordinals from eleventh up become 21st, 11th; first..tenth stay words."""
    def sub(m: re.Match) -> str:
        n = _ordinal_value(m.group(1))
        if n is None or n <= 10:
            return m.group(0)
        return f"{n}{_ordinal_suffix(n)}"
    return _ORDINAL_STANDALONE.sub(sub, text)


# --- money and percentages (on digits, after _numbers) --------------------

_NUM = r"\d[\d,]*(?:\.\d+)?"
_PERCENT = re.compile(r"(?<![\w.])(" + _NUM + r")\s*(?:percent|per\s+cent)\b", re.I)
_DOLLARS = re.compile(
    r"(?<![\w.$])(" + _NUM + r")(\s+(?:million|billion|thousand))?\s+(?:us\s+)?"
    r"dollars?(?:\s+and\s+(\d{1,2})\s+cents?)?\b", re.I)
_EUROS = re.compile(
    r"(?<![\w.€])(" + _NUM + r")(\s+(?:million|billion|thousand))?\s+euros?\b", re.I)
_CENTS_ONLY = re.compile(r"(?<![\w.$])\$(" + _NUM + r")\s+and\s+(\d{1,2})\s+cents?\b", re.I)


def _money(text: str) -> str:
    def dollars(m: re.Match) -> str:
        amount, scale, cents = m.group(1), (m.group(2) or ""), m.group(3)
        if cents:
            return f"${amount}.{int(cents):02d}{scale}"
        return f"${amount}{scale}"

    text = _DOLLARS.sub(dollars, text)
    text = _CENTS_ONLY.sub(lambda m: f"${m.group(1)}.{int(m.group(2)):02d}", text)
    text = _EUROS.sub(lambda m: f"€{m.group(1)}{m.group(2) or ''}", text)
    text = _PERCENT.sub(lambda m: f"{m.group(1)}%", text)
    return text


def _normalize_meridiem(text: str) -> str:
    """whisper's own "3:30 p.m." / "3.30pm" -> "3:30 PM"."""
    def sub(m: re.Match) -> str:
        minutes = m.group(2)
        ampm = "AM" if m.group(3).lower() == "a" else "PM"
        return _keep_stop(m, f"{int(m.group(1))}:{minutes} {ampm}" if minutes
                          else f"{int(m.group(1))} {ampm}")
    return re.sub(r"(?<![\w:.])(1[0-2]|0?[1-9])(?:[:.]([0-5]\d))?\s*([ap])\.?\s?m\b\.?(?=\s|$|[,;!?])",
                  sub, text, flags=re.IGNORECASE)


def normalize(text: str, day_first: bool = False) -> str:
    """The whole pass, in the order the rules depend on each other.

    Addresses first, so nothing below mistakes "one" in "one dot com" for a
    number. Phones before numbers, so seven single digits are not read as a
    list of words. Years and times before generic numbers, because "twenty
    twenty six" and "three thirty" are not cardinals.
    """
    if not text or not text.strip():
        return text
    global _day_first
    _day_first = day_first
    text = _EMAIL.sub(lambda m: _email(m, m.string), text)
    text = _URL.sub(_url, text)
    text = _PHONE.sub(_phone, text)
    text = _PHONE_GROUPS.sub(lambda m: f"({m.group(1)}) {m.group(2)}-{m.group(3)}", text)
    text = _YEAR_SPOKEN.sub(_year, text)
    text = _TIME.sub(_time, text)
    text = _normalize_meridiem(text)
    text = _OCLOCK.sub(lambda m: f"{_hour_value(m.group('hour').lower())} o'clock", text)
    # Dates and ordinals before cardinals: "twenty first" is one ordinal, but
    # the cardinal pass would read "twenty" and strand "first". Dates run
    # again afterwards for "January twenty five" once it is "January 25".
    text = _DATE_OF.sub(_date, text)
    text = _DATE.sub(_date, text)
    text = _ordinals(text)
    text = _numbers(text)
    text = _DATE.sub(_date, text)
    text = _money(text)
    return text

