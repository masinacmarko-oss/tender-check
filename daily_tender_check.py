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

CEJN_BASE_URL = "https://cejn.gov.me"
CEJN_API_URL = "https://cejn.gov.me/api/cadocuments/GetTenders"
CEJN_TENDER_URL = "https://cejn.gov.me/tenders/view-tender/"


# ============================================================
# KOLIKO TENDERA PROVJERAVAMO
# ============================================================

PAGE_SIZE = 100
MAX_PAGES = 5

# Ukupno: maksimalno 500 najnovijih postupaka


# ============================================================
# EMAIL
# ============================================================

EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "")
EMAIL_TO = os.getenv("EMAIL_TO", EMAIL_FROM)

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
# KLJUČNE RIJEČI
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

    text = text.lower()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# CEJN API
# ============================================================

def fetch_tenders_from_cejn():

    logger.info("")
    logger.info("=" * 70)
    logger.info("CEJN - PREUZIMANJE NAJNOVIJIH TENDERA")
    logger.info("=" * 70)

    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/130.0 Safari/537.36"
        ),

        "Accept":
            "application/json, text/plain, */*",

        "Content-Type":
            "application/json",

        "Origin":
            CEJN_BASE_URL,

        "Referer":
            CEJN_BASE_URL + "/tenders"
    })

    all_tenders = []

    seen_ids = set()

    for page_number in range(MAX_PAGES):

        skip = page_number * PAGE_SIZE

        logger.info(
            f"Preuzimam stranicu "
            f"{page_number + 1}/{MAX_PAGES}..."
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
                f"HTTP status: "
                f"{response.status_code}"
            )

            response.raise_for_status()

            data = response.json()

            items = data.get(
                "value",
                []
            )

            if not isinstance(items, list):

                logger.warning(
                    "CEJN nije vratio očekivanu listu."
                )

                break

            logger.info(
                f"Primljeno: "
                f"{len(items)} tendera"
            )

            if not items:
                break

            for item in items:

                tender_id = item.get("id")

                if not tender_id:
                    continue

                if tender_id in seen_ids:
                    continue

                seen_ids.add(
                    tender_id
                )

                status = (
                    item.get(
                        "lifecycleCaption",
                        ""
                    )
                    or ""
                )

                # --------------------------------------------
                # SAMO POSTUPCI KOJI SU U TOKU
                # --------------------------------------------

                if normalize_text(status) != "u toku":
                    continue

                tender = {
                    "id":
                        tender_id,

                    "title":
                        item.get(
                            "title",
                            ""
                        ),

                    "contract_authority":
                        item.get(
                            "contractAuthority",
                            ""
                        ),

                    "contract_type":
                        item.get(
                            "typeOfContractCaption",
                            ""
                        ),

                    "procedure_type":
                        item.get(
                            "typeOfProcedureCaption",
                            ""
                        ),

                    "publish_date":
                        item.get(
                            "publishDate",
                            ""
                        ),

                    "status":
                        status,

                    "url":
                        CEJN_TENDER_URL
                        + str(tender_id)
                }

                all_tenders.append(
                    tender
                )

        except requests.RequestException as e:

            # BITNO:
            # ne odbacujemo već preuzete tendere

            logger.warning(
                f"Problem sa CEJN stranicom "
                f"{page_number + 1}: {e}"
            )

            logger.warning(
                "Nastavljam sa već "
                "preuzetim tenderima."
            )

            break

        except Exception as e:

            logger.warning(
                f"Neočekivana greška: {e}"
            )

            break

    logger.info("")
    logger.info(
        f"UKUPNO AKTIVNIH TENDERA "
        f"MEĐU NAJNOVIJIH 500: "
        f"{len(all_tenders)}"
    )

    return all_tenders


# ============================================================
# ANALIZA TENDERA
# ============================================================

def analyze_tender(tender):

    title = tender.get(
        "title",
        ""
    )

    text = normalize_text(
        title
    )

    score = 0

    high_found = []
    medium_found = []
    project_found = []

    for keyword in HIGH_PRIORITY_KEYWORDS:

        if normalize_text(keyword) in text:

            score += 50

            high_found.append(
                keyword
            )

    for keyword in MEDIUM_PRIORITY_KEYWORDS:

        if normalize_text(keyword) in text:

            score += 25

            medium_found.append(
                keyword
            )

    for keyword in PROJECT_KEYWORDS:

        if normalize_text(keyword) in text:

            score += 5

            project_found.append(
                keyword
            )

    score = min(
        score,
        100
    )

    tender["score"] = score

    tender["matched_keywords"] = (
        high_found
        + medium_found
    )

    tender["project_keywords"] = (
        project_found
    )

    return tender


# ============================================================
# FILTER
# ============================================================

def filter_tenders(tenders):

    logger.info("")
    logger.info("=" * 70)
    logger.info("ANALIZA MAŠINSKIH INSTALACIJA")
    logger.info("=" * 70)

    relevant = []

    project_candidates = []

    for tender in tenders:

        analyzed = analyze_tender(
            tender
        )

        # Direktno mašinski tender

        if analyzed["score"] >= 25:

            relevant.append(
                analyzed
            )

            logger.info(
                f"✅ RELEVANTAN | "
                f"{analyzed['score']}% | "
                f"{analyzed['id']} | "
                f"{analyzed['title']}"
            )

        # Građevinski tender koji kasnije
        # treba detaljno analizirati

        elif analyzed["project_keywords"]:

            project_candidates.append(
                analyzed
            )

            logger.info(
                f"🔍 ZA DETALJNU PROVJERU | "
                f"{analyzed['id']} | "
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
        f"{len(project_candidates)}"
    )

    return relevant


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
        font-family:Arial,sans-serif;
        background:#f4f4f4;
        padding:20px;
    ">

    <div style="
        max-width:850px;
        margin:auto;
        background:white;
        padding:30px;
    ">

    <h2>
        MAŠINAC — CEJN Tender Monitor
    </h2>

    <p>
        Datum provjere:
        <strong>{today}</strong>
    </p>

    <p>
        Pronađeno:
        <strong>{len(tenders)}</strong>
        relevantnih tendera.
    </p>
    """

    for tender in tenders:

        keywords = ", ".join(
            tender.get(
                "matched_keywords",
                []
            )
        )

        publish_date = (
            tender.get(
                "publish_date",
                ""
            )
            .replace(
                "T",
                " "
            )
            [:16]
        )

        html += f"""

        <div style="
            margin-top:25px;
            padding:20px;
            border:1px solid #dddddd;
            border-radius:8px;
        ">

            <div style="
                color:#777;
                font-size:13px;
            ">
                CEJN #{tender['id']}
            </div>

            <h3>
                {tender['title']}
            </h3>

            <p>
                <strong>Naručilac:</strong>
                {tender['contract_authority']}
            </p>

            <p>
                <strong>Vrsta:</strong>
                {tender['contract_type']}
            </p>

            <p>
                <strong>Postupak:</strong>
                {tender['procedure_type']}
            </p>

            <p>
                <strong>Status:</strong>
                {tender['status']}
            </p>

            <p>
                <strong>Objavljeno:</strong>
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
                        background:#222;
                        color:#fff;
                        padding:12px 18px;
                        text-decoration:none;
                        border-radius:5px;
                        display:inline-block;
                    "
                >
                    OTVORI TENDER
                </a>
            </p>

        </div>
        """

    html += """

    <p style="
        margin-top:30px;
        color:#777;
        font-size:12px;
    ">
        Automatski CEJN Tender Monitor
        — Mašinac d.o.o.
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

        logger.info(
            "Nema relevantnih tendera."
        )

        logger.info(
            "Email se ne šalje."
        )

        return

    if not EMAIL_FROM:

        logger.error(
            "EMAIL_FROM nije podešen."
        )

        return

    if not EMAIL_PASSWORD:

        logger.error(
            "EMAIL_PASSWORD nije podešen."
        )

        return

    if not EMAIL_TO:

        logger.error(
            "EMAIL_TO nije podešen."
        )

        return

    today = datetime.now().strftime(
        "%d.%m.%Y"
    )

    subject = (
        f"MAŠINAC | "
        f"{len(tenders)} CEJN tendera | "
        f"{today}"
    )

    message = MIMEMultipart(
        "alternative"
    )

    message["Subject"] = subject
    message["From"] = EMAIL_FROM
    message["To"] = EMAIL_TO

    message.attach(
        MIMEText(
            build_email_html(
                tenders
            ),
            "html",
            "utf-8"
        )
    )

    try:

        logger.info("")
        logger.info(
            "Šaljem email..."
        )

        with smtplib.SMTP(
            SMTP_SERVER,
            SMTP_PORT
        ) as server:

            server.starttls()

            server.login(
                EMAIL_FROM,
                EMAIL_PASSWORD
            )

            server.sendmail(
                EMAIL_FROM,
                [EMAIL_TO],
                message.as_string()
            )

        logger.info(
            "✅ EMAIL USPJEŠNO POSLAT."
        )

    except Exception as e:

        logger.exception(
            f"Greška kod slanja emaila: {e}"
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
        "MAŠINAC - CEJN TENDER MONITOR V2"
    )

    logger.info(
        "============================================="
    )

    tenders = fetch_tenders_from_cejn()

    if not tenders:

        logger.warning(
            "Nema aktivnih tendera za analizu."
        )

        return

    relevant = filter_tenders(
        tenders
    )

    logger.info("")
    logger.info("=" * 70)
    logger.info("KONAČNI REZULTATI")
    logger.info("=" * 70)

    if relevant:

        for tender in relevant:

            logger.info(
                f"{tender['score']}% | "
                f"{tender['id']} | "
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

    send_email(
        relevant
    )

    logger.info("")
    logger.info(
        "✅ PROVJERA ZAVRŠENA."
    )


if __name__ == "__main__":
    main()
