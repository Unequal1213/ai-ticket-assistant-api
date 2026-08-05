import re
from html.parser import HTMLParser
from unicodedata import normalize

EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[A-Z0-9._%+-]+\s*@\s*"
    r"[A-Z0-9-]+(?:\s*\.\s*[A-Z0-9-]+)+(?![\w-])",
    re.IGNORECASE,
)
CARD_PATTERN = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d ()-]{5,}\d)(?!\w)")
LABELED_ID_PATTERN = re.compile(
    r"\b(?:passport|ssn|tax[ _-]?id|national[ _-]?id|"
    r"паспорт|снилс|инн)\s*[:#№-]?\s*"
    r"(?:[A-ZА-Я]{0,4}\d[A-ZА-Я0-9-]{4,20}|\d{3,4}[ -]\d{6})",
    re.IGNORECASE,
)


class _PlainTextExtractor(HTMLParser):
    _BLOCK_TAGS = {
        "article",
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "p",
        "section",
        "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._BLOCK_TAGS:
            self.parts.append("\n")


def _redact_phone_match(match: re.Match[str]) -> str:
    value = match.group(0)
    digit_count = sum(character.isdigit() for character in value)
    if 7 <= digit_count <= 15:
        return "[REDACTED_PHONE]"
    return value


def redact_pii(text: str) -> str:
    """Mask a conservative set of detectable PII patterns.

    This is risk reduction, not a guarantee that all personal data is removed.
    """

    redacted = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", text)
    redacted = CARD_PATTERN.sub("[REDACTED_CARD]", redacted)
    redacted = LABELED_ID_PATTERN.sub("[REDACTED_ID]", redacted)
    return PHONE_PATTERN.sub(_redact_phone_match, redacted)


def normalize_untrusted_text(text: str) -> str:
    """Decode HTML, normalize Unicode, and remove unsafe control characters."""

    parser = _PlainTextExtractor()
    parser.feed(text)
    parser.close()
    plain_text = "".join(parser.parts)
    normalized = normalize("NFKC", plain_text)
    without_controls = "".join(
        character
        for character in normalized
        if ord(character) >= 32 or character in "\n\t"
    )
    normalized_lines = (
        " ".join(line.split()) for line in without_controls.splitlines()
    )
    return "\n".join(line for line in normalized_lines if line)


def prepare_external_text(text: str) -> str:
    normalized = normalize_untrusted_text(text)
    redacted = redact_pii(normalized)
    if redact_pii(redacted) != redacted:
        raise ValueError("PII redaction produced an unstable outbound value")
    return redacted
