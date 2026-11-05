"""Conservative link removal for QQ chat output, not for tool requests.

QQ may reject bare domains as well as URLs. This is a local heuristic, not an
exact reproduction of QQ's detector; domain-shaped filenames may also match.
"""

import re

_OMITTED = "（链接已省略）"
_MARKDOWN_LINK = re.compile(r"!?\[([^\]\n]*)\]\([^\n)]*\)")
_REFERENCE_LINK = re.compile(r"\[([^\]\n]+)\]\[[^\]\n]*\]")
_REFERENCE_DEFINITION = re.compile(r"(?m)^\s{0,3}\[[^\]\n]+\]:[^\n]*(?:\n|$)")
_URL = re.compile(r"(?:https?|ftp)://[^\s<>{}()\"'，。；！？、]+", re.IGNORECASE)
_DOMAIN = re.compile(
    r"(?<![A-Za-z0-9_-])"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"(?:xn--[A-Za-z0-9-]{2,59}|[A-Za-z]{2,63})"
    r"(?![A-Za-z0-9_-])(?::[0-9]{1,5})?"
    r"(?:/[^\s<>\[\]{}()\"'，。；！？、]*)?",
    re.IGNORECASE,
)
_IDN = re.compile(r"[A-Za-z0-9\u4e00-\u9fff-]+(?:\.[A-Za-z0-9\u4e00-\u9fff-]+)*"
                  r"\.(?:中国|公司|网络|网址|在线|商城|中文网)"
                  r"(?:/[^\s<>\[\]{}()\"'，。；！？、]*)?")
_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")


def without_links(text: str) -> str:
    """Removes URL/domain shapes, retaining link labels and ordinary decimals.

    This must only run on final display text. Real URLs remain intact inside
    search/fetch requests so evidence retrieval is unaffected.
    """
    text = _REFERENCE_DEFINITION.sub("", text)
    text = _MARKDOWN_LINK.sub(r"\1", text)
    text = _REFERENCE_LINK.sub(r"\1", text)
    text = _URL.sub(_OMITTED, text)
    text = _DOMAIN.sub(_OMITTED, text)
    text = _IDN.sub(_OMITTED, text)
    return _IPV4.sub(_OMITTED, text)


def source_label(text: str) -> str:
    """Returns a readable source label with link-only text removed."""
    text = text.replace("<", "＜").replace(">", "＞")
    return " ".join(without_links(text).replace(_OMITTED,
                                                "").split()).strip(" -—|：:")
