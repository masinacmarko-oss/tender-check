import os
import re
import smtplib
import logging
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict

from playwright.sync_api import sync_playwright


# ============================================================
# PODEŠAVANJA
# ============================================================

CEJN_BASE_URL = "https://cejn.gov.me"
CEJN_TENDERS_URL = f"{CEJN_BASE_URL}/tenders"

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
# KLJUČNE RIJEČI ZA MAŠINAC
# ============================================================

HIGH_PRIORITY_KEYWORDS = [
    "mašinske instalacije",
    "masinske instalacije",

    "termotehničke instalacije",
    "termotehnicke instalacije",
    "termotehnika",

    "ventilacija",
    "ventilacioni",
    "ventilacione",

    "klimatizacija",
    "klimatizacioni",
    "klima uređaj",
    "klima uredjaj",
    "klima uređaji",
    "klima uredjaji",

    "grijanje",
    "grejanje",

    "hlađenje",
    "hladjenje",

    "sprinkler",
    "sprinklerski",

    "odimljavanje",
    "odimljavanja",

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

    "rashladni sistem",
    "rashladni sistemi",
    "rashladna oprema",

    "hvac",

    "rekuperacija",
    "rekuperator",

    "klimakomora",
    "klima komora",
    "klima komore",

    "ventilator",
    "ventilatori",

    "toplovod",
    "toplovodna instalacija",

    "cjevovod grijanja",
    "cevovod grejanja",

    "hidrotehničke mašinske instalacije",

    "automatsko gašenje",
    "automatsko gasenje",
]


MEDIUM_PRIORITY_KEYWORDS = [
    "rekonstrukcija kotlarnice",
    "rekonstrukcija grijanja",
    "rekonstrukcija grejanja",
    "rekonstrukcija ventilacije",

    "sistem grijanja",
    "sistem grejanja",
    "sistem hlađenja",
    "sistem hladjenja",

    "centralno grijanje",
    "centralno grejanje",

    "radijatori",
    "podno grijanje",
    "podno grejanje",

    "cirkulaciona pumpa",
    "cirkulacione pumpe",

    "ekspanziona posuda",

    "izmjenjivač toplote",
    "izmenjivač toplote",

    "solarno grijanje",
    "solarni kolektori",

    "bojler",
    "akumulacioni bojler",
]


CONTEXT_KEYWORDS = [
    "rekonstrukcija",
    "adaptacija",
    "izgradnja",
    "dogradnja",
    "sanacija",
    "objekat",
    "hotel",
    "škola",
    "skola",
    "vrtić",
    "vrtic",
    "bolnica",
    "dom zdravlja",
    "sportska hala",
    "garaža",
    "garaza",
    "poslovni objekat",
    "stambeni objekat",
]


# ============================================================
# POMOĆNE FUNKCIJE
# ============================================================

def normalize_text(text: str) -> str:
    if not text:
        return ""

    text = text.lower()
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def get_tender_id(url: str) -> str:
    if not url:
        return ""

    match = re.search(
        r"/tenders/view-tender/(\d+)",
        url
    )

    if match:
        return match.group(1)

    return ""


# ============================================================
# PREUZIMANJE CEJN TENDERA
# ============================================================

def fetch_tenders_from_cejn() -> List[Dict]:

    logger.info("=" * 70)
    logger.info("CEJN - PREUZIMANJE TENDERA")
    logger.info("=" * 70)

    tenders = []
    seen_ids = set()

    try:

        with sync_playwright() as p:

            logger.info("Pokrećem Chromium...")

            browser = p.chromium.launch(
                headless=True
            )

            context = browser.new_context(
                viewport={
                    "width": 1920,
                    "height": 1080
                },
                user_agent=(
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/130.0 Safari/537.36"
                )
            )

            page = context.new_page()

            logger.info(
                f"Otvaram CEJN: {CEJN_TENDERS_URL}"
            )

            response = page.goto(
                CEJN_TENDERS_URL,
                wait_until="domcontentloaded",
                timeout=90000
            )

            if response:
                logger.info(
                    f"HTTP status: {response.status}"
                )

            logger.info(
                "Čekam učitavanje CEJN aplikacije..."
            )

            page.wait_for_timeout(8000)

            logger.info(
                f"Naslov stranice: {page.title()}"
            )

            # ------------------------------------------------
            # PRONAĐI SVE LINKOVE KA TENDERIMA
            # ------------------------------------------------

            links = page.locator(
                'a[href*="/tenders/view-tender/"]'
            )

            count = links.count()

            logger.info(
                f"Pronađeno linkova ka tenderima: {count}"
            )

            for index in range(count):

                try:

                    link = links.nth(index)

                    href = link.get_attribute("href")

                    if not href:
                        continue

                    tender_id = get_tender_id(href)

                    if not tender_id:
                        continue

                    if tender_id in seen_ids:
                        continue

                    seen_ids.add(tender_id)

                    if href.startswith("http"):
                        tender_url = href

                    elif href.startswith("/"):
                        tender_url = CEJN_BASE_URL + href

                    else:
                        tender_url = (
                            CEJN_BASE_URL + "/" + href
                        )

                    # Tekst linka
                    try:
                        link_text = (
                            link.inner_text()
                            .strip()
                        )

                    except Exception:
                        link_text = ""

                    # Širi tekst oko tendera
                    try:

                        full_text = link.evaluate(
                            """
                            element => {

                                let current = element;

                                for (
                                    let i = 0;
                                    i < 10;
                                    i++
                                ) {

                                    if (!current) {
                                        break;
                                    }

                                    const tag =
                                        current.tagName
                                        ? current.tagName
                                            .toLowerCase()
                                        : '';

                                    const className =
                                        current.className
                                        ? String(
                                            current.className
                                        ).toLowerCase()
                                        : '';

                                    if (
                                        tag === 'tr' ||
                                        tag === 'li' ||
                                        className.includes(
                                            'row'
                                        ) ||
                                        className.includes(
                                            'card'
                                        ) ||
                                        className.includes(
                                            'tender'
                                        )
                                    ) {

                                        return (
                                            current.innerText
                                            || ''
                                        );
                                    }

                                    current =
                                        current.parentElement;
                                }

                                return (
                                    element.innerText
                                    || ''
                                );
                            }
                            """
                        )

                    except Exception:

                        full_text = link_text

                    full_text = (
                        full_text.strip()
                        if full_text
                        else ""
                    )

                    title = link_text

                    if not title:

                        lines = [
                            line.strip()
                            for line
                            in full_text.splitlines()
                            if line.strip()
                        ]

                        if lines:
                            title = lines[0]

                    if not title:

                        title = (
                            f"CEJN tender "
                            f"{tender_id}"
                        )

                    tender = {
                        "id": tender_id,
                        "title": title,
                        "description": full_text,
                        "url": tender_url,
                        "source": "CEJN"
                    }

                    tenders.append(tender)

                except Exception as e:

                    logger.warning(
                        f"Greška kod tendera "
                        f"{index}: {e}"
                    )

            browser.close()

    except Exception as e:

        logger.exception(
            f"Greška pri pristupu CEJN-u: {e}"
        )

        return []

    logger.info(
        f"UKUPNO PREUZETO: "
        f"{len(tenders)} tendera"
    )

    return tenders


# ============================================================
# ANALIZA RELEVANTNOSTI
# ============================================================

def analyze_tender(
    tender: Dict
) -> Dict:

    title = tender.get(
        "title",
        ""
    )

    description = tender.get(
        "description",
        ""
    )

    text = normalize_text(
        title + " " + description
    )

    score = 0

    found_high = []
    found_medium = []
    found_context = []

    # Jake HVAC riječi
    for keyword in HIGH_PRIORITY_KEYWORDS:

        if normalize_text(keyword) in text:

            score += 30

            found_high.append(
                keyword
            )

    # Srednje riječi
    for keyword in MEDIUM_PRIORITY_KEYWORDS:

        if normalize_text(keyword) in text:

            score += 15

            found_medium.append(
                keyword
            )

    # Kontekst
    for keyword in CONTEXT_KEYWORDS:

        if normalize_text(keyword) in text:

            score += 3

            found_context.append(
                keyword
            )

    # Ograniči ocjenu na 100
    score = min(
        score,
        100
    )

    if score >= 70:
        priority = "VISOKA"

    elif score >= 40:
        priority = "SREDNJA"

    else:
        priority = "NISKA"

    return {
        **tender,

        "score": score,

        "priority": priority,

        "matched_keywords": (
            found_high
            + found_medium
        ),

        "context_keywords":
            found_context
    }


# ============================================================
# FILTER
# ============================================================

def filter_tenders(
    tenders: List[Dict]
) -> List[Dict]:

    logger.info("")
    logger.info("=" * 70)
    logger.info("ANALIZA RELEVANTNOSTI")
    logger.info("=" * 70)

    relevant = []

    for tender in tenders:

        analyzed = analyze_tender(
            tender
        )

        logger.info(
            f"{analyzed['score']:>3}% | "
            f"{analyzed['title'][:80]}"
        )

        # Minimum 30 poena
        if analyzed["score"] >= 30:

            relevant.append(
                analyzed
            )

    relevant.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    logger.info("")
    logger.info(
        f"Relevantnih tendera: "
        f"{len(relevant)}"
    )

    return relevant


# ============================================================
# EMAIL
# ============================================================

def build_email_html(
    tenders: List[Dict]
) -> str:

    today = datetime.now().strftime(
        "%d.%m.%Y."
    )

    html = f"""
    <html>
    <body
        style="
            font-family:
            Arial,
            sans-serif;
            background:#f5f5f5;
            padding:20px;
        "
    >

    <div
        style="
            max-width:800px;
            margin:auto;
            background:white;
            padding:25px;
        "
    >

    <h2>
        CEJN tenderi za
        mašinske instalacije
    </h2>

    <p>
        Datum provjere:
        <strong>
            {today}
        </strong>
    </p>

    <p>
        Pronađeno relevantnih tendera:
        <strong>
            {len(tenders)}
        </strong>
    </p>
    """

    for tender in tenders:

        keywords = ", ".join(
            tender.get(
                "matched_keywords",
                []
            )[:10]
        )

        description = tender.get(
            "description",
            ""
        )

        if len(description) > 500:

            description = (
                description[:500]
                + "..."
            )

        html += f"""

        <hr>

        <h3>
            {tender["title"]}
        </h3>

        <p>
            <strong>
                Relevantnost:
            </strong>

            {tender["score"]}%

            —
            {tender["priority"]}
        </p>

        <p>
            <strong>
                Pronađene riječi:
            </strong>

            {keywords}
        </p>

        <p>
            {description}
        </p>

        <p>
            <a
                href="{tender["url"]}"
                style="
                    display:inline-block;
                    padding:10px 16px;
                    background:#222;
                    color:white;
                    text-decoration:none;
                "
            >
                OTVORI TENDER NA CEJN
            </a>
        </p>

        """

    html += """

    <hr>

    <p
        style="
            font-size:12px;
            color:#777;
        "
    >

        Automatska CEJN provjera
        — Mašinac d.o.o.

    </p>

    </div>

    </body>
    </html>
    """

    return html


def send_email(
    tenders: List[Dict]
):

    if not tenders:

        logger.info(
            "Nema relevantnih tendera. "
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
        f"CEJN | "
        f"{len(tenders)} relevantnih tendera "
        f"| {today}"
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

        logger.info(
            "Šaljem email..."
        )

        server = smtplib.SMTP(
            SMTP_SERVER,
            SMTP_PORT
        )

        server.starttls()

        server.login(
            EMAIL_FROM,
            EMAIL_PASSWORD
        )

        server.sendmail(
            EMAIL_FROM,
            EMAIL_TO,
            message.as_string()
        )

        server.quit()

        logger.info(
            "EMAIL USPJEŠNO POSLAT."
        )

    except Exception as e:

        logger.exception(
            f"Greška pri slanju emaila: {e}"
        )


# ============================================================
# GLAVNI PROGRAM
# ============================================================

def main():

    logger.info("")
    logger.info(
        "============================================="
    )

    logger.info(
        "MAŠINAC - CEJN TENDER CHECK"
    )

    logger.info(
        "============================================="
    )

    # 1. Preuzmi tendere
    tenders = fetch_tenders_from_cejn()

    logger.info(
        f"Preuzeto ukupno: "
        f"{len(tenders)} tendera"
    )

    if not tenders:

        logger.warning(
            "Nijedan tender nije preuzet."
        )

        logger.warning(
            "Provjeri CEJN scraping "
            "u GitHub Actions logu."
        )

        return

    # 2. Analiziraj
    relevant_tenders = filter_tenders(
        tenders
    )

    # 3. Ispiši najbolje
    if relevant_tenders:

        logger.info("")
        logger.info(
            "NAJBOLJI REZULTATI:"
        )

        for tender in relevant_tenders[:20]:

            logger.info(
                f"{tender['score']}% | "
                f"{tender['title']} | "
                f"{tender['url']}"
            )

    # 4. Pošalji email
    send_email(
        relevant_tenders
    )

    logger.info("")
    logger.info(
        "Provjera završena."
    )


if __name__ == "__main__":
    main()
