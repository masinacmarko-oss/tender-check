import os
import re
import smtplib
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests


# ============================================================
# MAŠINAC D.O.O. - CEJN TENDER MONITOR
# ============================================================

VERSION = "V4"

CEJN_BASE_URL = "https://cejn.gov.me"
CEJN_API_URL = "https://cejn.gov.me/api/cadocuments/GetTenders"
CEJN_TENDER_URL = "https://cejn.gov.me/tenders/view-tender/"


# ============================================================
# PODEŠAVANJA
# ============================================================

PAGE_SIZE = 100
MAX_PAGES = 5

# Maksimalno 500 najnovijih postupaka


# ============================================================
# EMAIL - POSTOJEĆI GITHUB SECRETS
# ============================================================

EMAIL_USER = os.getenv("EMAIL_USER", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL", "")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


# ============================================================
# LOGOVANJE
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
# KLJUČNE RIJEČI - VISOK PRIORITET
# ============================================================

HIGH_PRIORITY_KEYWORDS = [
    "mašinske instalacije",
    "masinske instalacije",
    "termotehničke instalacije",
    "termotehnicke instalacije",
    "termotehnika",
    "hvac",

    "ventilacija",
    "ventilaciona",
    "ventilacione",
    "ventilacioni",

    "klimatizacija",
    "klimatizaciona",
    "klimatizacione",
    "klimatizacioni",

    "grijanje",
    "grejanje",

    "hlađenje",
    "hladjenje",

    "sprinkler",
    "sprinklerski",

    "odimljavanje",
    "odvođenje dima",
    "odvodjenje dima",

    "toplotna pumpa",
    "toplotne pumpe",

    "kotlarnica",
    "kotlarnice",

    "vrf",
    "vrv",

    "fan coil",
    "fan-coil",
    "fancoil",

    "ventilokonvektor",
    "ventilokonvektori",

    "rekuperacija",
    "rekuperator",

    "klima komora",
    "klima komore",
    "klimakomora",

    "rashladni sistem",
    "rashladni sistemi",
    "rashladna instalacija",
    "rashladne instalacije",

    "centralno grijanje",
    "centralno grejanje",

    "podno grijanje",
    "podno grejanje",

    "toplovod",

    "automatsko gašenje požara",
    "automatsko gasenje pozara",

    "gašenje požara",
    "gasenje pozara"
]


# ============================================================
# KLJUČNE RIJEČI - SREDNJI PRIORITET
# ============================================================

MEDIUM_PRIORITY_KEYWORDS = [
    "ventilator",
    "ventilatori",

    "klima uređaj",
    "klima uredjaj",
    "klima uređaji",
    "klima uredjaji",

    "radijator",
    "radijatori",

    "cirkulaciona pumpa",
    "cirkulacione pumpe",

    "ekspanziona posuda",

    "izmjenjivač toplote",
    "izmenjivač toplote",

    "bojler",
    "bojleri",

    "solarni kolektor",
    "solarni kolektori",
    "solarno grijanje",

    "cjevovod grijanja",
    "cevovod grejanja",

    "cijevna mreža",
    "cevna mreza",

    "toplotna stanica",

    "rashladni uređaj",
    "rashladni uredjaj",

    "split sistem",
    "multi split",

    "chiller",
    "čiler",
    "ciler",

    "pumpna stanica"
]


# ============================================================
# GRAĐEVINSKI PROJEKTI ZA KASNIJU DETALJNU PROVJERU
# ============================================================

PROJECT_KEYWORDS = [
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
    "klinicki centar"
]


# ============================================================
# NORMALIZACIJA
# ============================================================

def normalize_text(text):
    if not text:
        return ""

    text = str(text).lower()
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# CEJN SESSION
# ============================================================

def create_cejn_session():
    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/130.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": CEJN_BASE_URL,
        "Referer": CEJN_BASE_URL + "/tenders"
    })

    return session


# ============================================================
# PREUZIMANJE TENDERA
# ============================================================

def fetch_tenders_from_cejn():
    logger.info("")
    logger.info("=" * 70)
    logger.info("CEJN - PREUZIMANJE NAJNOVIJIH TENDERA")
    logger.info("=" * 70)

    logger.info(f"VERSION = {VERSION}")
    logger.info(f"PAGE_SIZE = {PAGE_SIZE}")
    logger.info(f"MAX_PAGES = {MAX_PAGES}")
    logger.info(
        f"Maksimalno provjeravamo {PAGE_SIZE * MAX_PAGES} postupaka."
    )

    session = create_cejn_session()

    active_tenders = []
    seen_ids = set()

    for page_index in range(MAX_PAGES):
        page_number = page_index + 1
        skip = page_index * PAGE_SIZE

        logger.info("")
        logger.info(
            f"Preuzimam stranicu {page_number}/{MAX_PAGES}..."
        )

        payload = {
            "pageSize": PAGE_SIZE,

            "tenderStatuses": [
                "1",
                "512",
                "64",
                "4",
                "8"
            ],

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

            "statuses": "1,512,64,4,8"
        }

        try:
            response = session.post(
                CEJN_API_URL,
                json=payload,
                timeout=30
            )

            logger.info(
                f"HTTP status: {response.status_code}"
            )

            response.raise_for_status()

            data = response.json()
            items = data.get("value", [])

            if not isinstance(items, list):
                logger.warning(
                    "CEJN nije vratio očekivanu listu tendera."
                )
                break

            logger.info(
                f"Primljeno sa stranice: {len(items)}"
            )

            if not items:
                logger.info("Nema više tendera.")
                break

            for item in items:
                tender_id = item.get("id")

                if not tender_id:
                    continue

                if tender_id in seen_ids:
                    continue

                seen_ids.add(tender_id)

                status = (
                    item.get("lifecycleCaption", "")
                    or ""
                )

                # SAMO AKTIVNI
                if normalize_text(status) != "u toku":
                    continue

                tender = {
                    "id": tender_id,

                    "title": (
                        item.get("title", "")
                        or ""
                    ),

                    "contract_authority": (
                        item.get(
                            "contractAuthority",
                            ""
                        )
                        or ""
                    ),

                    "contract_type": (
                        item.get(
                            "typeOfContractCaption",
                            ""
                        )
                        or ""
                    ),

                    "procedure_type": (
                        item.get(
                            "typeOfProcedureCaption",
                            ""
                        )
                        or ""
                    ),

                    "publish_date": (
                        item.get(
                            "publishDate",
                            ""
                        )
                        or ""
                    ),

                    "created_date": (
                        item.get(
                            "createdDate",
                            ""
                        )
                        or ""
                    ),

                    "status": status,

                    "url": (
                        CEJN_TENDER_URL
                        + str(tender_id)
                    )
                }

                active_tenders.append(tender)

        except requests.RequestException as error:
            logger.warning(
                f"CEJN problem na stranici "
                f"{page_number}: {error}"
            )

            logger.warning(
                "Ne odbacujem već preuzete tendere."
            )

            break

        except Exception as error:
            logger.exception(
                f"Neočekivana greška: {error}"
            )
            break

    logger.info("")
    logger.info("=" * 70)
    logger.info(
        f"AKTIVNIH TENDERA MEĐU NAJNOVIJIH "
        f"{PAGE_SIZE * MAX_PAGES}: "
        f"{len(active_tenders)}"
    )
    logger.info("=" * 70)

    return active_tenders


# ============================================================
# ANALIZA JEDNOG TENDERA
# ============================================================

def analyze_tender(tender):
    title = tender.get("title", "")
    normalized_title = normalize_text(title)

    score = 0

    high_found = []
    medium_found = []
    project_found = []

    for keyword in HIGH_PRIORITY_KEYWORDS:
        if normalize_text(keyword) in normalized_title:
            score += 50
            high_found.append(keyword)

    for keyword in MEDIUM_PRIORITY_KEYWORDS:
        if normalize_text(keyword) in normalized_title:
            score += 25
            medium_found.append(keyword)

    for keyword in PROJECT_KEYWORDS:
        if normalize_text(keyword) in normalized_title:
            project_found.append(keyword)

    score = min(score, 100)

    result = dict(tender)

    result["score"] = score
    result["matched_keywords"] = (
        high_found + medium_found
    )
    result["project_keywords"] = (
        project_found
    )

    return result


# ============================================================
# FILTER
# ============================================================

def filter_tenders(tenders):
    logger.info("")
    logger.info("=" * 70)
    logger.info("FILTER - MAŠINSKE INSTALACIJE")
    logger.info("=" * 70)

    relevant = []
    construction_candidates = []

    for tender in tenders:
        analyzed = analyze_tender(tender)

        if analyzed["score"] >= 25:
            relevant.append(analyzed)

            logger.info(
                f"RELEVANTAN | "
                f"{analyzed['score']}% | "
                f"#{analyzed['id']} | "
                f"{analyzed['title']}"
            )

        elif analyzed["project_keywords"]:
            construction_candidates.append(analyzed)

            logger.info(
                f"ZA DETALJNU PROVJERU | "
                f"#{analyzed['id']} | "
                f"{analyzed['title']}"
            )

    relevant.sort(
        key=lambda x: (
            x.get("score", 0),
            x.get("publish_date", "")
        ),
        reverse=True
    )

    logger.info("")
    logger.info(
        f"Direktno relevantnih: "
        f"{len(relevant)}"
    )

    logger.info(
        f"Građevinskih kandidata: "
        f"{len(construction_candidates)}"
    )

    return relevant


# ============================================================
# FORMAT DATUMA
# ============================================================

def format_publish_date(value):
    if not value:
        return "-"

    return (
        value
        .replace("T", " ")
        [:16]
    )


# ============================================================
# EMAIL HTML
# ============================================================

def build_email_html(tenders):
    today = datetime.now().strftime(
        "%d.%m.%Y."
    )

    html = f"""
    <html>
    <body style="
        margin:0;
        padding:20px;
        background:#f3f3f3;
        font-family:Arial,sans-serif;
    ">

    <div style="
        max-width:850px;
        margin:auto;
        padding:30px;
        background:#ffffff;
        border-radius:10px;
    ">

    <h1 style="
        margin-top:0;
        font-size:26px;
    ">
        MAŠINAC — CEJN tenderi
    </h1>

    <p>
        Automatska dnevna provjera CEJN portala.
    </p>

    <p>
        <strong>Datum:</strong>
        {today}
    </p>

    <p>
        <strong>Relevantnih tendera:</strong>
        {len(tenders)}
    </p>
    """

    for tender in tenders:
        keywords = ", ".join(
            tender.get(
                "matched_keywords",
                []
            )
        )

        if not keywords:
            keywords = "-"

        publish_date = format_publish_date(
            tender.get(
                "publish_date",
                ""
            )
        )

        html += f"""
        <div style="
            margin-top:25px;
            padding:20px;
            border:1px solid #dddddd;
            border-radius:8px;
        ">

        <div style="
            color:#777777;
            font-size:13px;
        ">
            CEJN #{tender['id']}
        </div>

        <h2 style="
            font-size:20px;
            margin-bottom:15px;
        ">
            {tender['title']}
        </h2>

        <p>
            <strong>Naručilac:</strong>
            {tender['contract_authority']}
        </p>

        <p>
            <strong>Vrsta predmeta:</strong>
            {tender['contract_type']}
        </p>

        <p>
            <strong>Vrsta postupka:</strong>
            {tender['procedure_type']}
        </p>

        <p>
            <strong>Status:</strong>
            {tender['status']}
        </p>

        <p>
            <strong>Datum objave:</strong>
            {publish_date}
        </p>

        <p>
            <strong>Relevantnost:</strong>
            {tender['score']}%
        </p>

        <p>
            <strong>Pronađene riječi:</strong>
            {keywords}
        </p>

        <p>
            <a
                href="{tender['url']}"
                style="
                    display:inline-block;
                    margin-top:5px;
                    padding:12px 18px;
                    background:#222222;
                    color:#ffffff;
                    text-decoration:none;
                    border-radius:5px;
                    font-weight:bold;
                "
            >
                OTVORI TENDER NA CEJN
            </a>
        </p>

        </div>
        """

    html += """
    <p style="
        margin-top:30px;
        color:#888888;
        font-size:12px;
    ">
        CEJN Tender Monitor — Mašinac d.o.o.
    </p>

    </div>
    </body>
    </html>
    """

    return html


# ============================================================
# EMAIL
# ============================================================

def send_email(tenders):
    if not tenders:
        logger.info("")
        logger.info(
            "Nema relevantnih tendera."
        )
        logger.info(
            "Email se ne šalje."
        )
        return

    if not EMAIL_USER:
        logger.error(
            "EMAIL_USER nije podešen "
            "u GitHub Secrets."
        )
        return

    if not EMAIL_PASSWORD:
        logger.error(
            "EMAIL_PASSWORD nije podešen "
            "u GitHub Secrets."
        )
        return

    if not RECIPIENT_EMAIL:
        logger.error(
            "RECIPIENT_EMAIL nije podešen "
            "u GitHub Secrets."
        )
        return

    today = datetime.now().strftime(
        "%d.%m.%Y"
    )

    subject = (
        f"MAŠINAC | "
        f"{len(tenders)} relevantnih CEJN tendera "
        f"| {today}"
    )

    message = MIMEMultipart(
        "alternative"
    )

    message["Subject"] = subject
    message["From"] = EMAIL_USER
    message["To"] = RECIPIENT_EMAIL

    html = build_email_html(
        tenders
    )

    message.attach(
        MIMEText(
            html,
            "html",
            "utf-8"
        )
    )

    try:
        logger.info("")
        logger.info(
            f"Šaljem email na "
            f"{RECIPIENT_EMAIL}..."
        )

        with smtplib.SMTP(
            SMTP_SERVER,
            SMTP_PORT,
            timeout=30
        ) as server:

            server.ehlo()
            server.starttls()
            server.ehlo()

            server.login(
                EMAIL_USER,
                EMAIL_PASSWORD
            )

            server.sendmail(
                EMAIL_USER,
                [RECIPIENT_EMAIL],
                message.as_string()
            )

        logger.info(
            "EMAIL USPJEŠNO POSLAT."
        )

    except Exception as error:
        logger.exception(
            f"Greška pri slanju emaila: "
            f"{error}"
        )


# ============================================================
# MAIN
# ============================================================

def main():
    logger.info("")
    logger.info(
        "============================================="
    )

    logger.info(
        f"MAŠINAC - CEJN TENDER MONITOR {VERSION}"
    )

    logger.info(
        "============================================="
    )

    # 1. CEJN
    tenders = fetch_tenders_from_cejn()

    if not tenders:
        logger.warning(
            "Nema aktivnih tendera za analizu."
        )
        return

    # 2. FILTER
    relevant = filter_tenders(
        tenders
    )

    # 3. LOG
    logger.info("")
    logger.info("=" * 70)
    logger.info("KONAČNI REZULTATI")
    logger.info("=" * 70)

    if relevant:
        for tender in relevant:
            logger.info(
                f"{tender['score']}% | "
                f"#{tender['id']} | "
                f"{tender['title']}"
            )

            logger.info(
                tender["url"]
            )

    else:
        logger.info(
            "Nema direktno relevantnih "
            "tendera među provjerenim."
        )

    # 4. EMAIL
    send_email(
        relevant
    )

    logger.info("")
    logger.info(
        "PROVJERA ZAVRŠENA."
    )


if __name__ == "__main__":
    main()
