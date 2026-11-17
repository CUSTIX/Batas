"""Download the laws and parse them into data/corpus.json (a developer step, needs internet).

The app itself never scrapes: it loads the committed data/corpus.json with `load_corpus`.
Re-run this only to refresh the text, then review the diff of data/corpus.json before committing.
Philippine statutes are not copyrighted (RA 8293, Sec. 176); only the law text is kept, with a link
to the page it came from.
"""

import json
import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

CHANROBLES = "https://chanrobles.com/legal4labor{page}.htm"
LABOR_CODE_PAGES = ["", "1", "2", "3", "4", "5", "6", "7"]
PD851 = "https://lawphil.net/statutes/presdecs/pd1975/pd_851_1975.html"
MO28 = "https://lawphil.net/executive/mo/mo1986/mo_28_1986.html"
USER_AGENT = "Mozilla/5.0 (compatible; batas-corpus-builder)"

BLOCK_TAGS = {"p", "br", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "td"}
# Site navigation and credit lines (dropped when a whole short line is only that)...
NOISE = re.compile(
    r"chanrobles|virtual law library|lawphil|arellano|copyright|back to|home page", re.I
)
NAV_LINE_MAX = 90
# ...and ChanRobles' hidden white-text watermark, which sits INSIDE real paragraphs: strip the
# words, keep the law text around them (dropping the whole line once lost Art. 95 (b)).
WATERMARK = re.compile(
    r"chan\s*robles\s*virtual\s*law\s*library|chanroblesvirtuallawlibrary|"
    r"chanrobles\s*virtual\s*law\s*library|chan\s*robles|chanrobles\w*",
    re.I,
)
ARTICLE = re.compile(r"^(?:ART|ARTICLE|Article|Art)\.?\s*(\d+)(-[A-Z])?\.\s*(.*)$")
# an article marker in the middle of a line starts a new line
ARTICLE_INLINE = re.compile(r"(?=\b(?:ART|Article)\.?\s+\d+(?:-[A-Z])?\.\s+[A-Z])")
ROMAN = re.compile(r"\b(Title|Chapter) ([ivxl]+)\b", re.I)
HEADING = re.compile(
    r"^(BOOK\s+[A-Z]+|PRELIMINARY TITLE|TITLE\s+[IVXL]+|CHAPTER\s+[IVXL]+)\b(.*)$", re.I
)
# "Right to service incentive leave. - (a) Every employee ..." -> heading, body
HEAD_SPLIT = re.compile(r"^(.{3,160}?)\.\s*[-–—]+\s*(.*)$", re.S)


class TextExtractor(HTMLParser):
    """HTML -> lines of text. Line breaks come from block tags only, not from the HTML source."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.buf, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in BLOCK_TAGS:
            self.flush()

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK_TAGS:
            self.flush()

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data.replace("\n", " ").replace("\r", " "))

    def flush(self):
        raw = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        self.buf = []
        if not raw:
            return
        if NOISE.search(raw) and len(WATERMARK.sub("", raw).strip()) < NAV_LINE_MAX:
            if not ARTICLE.match(raw):
                return  # a navigation or credit line, not law text
        line = re.sub(r"\s+", " ", WATERMARK.sub(" ", raw)).strip()
        if line:
            self.lines.append(line)

    @classmethod
    def lines_of(cls, html: str) -> list[str]:
        parser = cls()
        parser.feed(html)
        parser.flush()
        lines = []
        for line in parser.lines:
            lines.extend(part.strip() for part in ARTICLE_INLINE.split(line) if part.strip())
        return lines


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310 - fixed https URLs above
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        raw = response.read()
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CommandError(f"Can't decode {url}")


def split_heading(rest: str) -> tuple[str, str]:
    match = HEAD_SPLIT.match(rest)
    if match:
        return match.group(1).strip(), match.group(2).strip()
    first, _, body = rest.partition(". ")
    return first.strip()[:160], body.strip()


def parse_labor_code(pages: dict[str, str]) -> list[dict]:
    articles, seen = [], set()
    book = title = chapter = ""
    current = None
    for page_url, html in pages.items():
        for line in TextExtractor.lines_of(html):
            heading = HEADING.match(line)
            article = ARTICLE.match(line)
            if heading and not article:
                kind = heading.group(1).upper()
                label = ROMAN.sub(
                    lambda m: f"{m.group(1).title()} {m.group(2).upper()}",
                    " ".join(line.split()[:2]).title(),
                )
                if kind.startswith("BOOK") or kind.startswith("PRELIMINARY"):
                    book, title, chapter = (
                        (line.title() if kind.startswith("PRELIMINARY") else label),
                        "",
                        "",
                    )
                elif kind.startswith("TITLE"):
                    title, chapter = label.replace("Title", "Title"), ""
                else:
                    chapter = label
                current = None
                continue
            if article:
                number = article.group(1) + (article.group(2) or "")
                if (
                    number in seen
                ):  # the same article quoted again later (e.g. in a note): keep the first
                    current = None
                    continue
                seen.add(number)
                head, body = split_heading(article.group(3))
                current = {
                    "number": number,
                    "sort_key": int(article.group(1)),
                    "heading": head,
                    "path": " > ".join(p for p in (book, title, chapter) if p),
                    "paragraphs": [body] if body else [],
                    "url": page_url,
                }
                articles.append(current)
                continue
            if current is not None:
                current["paragraphs"].append(line)
    for a in articles:
        a["text"] = "\n".join(p for p in a.pop("paragraphs") if p)
    return [a for a in articles if a["text"]]


RULE_HEAD = re.compile(
    r"^(.+?)\s+(?=(?:All|As|The|A|An|Except|Distressed|Non-payment|Nothing|These|Every|Each|In|No|Employers|Any|For)\b)"
)


def parse_sections(
    lines: list[str], url: str, start: int, end: int, rule_headings: bool
) -> list[dict]:
    out = []
    for line in lines[start:end]:
        match = re.match(r"^Section\s+(\d+)\.\s*(.*)$", line)
        if not match:
            if out and line:  # navigation lines were already dropped by TextExtractor
                out[-1]["text"] += "\n" + line
            continue
        number, rest = match.group(1), match.group(2)
        head = ""
        if rule_headings:
            m = RULE_HEAD.match(rest)
            head = m.group(1).rstrip(".") if m and len(m.group(1)) < 80 else ""
            if head.split()[-1:] in (["of"], ["for"], ["to"], ["the"], ["and"]):  # cut mid-phrase
                head = " ".join(rest.split()[: len(head.split()) + 2])
        if not head:
            head = rest.split(".")[0][:90]
        out.append(
            {
                "number": number,
                "sort_key": int(number),
                "heading": head,
                "path": "",
                "text": rest,
                "url": url,
            }
        )
    return out


class Command(BaseCommand):
    help = "Download the Labor Code, PD 851 and MO 28 and write data/corpus.json (needs internet)."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(Path(settings.BASE_DIR) / "data" / "corpus.json"))

    def handle(self, *args, **options):
        pages = {
            CHANROBLES.format(page=p): fetch(CHANROBLES.format(page=p)) for p in LABOR_CODE_PAGES
        }
        labor = parse_labor_code(pages)

        pd_lines = TextExtractor.lines_of(fetch(PD851))
        rules_at = next(
            i
            for i, line in enumerate(pd_lines)
            if line.upper().startswith("RULES AND REGULATIONS IMPLEMENTING")
        )
        supplementary = next(
            (
                i
                for i, line in enumerate(pd_lines)
                if line.upper().startswith("SUPPLEMENTARY RULES")
            ),
            len(pd_lines),
        )
        decree = parse_sections(pd_lines, PD851, 0, rules_at, rule_headings=False)
        rules = parse_sections(pd_lines, PD851, rules_at, supplementary, rule_headings=True)

        mo_lines = TextExtractor.lines_of(fetch(MO28))
        mo_text = next(
            line for line in mo_lines if line.startswith("Section 1 of Presidential Decree No. 851")
        )
        mo = [
            {
                "number": "28",
                "sort_key": 28,
                "heading": "Modifying PD 851: all rank-and-file employees get a 13th month pay",
                "path": "",
                "text": mo_text,
                "url": MO28,
            }
        ]

        corpus = {
            "sources": [
                {
                    "slug": "labor-code",
                    "title": "Labor Code of the Philippines",
                    "citation": "Presidential Decree No. 442, as amended",
                    "short_label": "Art.",
                    "url": CHANROBLES.format(page=""),
                    "articles": labor,
                },
                {
                    "slug": "pd-851",
                    "title": "13th Month Pay Law",
                    "citation": "Presidential Decree No. 851 (1975)",
                    "short_label": "PD 851 Sec.",
                    "url": PD851,
                    "articles": decree,
                },
                {
                    "slug": "pd-851-rules",
                    "title": "Rules Implementing PD 851",
                    "citation": "Rules and Regulations Implementing PD 851 (1975)",
                    "short_label": "PD 851 Rules Sec.",
                    "url": PD851,
                    "articles": rules,
                },
                {
                    "slug": "mo-28",
                    "title": "Memorandum Order No. 28 (1986)",
                    "citation": "Memorandum Order No. 28, s. 1986",
                    "short_label": "MO",
                    "url": MO28,
                    "articles": mo,
                },
            ]
        }
        out = Path(options["out"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(corpus, ensure_ascii=False, indent=1), encoding="utf-8")
        for s in corpus["sources"]:
            self.stdout.write(f"{s['slug']}: {len(s['articles'])} articles")
        self.stdout.write(self.style.SUCCESS(f"Wrote {out}"))
