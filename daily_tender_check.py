import logging
from typing import List, Dict

from playwright.sync_api import sync_playwright


# ============================================================
# LOGOVANJE
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


# ============================================================
# CEJN
# ============================================================

CEJN_URL = "https://cejn.gov.me/tenders"


# ============================================================
# PREUZIMANJE / DIJAGNOSTIKA CEJN-a
# ============================================================

def fetch_tenders_from_cejn() -> List[Dict]:
    """
    Dijagnostička funkcija.

    Otvara CEJN portal i prati sve XHR/fetch zahtjeve
    kako bismo pronašli interni endpoint kojim CEJN
    učitava tendere.

    Za sada namjerno vraća praznu listu.
    """

    logger.info("=" * 70)
    logger.info("CEJN - TRAŽENJE INTERNOG API ENDPOINTA")
    logger.info("=" * 70)

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

            # ------------------------------------------------
            # LOGOVANJE REQUEST-a
            # ------------------------------------------------

            def log_request(request):
                try:
                    resource_type = request.resource_type

                    if resource_type in ["xhr", "fetch"]:
                        logger.info(
                            f"➡️ {resource_type.upper()} REQUEST: "
                            f"{request.method} {request.url}"
                        )

                        # Ako je POST, ispiši payload
                        if request.method.upper() == "POST":
                            try:
                                post_data = request.post_data

                                if post_data:
                                    preview = post_data

                                    if len(preview) > 2000:
                                        preview = (
                                            preview[:2000]
                                            + "..."
                                        )

                                    logger.info(
                                        f"📤 POST DATA: {preview}"
                                    )

                            except Exception as e:
                                logger.info(
                                    f"Ne mogu pročitati POST data: {e}"
                                )

                except Exception as e:
                    logger.warning(
                        f"Greška u request loggeru: {e}"
                    )

            # ------------------------------------------------
            # LOGOVANJE RESPONSE-a
            # ------------------------------------------------

            def log_response(response):
                try:
                    request = response.request

                    resource_type = request.resource_type

                    if resource_type not in ["xhr", "fetch"]:
                        return

                    logger.info(
                        f"⬅️ RESPONSE {response.status}: "
                        f"{response.url}"
                    )

                    content_type = (
                        response.headers
                        .get("content-type", "")
                        .lower()
                    )

                    logger.info(
                        f"📄 CONTENT-TYPE: {content_type}"
                    )

                    # Ako je JSON
                    if "json" in content_type:
                        try:
                            data = response.json()

                            preview = str(data)

                            if len(preview) > 3000:
                                preview = (
                                    preview[:3000]
                                    + "..."
                                )

                            logger.info(
                                f"📦 JSON PREVIEW: {preview}"
                            )

                        except Exception as json_error:
                            logger.info(
                                f"JSON nije moguće pročitati: "
                                f"{json_error}"
                            )

                    # Ako nije označeno kao JSON,
                    # pokušaj ipak pročitati tekst
                    else:
                        try:
                            text = response.text()

                            if text:
                                preview = text.strip()

                                if len(preview) > 1500:
                                    preview = (
                                        preview[:1500]
                                        + "..."
                                    )

                                # Ne štampaj prazne/ogromne HTML odgovore
                                if preview:
                                    logger.info(
                                        f"📃 RESPONSE PREVIEW: "
                                        f"{preview}"
                                    )

                        except Exception:
                            pass

                except Exception as e:
                    logger.warning(
                        f"Greška u response loggeru: {e}"
                    )

            # ------------------------------------------------
            # UKLJUČI LISTENERE
            # ------------------------------------------------

            page.on(
                "request",
                log_request
            )

            page.on(
                "response",
                log_response
            )

            # ------------------------------------------------
            # OTVORI CEJN
            # ------------------------------------------------

            logger.info(
                f"Otvaram CEJN: {CEJN_URL}"
            )

            response = page.goto(
                CEJN_URL,
                wait_until="domcontentloaded",
                timeout=90000
            )

            if response:
                logger.info(
                    f"Glavni HTTP status: "
                    f"{response.status}"
                )

            logger.info(
                "Čekam 20 sekundi da CEJN "
                "učita sve podatke..."
            )

            page.wait_for_timeout(
                20000
            )

            # ------------------------------------------------
            # DODATNA DIJAGNOSTIKA
            # ------------------------------------------------

            logger.info(
                f"Naslov stranice: "
                f"{page.title()}"
            )

            logger.info(
                f"Finalni URL: "
                f"{page.url}"
            )

            try:
                body_text = page.locator(
                    "body"
                ).inner_text()

                logger.info(
                    f"Dužina BODY teksta: "
                    f"{len(body_text)}"
                )

                preview = body_text.strip()

                if len(preview) > 3000:
                    preview = (
                        preview[:3000]
                        + "..."
                    )

                logger.info(
                    f"BODY PREVIEW: {preview}"
                )

            except Exception as e:
                logger.warning(
                    f"Ne mogu pročitati BODY: {e}"
                )

            # ------------------------------------------------
            # LINKOVI
            # ------------------------------------------------

            try:
                all_links = page.locator("a")

                total_links = all_links.count()

                logger.info(
                    f"Ukupan broj <a> linkova: "
                    f"{total_links}"
                )

                for i in range(
                    min(total_links, 100)
                ):
                    try:
                        link = all_links.nth(i)

                        href = link.get_attribute(
                            "href"
                        )

                        text = ""

                        try:
                            text = (
                                link.inner_text()
                                .strip()
                            )
                        except Exception:
                            pass

                        if href:
                            logger.info(
                                f"🔗 LINK {i}: "
                                f"{text[:80]} | {href}"
                            )

                    except Exception:
                        pass

            except Exception as e:
                logger.warning(
                    f"Ne mogu čitati linkove: {e}"
                )

            logger.info(
                "CEJN network analiza završena."
            )

            browser.close()

    except Exception as e:
        logger.exception(
            f"Greška prilikom CEJN "
            f"network analize: {e}"
        )

    # Za sada namjerno vraćamo prazno.
    # Cilj ovog testa je pronaći pravi CEJN endpoint.
    return []


# ============================================================
# GLAVNI PROGRAM
# ============================================================

def main():

    logger.info("")
    logger.info(
        "============================================="
    )

    logger.info(
        "MAŠINAC - CEJN DIJAGNOSTIKA"
    )

    logger.info(
        "============================================="
    )

    tenders = fetch_tenders_from_cejn()

    logger.info(
        f"Preuzeto ukupno: "
        f"{len(tenders)} tendera"
    )

    logger.info(
        "DIJAGNOSTIKA ZAVRŠENA."
    )

    logger.info(
        "Pošalji XHR/FETCH/JSON dio "
        "GitHub Actions loga."
    )


if __name__ == "__main__":
    main()
