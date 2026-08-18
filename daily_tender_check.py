#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAŠINAC d.o.o. - CEJN TENDER MONITOR
=====================================
Dnevna provjera novih tendera na crnogorskom portalu javnih nabavki (CEJN)
i slanje e-mail izvještaja sa tenderima relevantnim za mašinske/termotehničke
instalacije.

Izvor podataka:  POST https://cejn.gov.me/api/cadocuments/GetTenders
Zavisnosti:      requests
"""

import os
import re
import ssl
import sys
import time
import smtplib
import logging
import unicodedata
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr

import requests

# =============================================================================
# 1. KONFIGURACIJA
# =============================================================================

VERSION = "V5"
PAGE_SIZE = 100
MAX_PAGES = 5

API_URL = "https://cejn.gov.me/api/cadocuments/GetTenders"
TENDER_URL_TEMPLATE = "https://cejn.gov.me/tenders/view-tender/{id}"

# Statusi koje CEJN frontend šalje (aktivni / u toku / objavljeni postupci)
TENDER_STATUSES = ["1", "512", "64", "4", "8"]

# Zadržavamo samo tendere sa ovim lifecycle opisom
ACTIVE_LIFECYCLE_CAPTION = "u toku"

REQUEST_TIMEOUT = 45          # sekundi po zahtjevu
MAX_RETRIES_PER_PAGE = 3      # pokušaja po stranici prije odustajanja
RETRY_BACKOFF_SECONDS = 4     # pauza između pokušaja (množi se rednim brojem)
PAUSE_BETWEEN_PAGES = 1.0     # pauza između stranica (da ne opterećujemo server)

# Ako je True, e-mail se šalje i kada nema direktno relevantnih tendera,
# a postoje građevinski kandidati za ručnu provjeru.
SEND_EMAIL_FOR_CANDIDATES_ONLY = False

# NAPOMENA O DETALJIMA TENDERA (drugi nivo provjere):
# Javni CEJN endpoint za detalje pojedinačnog tendera nije pouzdano utvrđen,
# pa NIJE izmišljen niti ugrađen. Kandidati se za sada samo evidentiraju.
# Ako u DevTools -> Network potvrdite tačan endpoint (npr. pri otvaranju
# stranice view-tender), upišite ga ovdje i drugi nivo provjere se aktivira.
DETAIL_API_URL = None         # npr. "https://cejn.gov.me/api/cadocuments/GetTender"

# E-mail (postojeći GitHub Secrets - NE MIJENJATI)
EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

HTTP_HEADERS = {
    "Content-Type": "application/json;charset=UTF-8",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "sr,en-US;q=0.8,en;q=0.6",
    "Origin": "https://cejn.gov.me",
    "Referer": "https://cejn.gov.me/tenders",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
}

# =============================================================================
# 2. KLJUČNE RIJEČI
# =============================================================================

STRONG_KEYWORDS = [
    "mašinske instalacije",
    "masinske instalacije",
    "mašinska instalacija",
    "termotehničke instalacije",
    "termotehnicke instalacije",
    "termotehnika",
    "termotehnička oprema",
    "hvac",
    "ventilacija",
    "klimatizacija",
    "grijanje",
    "grejanje",
    "hlađenje",
    "hladjenje",
    "sprinkler",
    "odimljavanje",
    "toplotna pumpa",
    "toplotne pumpe",
    "kotlarnica",
    "vrf",
    "vrv",
    "fan coil",
    "fancoil",
    "ventilokonvektor",
    "rekuperacija",
    "rekuperator",
    "klima komora",
    "rashladni sistem",
    "rashladna instalacija",
    "centralno grijanje",
    "centralno grejanje",
    "podno grijanje",
    "podno grejanje",
    "toplovod",
    "automatsko gašenje požara",
    "gašenje požara",
    "dojava požara i gašenje",
]

MEDIUM_KEYWORDS = [
    "ventilator",
    "klima uređaj",
    "radijator",
    "cirkulaciona pumpa",
    "ekspanziona posuda",
    "izmjenjivač toplote",
    "izmjenjivac toplote",
    "bojler",
    "solarni kolektor",
    "cjevovod grijanja",
    "cijevna mreža",
    "toplotna stanica",
    "rashladni uređaj",
    "split sistem",
    "multi split",
    "chiller",
    "čiler",
    "pumpna stanica",
    "kotao",
    "dimnjak",
    "vodovod i kanalizacija",
]

# Građevinski tenderi koji često "kriju" mašinske instalacije u sebi
CONSTRUCTION_KEYWORDS = [
    "adaptacija",
    "rekonstrukcija",
    "izgradnja",
    "dogradnja",
    "sanacija",
    "hotel",
    "bolnica",
    "škola",
    "skola",
    "vrtić",
    "vrtic",
    "garaža",
    "garaza",
    "sportska hala",
    "poslovni objekat",
    "stambeni objekat",
    "dom zdravlja",
    "klinički centar",
    "klinicki centar",
]

STRONG_POINTS = 3
MEDIUM_POINTS = 1
RELEVANCE_THRESHOLD = 2  # minimalni skor da bi tender ušao u e-mail

# =============================================================================
# 3. LOGGING
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("cejn")

# =============================================================================
# 4. NORMALIZACIJA TEKSTA I PRETRAGA KLJUČNIH RIJEČI
# =============================================================================


def normalize(text):
    """Mala slova, bez dijakritika (č/ć->c, š->s, ž->z, đ->dj), bez interpunkcije."""
    if not text:
        return ""
    t = str(text).lower().replace("đ", "dj").replace("Đ", "dj")
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def build_keyword_pattern(keyword):
    """
    Pravi regex koji tolerantno hvata padeže.
    Primjer: 'toplotna pumpa' -> hvata i 'toplotne pumpe', 'toplotnih pumpi'.
    """
    tokens = normalize(keyword).split()
    parts = []
    for token in tokens:
        if len(token) <= 4:
            parts.append(re.escape(token))
        elif len(token) <= 6:
            parts.append(re.escape(token[:-1]) + r"[a-z]{0,3}")
        else:
            parts.append(re.escape(token[:-2]) + r"[a-z]{0,4}")
    return r"\b" + r"\s+".join(parts) + r"\b"


def compile_keywords(keywords):
    """Vraća listu parova (originalna_rijec, kompajlirani_regex), bez duplikata."""
    compiled = []
    seen_patterns = set()
    for kw in keywords:
        if not normalize(kw):
            continue
        pattern_text = build_keyword_pattern(kw)
        if pattern_text in seen_patterns:
            continue
        seen_patterns.add(pattern_text)
        compiled.append((kw, re.compile(pattern_text)))
    return compiled


STRONG_PATTERNS = compile_keywords(STRONG_KEYWORDS)
MEDIUM_PATTERNS = compile_keywords(MEDIUM_KEYWORDS)
CONSTRUCTION_PATTERNS = compile_keywords(CONSTRUCTION_KEYWORDS)


def find_matches(normalized_text, patterns):
    """
    Vraća listu originalnih ključnih riječi pronađenih u tekstu.
    Ako je jedna fraza sadržana u drugoj (npr. 'grijanje' i 'podno grijanje'),
    zadržava se samo preciznija (duža) fraza.
    """
    hits = [kw for kw, pattern in patterns if pattern.search(normalized_text)]
    normalized_hits = {kw: normalize(kw) for kw in hits}
    result = []
    for kw in hits:
        current = normalized_hits[kw]
        if any(current != other and current in other for other in normalized_hits.values()):
            continue
        result.append(kw)
    return result


# =============================================================================
# 5. PREUZIMANJE PODATAKA SA CEJN API-JA
# =============================================================================


def build_payload(skip):
    """Payload identičan onom koji šalje CEJN frontend."""
    return {
        "pageSize": PAGE_SIZE,
        "tenderStatuses": TENDER_STATUSES,
        "skip": skip,
        "top": PAGE_SIZE,
        "procedureType": 0,
        "subjectType": 0,
        "justCanApply": False,
        "sort": None,
        "myTenders": False,
        "useAdditionalCaSearch": False,
        "caType": 0,
        "caStateId": 0,
        "statuses": ",".join(TENDER_STATUSES),
    }


def extract_items(data):
    """Iz odgovora API-ja izvlači listu tendera."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("value", "Value", "data", "items", "result"):
            items = data.get(key)
            if isinstance(items, list):
                return items
    return []


def fetch_page(session, page_index):
    """
    Preuzima jednu stranicu. Vraća listu tendera.
    Podiže izuzetak samo ako svi pokušaji propadnu.
    """
    skip = page_index * PAGE_SIZE
    last_error = None

    for attempt in range(1, MAX_RETRIES_PER_PAGE + 1):
        try:
            response = session.post(
                API_URL,
                json=build_payload(skip),
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return extract_items(response.json())
        except (requests.exceptions.RequestException, ValueError) as exc:
            last_error = exc
            log.warning(
                "Greška na stranici %d (pokušaj %d/%d): %s",
                page_index + 1, attempt, MAX_RETRIES_PER_PAGE, exc,
            )
            if attempt < MAX_RETRIES_PER_PAGE:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    raise RuntimeError("Neuspješno preuzimanje stranice %d: %s" % (page_index + 1, last_error))


def fetch_tenders():
    """
    Preuzima najviše MAX_PAGES * PAGE_SIZE tendera.
    Ako pukne konekcija na nekoj stranici, zadržava sve prethodno preuzeto
    i prekida dalje preuzimanje (nikada ne vraća praznu listu bez razloga).
    """
    tenders = []
    seen_ids = set()
    total_count_reported = None

    with requests.Session() as session:
        session.headers.update(HTTP_HEADERS)

        for page_index in range(MAX_PAGES):
            log.info("Preuzimam stranicu %d/%d", page_index + 1, MAX_PAGES)

            try:
                items = fetch_page(session, page_index)
            except RuntimeError as exc:
                log.error("%s", exc)
                if tenders:
                    log.warning(
                        "Prekidam preuzimanje, nastavljam analizu sa %d već preuzetih tendera.",
                        len(tenders),
                    )
                else:
                    log.error("Nijedan tender nije preuzet.")
                break

            if not items:
                log.info("Stranica %d je prazna - prekidam preuzimanje.", page_index + 1)
                break

            new_on_page = 0
            for item in items:
                if not isinstance(item, dict):
                    continue
                if total_count_reported is None and item.get("totalCount"):
                    total_count_reported = item.get("totalCount")
                tender_id = item.get("id")
                if tender_id in seen_ids:
                    continue
                seen_ids.add(tender_id)
                tenders.append(item)
                new_on_page += 1

            log.info(
                "Stranica %d/%d: %d zapisa (novih: %d), ukupno preuzeto: %d",
                page_index + 1, MAX_PAGES, len(items), new_on_page, len(tenders),
            )

            if len(items) < PAGE_SIZE:
                log.info("Posljednja stranica sa podacima - prekidam preuzimanje.")
                break

            if page_index < MAX_PAGES - 1:
                time.sleep(PAUSE_BETWEEN_PAGES)

    if total_count_reported:
        log.info("CEJN prijavljuje ukupno %s tendera u bazi (mi gledamo samo najnovije).",
                 total_count_reported)

    return tenders


# =============================================================================
# 6. ANALIZA I FILTRIRANJE
# =============================================================================


def is_active(tender):
    caption = (tender.get("lifecycleCaption") or "").strip().lower()
    return normalize(caption) == normalize(ACTIVE_LIFECYCLE_CAPTION)


def format_date(value):
    """'2026-08-18T19:00:00' -> '18.08.2026. 19:00'"""
    if not value:
        return "-"
    text = str(value).strip().replace("Z", "")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%d.%m.%Y. %H:%M")
        except ValueError:
            continue
    return text


def relevance_label(score, strong_hits):
    if strong_hits >= 2 or score >= 6:
        return "VISOKA"
    if strong_hits >= 1 or score >= 3:
        return "SREDNJA"
    return "NISKA"


def analyze_tender(tender):
    """Vraća rječnik sa rezultatom analize jednog tendera."""
    title = tender.get("title") or ""
    authority = tender.get("contractAuthority") or ""
    contract_type = tender.get("typeOfContractCaption") or ""

    searchable = normalize(" ".join([title, authority, contract_type]))

    strong = find_matches(searchable, STRONG_PATTERNS)
    medium = find_matches(searchable, MEDIUM_PATTERNS)
    construction = find_matches(normalize(title), CONSTRUCTION_PATTERNS)

    score = len(strong) * STRONG_POINTS + len(medium) * MEDIUM_POINTS

    tender_id = tender.get("id")
    return {
        "id": tender_id,
        "title": title.strip() or "(bez naziva)",
        "authority": authority.strip() or "-",
        "contract_type": contract_type.strip() or "-",
        "procedure_type": (tender.get("typeOfProcedureCaption") or "-").strip(),
        "status": (tender.get("lifecycleCaption") or "-").strip(),
        "publish_date": format_date(tender.get("publishDate") or tender.get("createdDate")),
        "url": TENDER_URL_TEMPLATE.format(id=tender_id),
        "strong": strong,
        "medium": medium,
        "construction": construction,
        "score": score,
        "relevance": relevance_label(score, len(strong)),
    }


def analyze_tenders(tenders):
    """Vraća (relevantni, kandidati_za_provjeru)."""
    relevant = []
    candidates = []

    for tender in tenders:
        result = analyze_tender(tender)
        if result["score"] >= RELEVANCE_THRESHOLD:
            relevant.append(result)
        elif result["construction"]:
            candidates.append(result)

    relevant.sort(key=lambda r: r["score"], reverse=True)
    return relevant, candidates


# =============================================================================
# 7. HTML E-MAIL
# =============================================================================


def html_escape(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


RELEVANCE_COLORS = {
    "VISOKA": "#1b7f3b",
    "SREDNJA": "#b8860b",
    "NISKA": "#6c757d",
}


def render_row(label, value):
    return (
        '<tr>'
        '<td style="padding:4px 10px 4px 0;color:#6c757d;font-size:13px;white-space:nowrap;">'
        + html_escape(label)
        + '</td>'
        '<td style="padding:4px 0;color:#212529;font-size:13px;">'
        + html_escape(value)
        + '</td>'
        '</tr>'
    )


def render_tender_card(item, index):
    color = RELEVANCE_COLORS.get(item["relevance"], "#6c757d")
    keywords = item["strong"] + item["medium"]
    keywords_text = ", ".join(keywords) if keywords else "-"

    rows = "".join([
        render_row("CEJN ID:", item["id"]),
        render_row("Naručilac:", item["authority"]),
        render_row("Vrsta predmeta:", item["contract_type"]),
        render_row("Vrsta postupka:", item["procedure_type"]),
        render_row("Status:", item["status"]),
        render_row("Datum objave:", item["publish_date"]),
        render_row("Relevantnost:", "%s (skor %d)" % (item["relevance"], item["score"])),
        render_row("Ključne riječi:", keywords_text),
    ])

    return (
        '<div style="border:1px solid #dee2e6;border-left:5px solid ' + color + ';'
        'border-radius:6px;padding:16px;margin-bottom:16px;background:#ffffff;">'
        '<div style="font-size:12px;color:#adb5bd;margin-bottom:4px;">#' + str(index) + '</div>'
        '<div style="font-size:16px;font-weight:bold;color:#12263f;margin-bottom:10px;">'
        + html_escape(item["title"]) + '</div>'
        '<table cellpadding="0" cellspacing="0" border="0" style="width:100%;">' + rows + '</table>'
        '<div style="margin-top:14px;">'
        '<a href="' + html_escape(item["url"]) + '" '
        'style="display:inline-block;background:#0b5ed7;color:#ffffff;text-decoration:none;'
        'padding:10px 18px;border-radius:4px;font-size:13px;font-weight:bold;">'
        'OTVORI TENDER NA CEJN</a>'
        '</div>'
        '<div style="margin-top:8px;font-size:11px;color:#adb5bd;">'
        + html_escape(item["url"]) + '</div>'
        '</div>'
    )


def render_candidate_row(item):
    return (
        '<li style="margin-bottom:10px;font-size:13px;color:#212529;">'
        '<strong>' + html_escape(item["title"]) + '</strong><br>'
        '<span style="color:#6c757d;">' + html_escape(item["authority"])
        + ' &middot; ID ' + html_escape(item["id"])
        + ' &middot; ' + html_escape(item["publish_date"]) + '</span><br>'
        '<span style="color:#6c757d;">Razlog: ' + html_escape(", ".join(item["construction"])) + '</span><br>'
        '<a href="' + html_escape(item["url"]) + '" style="color:#0b5ed7;">'
        + html_escape(item["url"]) + '</a>'
        '</li>'
    )


def build_email_html(relevant, candidates, stats):
    today = datetime.now().strftime("%d.%m.%Y.")

    cards = "".join(render_tender_card(item, i) for i, item in enumerate(relevant, start=1))
    if not cards:
        cards = ('<p style="font-size:13px;color:#6c757d;">'
                 'Danas nema direktno relevantnih tendera.</p>')

    candidates_html = ""
    if candidates:
        candidates_html = (
            '<h3 style="font-size:15px;color:#12263f;margin:28px 0 10px 0;">'
            'Građevinski tenderi - kandidati za ručnu provjeru (' + str(len(candidates)) + ')</h3>'
            '<p style="font-size:12px;color:#6c757d;margin:0 0 10px 0;">'
            'Naslovi ne pominju mašinske instalacije, ali je riječ o objektima kod kojih '
            'tenderska dokumentacija često sadrži termotehničke radove.</p>'
            '<ul style="padding-left:18px;margin:0;">'
            + "".join(render_candidate_row(item) for item in candidates)
            + '</ul>'
        )

    return (
        '<!DOCTYPE html><html><head><meta charset="UTF-8"></head>'
        '<body style="margin:0;padding:0;background:#f1f3f5;">'
        '<div style="max-width:760px;margin:0 auto;padding:24px;'
        'font-family:Arial,Helvetica,sans-serif;">'
        '<div style="background:#12263f;color:#ffffff;padding:20px 24px;border-radius:6px;">'
        '<div style="font-size:20px;font-weight:bold;">MAŠINAC d.o.o. - CEJN Tender Monitor</div>'
        '<div style="font-size:13px;color:#c7d2e0;margin-top:6px;">'
        + today + ' &middot; verzija ' + VERSION + '</div>'
        '</div>'
        '<p style="font-size:13px;color:#495057;margin:18px 0 6px 0;">'
        'Pregledano ' + str(stats["fetched"]) + ' najnovijih tendera &middot; '
        'aktivnih ("U toku"): ' + str(stats["active"]) + ' &middot; '
        'relevantnih: <strong>' + str(len(relevant)) + '</strong> &middot; '
        'kandidata za provjeru: ' + str(len(candidates)) + '</p>'
        '<h3 style="font-size:15px;color:#12263f;margin:22px 0 12px 0;">'
        'Relevantni tenderi (' + str(len(relevant)) + ')</h3>'
        + cards
        + candidates_html
        + '<p style="font-size:11px;color:#adb5bd;margin-top:28px;border-top:1px solid #dee2e6;'
        'padding-top:12px;">Automatska poruka - CEJN Tender Monitor ' + VERSION
        + ' &middot; izvor: cejn.gov.me</p>'
        '</div></body></html>'
    )


def send_email(relevant, candidates, stats):
    if not EMAIL_USER or not EMAIL_PASSWORD or not RECIPIENT_EMAIL:
        log.error("Nedostaju EMAIL_USER / EMAIL_PASSWORD / RECIPIENT_EMAIL - e-mail nije poslat.")
        return False

    recipients = [r.strip() for r in re.split(r"[,;]", RECIPIENT_EMAIL) if r.strip()]
    if not recipients:
        log.error("Lista primalaca je prazna - e-mail nije poslat.")
        return False

    subject = "MAŠINAC | %d relevantnih CEJN tendera | %s" % (
        len(relevant), datetime.now().strftime("%d.%m.%Y"),
    )

    message = MIMEText(build_email_html(relevant, candidates, stats), "html", "utf-8")
    message["Subject"] = Header(subject, "utf-8")
    message["From"] = formataddr((str(Header("MASINAC Tender Monitor", "utf-8")), EMAIL_USER))
    message["To"] = ", ".join(recipients)

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=60) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(EMAIL_USER, EMAIL_PASSWORD)
            server.sendmail(EMAIL_USER, recipients, message.as_string())
        log.info("E-mail poslat na: %s", ", ".join(recipients))
        return True
    except Exception as exc:  # noqa: BLE001 - želimo da workflow prijavi grešku, ali čitljivo
        log.error("Slanje e-maila nije uspjelo: %s", exc)
        return False


# =============================================================================
# 8. MAIN
# =============================================================================


def main():
    log.info("=" * 70)
    log.info("MAŠINAC - CEJN TENDER MONITOR %s", VERSION)
    log.info("VERSION = %s", VERSION)
    log.info("PAGE_SIZE = %d", PAGE_SIZE)
    log.info("MAX_PAGES = %d", MAX_PAGES)
    log.info("Maksimalno tendera za analizu: %d", PAGE_SIZE * MAX_PAGES)
    log.info("API: %s", API_URL)
    log.info("=" * 70)

    tenders = fetch_tenders()
    log.info("Ukupno preuzeto tendera: %d", len(tenders))

    if not tenders:
        log.error("Nema preuzetih tendera - završavam bez slanja e-maila.")
        return 1

    active = [t for t in tenders if is_active(t)]
    log.info("Aktivnih tendera (lifecycleCaption = 'U toku'): %d", len(active))

    relevant, candidates = analyze_tenders(active)

    log.info("-" * 70)
    log.info("RELEVANTNIH TENDERA: %d", len(relevant))
    for item in relevant:
        log.info(
            "  [%s | skor %d] %s | %s | %s",
            item["relevance"], item["score"], item["id"], item["title"], item["url"],
        )

    log.info("-" * 70)
    log.info("GRAĐEVINSKI KANDIDATI ZA DETALJNU PROVJERU: %d", len(candidates))
    for item in candidates:
        log.info(
            "  [KANDIDAT] %s | %s | ključne riječi: %s | %s",
            item["id"], item["title"], ", ".join(item["construction"]), item["url"],
        )

    if DETAIL_API_URL:
        log.info("DETAIL_API_URL je podešen (%s) - drugi nivo provjere se može aktivirati.",
                 DETAIL_API_URL)
    else:
        log.info("Drugi nivo provjere nije aktivan: javni endpoint za detalje "
                 "pojedinačnog tendera nije potvrđen (DETAIL_API_URL = None).")

    log.info("-" * 70)

    stats = {"fetched": len(tenders), "active": len(active)}

    should_send = bool(relevant) or (SEND_EMAIL_FOR_CANDIDATES_ONLY and bool(candidates))
    if should_send:
        send_email(relevant, candidates, stats)
    else:
        log.info("Nema relevantnih tendera - e-mail se ne šalje.")

    log.info("Završeno (%s).", VERSION)
    return 0


if __name__ == "__main__":
    sys.exit(main())
