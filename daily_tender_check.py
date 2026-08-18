import os
import re
import json
import smtplib
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict

import requests


# ============================================================
# MAŠINAC D.O.O. - CEJN TENDER MONITOR
# ============================================================

CEJN_BASE_URL = "https://cejn.gov.me"

CEJN_API_URL = (
    "https://cejn.gov.me/api/cadocuments/GetTenders"
)

CEJN_TENDER_URL = (
    "https://cejn.gov.me/tenders/view-tender/"
)


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

# ------------------------------------------------------------
# VEOMA JAKE RIJEČI
# Ako se pojavi jedna od njih, tender je vrlo vjerovatno
# interesantan firmi Mašinac.
# ------------------------------------------------------------

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
    "sprinkler sistem",

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

    "sistem grijanja",
    "sistem grejanja",

    "sistem hlađenja",
    "sistem hladjenja",

    "centralno grijanje",
    "centralno grejanje",

    "podno grijanje",
    "podno grejanje",

    "toplovod",
    "toplovodna instalacija",

    "automatsko gašenje požara",
    "automatsko gasenje pozara",

    "gašenje požara vodom",
    "gasenje pozara vodom",
]


# ------------------------------------------------------------
# DODATNE RIJEČI
# ------------------------------------------------------------

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

    "pumpna stanica",
]


# ------------------------------------------------------------
# RIJEČI KOJE SAME NISU DOVOLJNE,
# ALI MOGU UKAZATI NA VELIKI PROJEKAT
# ------------------------------------------------------------

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
    "klinicki centar",
]


# ============================================================
# NORMALIZACIJA TEKSTA
# ============================================================

def normalize_text(text: str) -> str:

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

def fetch_tenders_from_cejn() -> List[Dict]:
    """
    Direktno preuzima objavljene tendere sa CEJN API-ja.

    Koristimo status 64 = Published.

    Podaci se preuzimaju stranicu po stranicu.
    """

    logger.info("")
    logger.info("=" * 70)
    logger.info("CEJN - PREUZIMANJE AKTIVNIH TENDERA")
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
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": CEJN_BASE_URL,
        "Referer": CEJN_BASE_URL + "/tenders"
    })

    all_tenders = []

    page_size = 100
    skip = 0

    max_pages = 100

    try:

        for page_number in range(1, max_pages + 1):

            logger.info(
                f"Preuzimam stranicu {page_number}..."
            )

            payload = {

                "pageSize": page_size,

                # 64 = Published
                "tenderStatuses": [
                    "64"
                ],

                "skip": skip,

                "top": page_size,

                "procedureType": 0,

                "subjectType": 0,

                "justCanApply": False,

                "sort": None,

                "myTenders": False,

                "useAdditionalCaSearch": False,

                "caType": 0,

                "caStateId": 0,

                "statuses": "64"
            }

            response = session.post(
                CEJN_API_URL,
                json=payload,
                timeout=60
            )

            logger.info(
                f"HTTP status: {response.status_code}"
            )

            response.raise_for_status()

            data = response.json()

            items = data.get(
                "value",
                []
            )

            if not isinstance(items, list):

                logger.error(
                    "CEJN odgovor nema očekivanu listu 'value'."
                )

                logger.info(
                    f"Odgovor: {str(data)[:1000]}"
                )

                break

            logger.info(
                f"Na stranici pronađeno: {len(items)}"
            )

            if not items:
                break

            for item in items:

                tender_id = item.get(
                    "id"
                )

                if not tender_id:
                    continue

                tender = {

                    "id": tender_id,

                    "title": item.get(
                        "title",
                        ""
                    ),

                    "contract_authority": item.get(
                        "contractAuthority",
                        ""
                    ),

                    "contract_authority_id": item.get(
                        "contractAuthorityId"
                    ),

                    "contract_type": item.get(
                        "typeOfContractCaption",
                        ""
                    ),

                    "procedure_type": item.get(
                        "typeOfProcedureCaption",
                        ""
                    ),

                    "publish_date": item.get(
                        "publishDate",
                        ""
                    ),

                    "created_date": item.get(
                        "createdDate",
                        ""
                    ),

                    "lifecycle": item.get(
                        "lifecycle",
                        ""
                    ),

                    "status": item.get(
                        "lifecycleCaption",
                        ""
                    ),

                    "url": (
                        CEJN_TENDER_URL
                        + str(tender_id)
                    )
                }

                all_tenders.append(
                    tender
                )

            # Ako je vraćeno manje od page_size,
            # stigli smo do kraja.
            if len(items) < page_size:
                break

            skip += page_size

        logger.info("")
        logger.info(
            f"UKUPNO PREUZETO SA CEJN-a: "
            f"{len(all_tenders)}"
        )

        return all_tenders

    except requests.RequestException as e:

        logger.exception(
            f"CEJN API greška: {e}"
        )

        return []

    except Exception as e:

        logger.exception(
            f"Neočekivana CEJN greška: {e}"
        )

        return []


# ============================================================
# OCJENA RELEVANTNOSTI
# ============================================================

def analyze_tender(
    tender: Dict
) -> Dict:

    title = tender.get(
        "title",
        ""
    )

    text = normalize_text(
        title
    )

    score = 0

    found_high = []
    found_medium = []
    found_project = []

    # --------------------------------------------------------
    # JAKE RIJEČI
    # --------------------------------------------------------

    for keyword in HIGH_PRIORITY_KEYWORDS:

        normalized_keyword = normalize_text(
            keyword
        )

        if normalized_keyword in text:

            score += 50

            found_high.append(
                keyword
            )

    # --------------------------------------------------------
    # SREDNJE RIJEČI
    # --------------------------------------------------------

    for keyword in MEDIUM_PRIORITY_KEYWORDS:

        normalized_keyword = normalize_text(
            keyword
        )

        if normalized_keyword in text:

            score += 25

            found_medium.append(
                keyword
            )

    # --------------------------------------------------------
    # PROJEKTNE RIJEČI
    # --------------------------------------------------------

    for keyword in PROJECT_KEYWORDS:

        normalized_keyword = normalize_text(
            keyword
        )

        if normalized_keyword in text:

            score += 5

            found_project.append(
                keyword
            )

    score = min(
        score,
        100
    )

    matched_keywords = (
        found_high
        + found_medium
    )

    return {

        **tender,

        "score": score,

        "matched_keywords":
            matched_keywords,

        "project_keywords":
            found_project
    }


# ============================================================
# FILTER
# ============================================================

def filter_tenders(
    tenders: List[Dict]
) -> List[Dict]:

    logger.info("")
    logger.info("=" * 70)
    logger.info("FILTRIRANJE MAŠINSKIH INSTALACIJA")
    logger.info("=" * 70)

    relevant = []

    possible_projects = []

    for tender in tenders:

        analyzed = analyze_tender(
            tender
        )

        # Direktno relevantan
        if analyzed["score"] >= 25:

            relevant.append(
                analyzed
            )

            logger.info(
                f"RELEVANTAN | "
                f"{analyzed['score']}% | "
                f"{analyzed['id']} | "
                f"{analyzed['title']}"
            )

        # Širi građevinski projekat
        elif analyzed["project_keywords"]:

            possible_projects.append(
                analyzed
            )

    relevant.sort(
        key=lambda x: (
            x["score"],
            x.get(
                "publish_date",
                ""
            )
        ),
        reverse=True
    )

    logger.info("")
    logger.info(
        f"Direktno relevantnih tendera: "
        f"{len(relevant)}"
    )

    logger.info(
        f"Potencijalnih velikih projekata: "
        f"{len(possible_projects)}"
    )

    return relevant


# ============================================================
# EMAIL HTML
# ============================================================

def build_email_html(
    tenders: List[Dict]
) -> str:

    today = datetime.now().strftime(
        "%d.%m.%Y."
    )

    html = f"""
    <html>

    <body style="
        margin:0;
        padding:20px;
        background:#f4f4f4;
        font-family:Arial, sans-serif;
    ">

    <div style="
        max-width:850px;
        margin:auto;
        background:#ffffff;
        padding:30px;
        border-radius:8px;
    ">

    <h1 style="
        margin-top:0;
        font-size:26px;
    ">
        MAŠINAC — CEJN tenderi
    </h1>

    <p>
        Automatska provjera CEJN portala
        za mašinske instalacije.
    </p>

    <p>
        <strong>Datum:</strong>
        {today}
    </p>

    <p>
        <strong>Pronađeno:</strong>
        {len(tenders)}
        relevantnih tendera
    </p>
    """

    for tender in tenders:

        keywords = ", ".join(
            tender.get(
                "matched_keywords",
                []
            )
        )

        publish_date = tender.get(
            "publish_date",
            ""
        )

        if publish_date:
            publish_date = (
                publish_date
                .replace("T", " ")
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
                font-size:13px;
                color:#777777;
            ">
                CEJN #{tender['id']}
            </div>

            <h2 style="
                font-size:20px;
                margin-bottom:10px;
            ">
                {tender['title']}
            </h2>

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
                <strong>Objavljeno:</strong>
                {publish_date}
            </p>

            <p>
                <strong>Status:</strong>
                {tender['status']}
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
                        padding:12px 18px;
                        background:#222222;
                        color:#ffffff;
                        text-decoration:none;
                        border-radius:5px;
                        font-weight:bold;
                    "
                >
                    OTVORI TENDER
                </a>
            </p>

        </div>

        """

    html += """

        <p style="
            margin-top:35px;
            color:#888888;
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
# SLANJE EMAILA
# ============================================================

def send_email(
    tenders: List[Dict]
):

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
            "Nije podešen EMAIL_FROM."
        )

        return

    if not EMAIL_PASSWORD:

        logger.error(
            "Nije podešen EMAIL_PASSWORD."
        )

        return

    if not EMAIL_TO:

        logger.error(
            "Nije podešen EMAIL_TO."
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
            "EMAIL USPJEŠNO POSLAT."
        )

    except Exception as e:

        logger.exception(
            f"Greška pri slanju emaila: {e}"
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
        "MAŠINAC - CEJN TENDER MONITOR"
    )

    logger.info(
        "============================================="
    )

    # --------------------------------------------------------
    # 1. PREUZIMANJE
    # --------------------------------------------------------

    tenders = fetch_tenders_from_cejn()

    if not tenders:

        logger.warning(
            "Nema preuzetih tendera."
        )

        return

    # --------------------------------------------------------
    # 2. FILTER
    # --------------------------------------------------------

    relevant = filter_tenders(
        tenders
    )

    # --------------------------------------------------------
    # 3. REZULTATI
    # --------------------------------------------------------

    logger.info("")
    logger.info("=" * 70)
    logger.info("REZULTAT")
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
            "Danas nema direktno "
            "relevantnih tendera."
        )

    # --------------------------------------------------------
    # 4. EMAIL
    # --------------------------------------------------------

    send_email(
        relevant
    )

    logger.info("")
    logger.info(
        "Provjera završena."
    )


if __name__ == "__main__":
    main()
