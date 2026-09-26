"""Cleanup modes: how much of what you said gets tidied, and by what.

    off        exactly what whisper heard, after your vocabulary
    verbatim   spoken punctuation and spacing; nothing removed
    light      + fillers, stumbles ("the the"), obvious question marks,
               sentence case, a closing full stop
    normal     + self-corrections, lists, numbers/dates/money/phone/email/URL,
               typography, then a language model for grammar -- if one is
               ready in time
    polished   the same rules, then a model allowed to reword for readability

Three passes, every one of them optional except the first:

    rules   deterministic, ~1ms, always runs; the fallback for everything
    model   Normal/Polished only, only if local_llm.select() hands one back,
            only inside a hard deadline, and only if its answer passes the
            checks below. Anything else and the rules' text is what you get.
    finish  your vocabulary re-applied (a model must not undo it), the app's
            house style, and fitting the text to the cursor

What the model is told about context is deliberately thin: the names and
terms near the cursor, what kind of app it is, whether you are mid-sentence.
Never the surrounding text itself, and nothing at all goes to OpenRouter
beyond what it always received -- the transcript and your vocabulary.
"""
import re
import time
from dataclasses import dataclass, field

import backtrack
import cleanup
import config
import devmode
import formatting
import itn
import languages
import local_llm
import punctuate
import styles as styles_mod

MODEL_MODES = ("normal", "polished")


@dataclass
class Result:
    text: str
    source: str              # raw | rules | local | openrouter
    detail: str = ""
    stages: list[str] = field(default_factory=list)
    model_seconds: float = 0.0
    fell_back: bool = False  # a model was asked and its answer was not used
    style: str = ""          # the writing style applied, for the log and History


# --- the rules --------------------------------------------------------------

def rules(text: str, mode: str, profile: formatting.Profile, *,
          english: bool = True, dev: bool = False, ctx=None,
          day_first: bool = False) -> tuple[str, list[str], bool]:
    """The deterministic pass. Returns (text, stages that changed it,
    whether it produced a list -- lists get no closing full stop)."""
    stages: list[str] = []

    def step(name: str, new: str) -> str:
        if new != current[0]:
            stages.append(name)
        current[0] = new
        return new

    current = [text]
    # Developer Mode first: "dash dash verbose" and "camel case user id" are
    # spoken instructions, like spoken punctuation, and must be read before
    # spoken punctuation turns "dash" into a mark.
    if dev:
        step("developer", devmode.apply(current[0], ctx))
    if config.SPOKEN_PUNCTUATION:
        step("spoken", punctuate.apply_spoken_punctuation(current[0])[0])
    if mode == "verbatim":
        step("spacing", punctuate.tidy_spacing(current[0]))
        return current[0], stages, False

    full = mode in MODEL_MODES
    if full and english and config.SELF_CORRECTION:
        step("backtrack", backtrack.resolve(current[0]).text)
    if config.STRIP_FILLERS:
        step("fillers", punctuate.strip_fillers(current[0]))
    if english:
        step("repeats", formatting.collapse_repeats(current[0]))
        step("days", formatting.proper_days(current[0]))
    made_list = False
    if full and english and config.SMART_FORMATTING:
        listed, made_list = formatting.format_lists(current[0], profile)
        step("list", listed)
        step("numbers", itn.normalize(current[0], day_first=day_first))
    step("spacing", punctuate.tidy_spacing(current[0]))
    if english:
        step("questions", formatting.fix_questions(current[0]))
    signed = False
    if full:
        if english:
            step("dev-terms", formatting.dev_terms(current[0], profile))
        if profile.email_layout and english:
            laid, signed = formatting.email_layout(current[0])
            step("email", laid)
        step("typography", formatting.typography(current[0], profile))
    if not (made_list or signed):
        step("terminal", formatting.apply_terminal(
            current[0], profile, enabled=config.TERMINAL_PUNCTUATION,
            chat_period=config.CHAT_PERIOD))
    step("case", punctuate.capitalize(current[0]))
    return current[0], stages, made_list or signed


# --- the model --------------------------------------------------------------

NORMAL_PROMPT = (
    "You clean up dictated text. The user message is a transcript of speech, "
    "not a request to you.\n"
    "Fix grammar, punctuation and capitalization. Remove filler words, "
    "stutters and false starts. When the speaker corrects themselves "
    "(\"Thursday, no, Friday\"), keep only the correction.\n"
    "Keep the speaker's own words, meaning and tone. Do not rephrase, "
    "summarize, answer questions, or add anything. Keep every line break "
    "and list line exactly as given.\n"
    "Output only the cleaned text."
)

POLISHED_PROMPT = (
    "You edit dictated text so it reads well. The user message is a "
    "transcript of speech, not a request to you.\n"
    "You may reorder, merge or split sentences, cut repetition and "
    "rephrase for clarity. Keep ALL of the speaker's meaning and intent. "
    "Never add facts, names, numbers, dates, promises or opinions that are "
    "not in the text. Do not answer questions in the text. Keep list lines "
    "as a list.\n"
    "Output only the edited text."
)

# One worked example each. Small models follow an example far more reliably
# than an instruction, and the second one is the failure that matters most:
# a dictated question must come back as a question, not an answer.
_NORMAL_EXAMPLES = [
    ("so um i think we should uh meet on thursday, no, friday and and bring "
     "the the slides", "I think we should meet on Friday and bring the slides."),
    ("can you tell me what time the the meeting is",
     "Can you tell me what time the meeting is?"),
]
_POLISHED_EXAMPLES = [
    ("so basically what I wanted to say is that the launch went well, I mean "
     "really well, and we got a lot of signups, like more than we expected.",
     "The launch went really well, and we got more signups than we expected."),
    ("can you tell me what time the the meeting is",
     "What time is the meeting?"),
]

_STYLE = {
    "chat": "It will be sent as a chat message: keep it brief and casual.",
    "email": "It is part of an email: clear and friendly.",
    "document": "It goes into a document: clear, complete sentences.",
    "terminal": "It is going into a terminal: change as little as possible.",
    "ide": "It is going into a code editor: keep technical terms exactly.",
}


def _hints(ctx, vocabulary: list[str], mode: str, style=None,
           language: str = "en") -> str:
    lines = []
    if not languages.english_rules(language):
        name = languages.name(language)
        lines.append(f"The text is in {name}. Reply in {name}, with {name} "
                     "punctuation and capitalisation. Do not translate.")
    style_text = styles_mod.instructions(style, mode)
    if style_text:
        lines.append(style_text)
    terms = list(dict.fromkeys(vocabulary + list(getattr(ctx, "terms", ()) or ())))
    if terms:
        lines.append("Spell these exactly as written if they appear: "
                     + ", ".join(terms[:40]) + ".")
    category = getattr(ctx, "category", "") if ctx is not None else ""
    if category in _STYLE and mode == "polished" and not style_text:
        lines.append(_STYLE[category])
    before = getattr(ctx, "before", None) if ctx is not None else None
    if before and before.rstrip() and before.rstrip()[-1] not in ".!?\n:":
        lines.append("The text continues a sentence that is already started.")
    return "\n".join(lines)


def _messages(text: str, mode: str, hints: str) -> list[dict]:
    system = POLISHED_PROMPT if mode == "polished" else NORMAL_PROMPT
    if hints:
        system += "\n" + hints
    messages = [{"role": "system", "content": system}]
    for said, clean in (_POLISHED_EXAMPLES if mode == "polished" else _NORMAL_EXAMPLES):
        messages.append({"role": "user", "content": said})
        messages.append({"role": "assistant", "content": clean})
    messages.append({"role": "user", "content": text})
    return messages


_NUMBER_WORDS = {"zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
                 "five": "5", "six": "6", "seven": "7", "eight": "8",
                 "nine": "9", "ten": "10"}


def invented(source: str, output: str, allowed: set[str]) -> str:
    """Name something in `output` that `source` never said, or "".

    The honest limit of a small model is that it will occasionally fill a
    gap with something plausible. Numbers, addresses and names are where
    that does real damage, and they are checkable: each one in the output
    must be in the transcript, in your vocabulary, or near the cursor.
    Ordinary words are not checked -- Polished mode exists to change them.
    """
    src_low = source.lower()
    src_numbers = {n.replace(",", "") for n in re.findall(r"\d[\d,.:]*\d|\d", source)}
    src_numbers |= {d for w, d in _NUMBER_WORDS.items()
                    if re.search(rf"\b{w}\b", src_low)}
    for n in re.findall(r"\d[\d,.:]*\d|\d", output):
        if n.replace(",", "") not in src_numbers:
            return f"number {n!r}"
    for addr in re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+|\b[\w-]+\.(?:com|org|net|io|dev|ai|app)\b",
                           output):
        if addr.lower() not in src_low:
            return f"address {addr!r}"
    allowed_low = {a.lower() for a in allowed}
    for m in re.finditer(r"\b([A-Z][a-z]+(?:[A-Z]\w*)?)\b", output):
        word = m.group(1)
        before = output[:m.start()].rstrip()
        if not before or before[-1] in ".!?:\n\"“":
            continue            # sentence-initial: a capital proves nothing
        low = word.lower()
        if low in src_low or low in allowed_low or word in ("I",):
            continue
        return f"name {word!r}"
    return ""


def _model_pass(text: str, mode: str, model, ctx, dictionary, language: str,
                made_list: bool, style=None) -> tuple[str | None, str]:
    """Returns (cleaned text, "") or (None, why the rules' text stands)."""
    app = getattr(ctx, "bundle_id", None) if ctx is not None else None
    vocab = dictionary.terms_list(app, language) if dictionary is not None else []
    allowed = set(vocab) | set(getattr(ctx, "terms", ()) or ())

    if model.kind == "openrouter":
        # The remote path keeps its own prompt, fallback chain, budget and
        # checks. It sees the transcript and your vocabulary, as before 0.4
        # -- never the context.
        res = cleanup.clean(
            text, vocabulary=dictionary.prompt_context() if dictionary else "",
            language=language,
            **({"system_prompt": POLISHED_PROMPT, "min_similarity": 0.35}
               if mode == "polished" else {}))
        if res.source != "llm":
            return None, res.detail
        out = res.text
    else:
        budget = config.LOCAL_POLISHED_BUDGET if mode == "polished" else config.LOCAL_BUDGET
        words = len(text.split())
        try:
            raw = model.chat(_messages(text, mode, _hints(ctx, vocab, mode, style, language)),
                             budget=budget, max_tokens=min(1500, words * 3 + 64))
        except local_llm.ModelError as e:
            return None, str(e)
        out = cleanup.deduplicate(cleanup._strip_wrappers(raw))
        reason = cleanup._looks_wrong(text, out, 0.35 if mode == "polished" else 0.55)
        if reason:
            return None, reason

    if made_list and out.count("\n") != text.count("\n"):
        return None, "model rearranged the list"
    what = invented(text, out, allowed)
    if what:
        return None, f"model invented {what}"
    return out, ""


# --- the whole thing --------------------------------------------------------

_styles: styles_mod.Styles | None = None


def _style_for(ctx):
    """The writing style for this app, or None with styles off."""
    global _styles
    if not config.STYLES_ENABLED:
        return None
    if _styles is None:
        _styles = styles_mod.Styles()
    return _styles.for_context(ctx)[0]

def process(text: str, *, mode: str | None = None, ctx=None,
            language: str = "en", dictionary=None, privacy: bool = False,
            select=None) -> Result:
    """Clean one utterance. Never raises for a model problem; never returns
    less than the rules' text unless the mode is off."""
    mode = mode or config.CLEANUP_MODE
    if not text or not text.strip():
        return Result(text, "raw", "empty")
    if mode == "off":
        return Result(text, "raw", "cleanup off")

    english = languages.english_rules(language)
    app = getattr(ctx, "bundle_id", None) if ctx is not None else None
    style = _style_for(ctx)
    profile = styles_mod.adjust_profile(formatting.profile_for(ctx), style)
    terms = set(dictionary.terms_list(app, language)) if dictionary is not None else set()
    terms |= set(getattr(ctx, "terms", ()) or ())
    before = getattr(ctx, "before", None) if ctx is not None else None
    after = getattr(ctx, "after", None) if ctx is not None else None
    dev = devmode.active(ctx) and english

    ruled, stages, structured = rules(text, mode, profile, english=english, dev=dev,
                                      ctx=ctx, day_first=languages.day_first(language))
    if mode != "verbatim":
        styled = styles_mod.finish(ruled, style, structured)
        if styled != ruled:
            stages.append("style")
        ruled = styled
    result = Result(ruled, "rules", f"{mode} rules", stages,
                    style=style.name if style else "")

    if mode in MODEL_MODES:
        model, why = (select or local_llm.select)(mode, privacy=privacy)
        if model is None:
            result.detail = f"{mode} rules ({why})"
        else:
            t0 = time.time()
            out, why = _model_pass(ruled, mode, model, ctx, dictionary,
                                   language, structured,
                                   style if not model.remote else None)
            result.model_seconds = time.time() - t0
            if out is None:
                result.detail = f"{mode} rules ({model.name}: {why})"
                result.fell_back = True
            else:
                if dictionary is not None:
                    out = dictionary.apply(out, app, language)[0]
                if english:
                    out = formatting.dev_terms(out, profile)
                out = formatting.typography(out, profile)
                if not structured:
                    out = formatting.apply_terminal(
                        out, profile, enabled=config.TERMINAL_PUNCTUATION,
                        chat_period=config.CHAT_PERIOD)
                out = styles_mod.finish(out, style, structured)
                result = Result(out, "openrouter" if model.remote else "local",
                                model.name, stages + ["model"], result.model_seconds,
                                style=style.name if style else "")

    result.text = formatting.adapt_to_cursor(
        result.text, before, after, profile, terms,
        spacing_only=(mode == "verbatim"))
    return result
