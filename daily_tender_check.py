import requests
import smtplib
import json
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import List, Dict
import os

# Konfiguracija
class Config:
    # Email podesavanja
    SMTP_SERVER = 'smtp.gmail.com'
    SMTP_PORT = 587
    EMAIL_USER = os.environ.get('EMAIL_USER', 'masinacmarko@gmail.com')
    EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', '')
    RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', 'masinacmarko@gmail.com')
    
    # Ključne reči za filtriranje - prilagođeno za Crnu Goru
    KEYWORDS = [
        # Mašinske instalacije
        'mašinske instalacije',
        'mašinska instalacija',
        'machine installation',
        'mechanical installation',
        'masinske instalacije',
        'masinska instalacija',
        
        # HVAC sistemi
        'hvac',
        'klimatizacija',
        'klima instalacije',
        'klima uređaji',
        'klima uredjaji',
        'klima sistemi',
        'klima komore',
        'ventilacija',
        'ventilacioni sistem',
        'ventilacioni kanali',
        'ventilatorske jedinice',
        'klima komora',
        
        # Grijanje
        'grijanje',
        'grejanje',
        'centralno grijanje',
        'centralno grejanje',
        'toplotne pumpe',
        'toplotna pumpa',
        'kotlarnica',
        'kotlovi',
        'kotao',
        'radijatori',
        'podno grijanje',
        'podno grejanje',
        'toplovod',
        'toplotna stanica',
        'toplotne podstanice',
        'gasni kotlovi',
        'električno grijanje',
        'elektricno grijanje',
        
        # Vodovod i kanalizacija
        'vodovod',
        'kanalizacija',
        'cjevovod',
        'cevovod',
        'cjevovodi',
        'cevovodi',
        'sanitarne instalacije',
        'sanitarije',
        'vodovodne instalacije',
        'kanalizacione instalacije',
        
        # Oprema
        'pumpe',
        'pumpa',
        'kompresori',
        'kompresor',
        'izmjenjivači toplote',
        'izmjenjivaci toplote',
        'rashladni sistemi',
        'rashladne mašine',
        'rashladni uređaji',
        'rashladni uredjaji',
        'klima komore',
        'ventilatori',
        'filteri za ventilaciju',
        'rekuperatori',
        'rekuperacija',
        
        # Industrijske instalacije
        'industrijske instalacije',
        'procesna oprema',
        'termotehnika',
        'termotehničke instalacije',
        'termotehnicke instalacije',
        'gasne instalacije',
        'gasni sistemi',
        'industrijska ventilacija',
        
        # Usluge
        'montaža',
        'montaza',
        'održavanje',
        'odrzavanje',
        'servisiranje',
        'ugradnja',
        'instalacija',
        'demontaža',
        'demontaza',
        
        # Dodatni pojmovi
        'energetska efikasnost',
        'energetska obnova',
        'termoizolacija',
        'toplotna izolacija',
        'vazdušno grijanje',
        'vazdusno grijanje',
        'konvektori',
        'toplotni agregati',
        'rashladni agregati',
        'čiler',
        'chiller',
        'vršna rashladna',
        'klima centrala',
        'fan coil',
        'ventilokonvektor',
    ]

def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('daily_tender.log'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

def load_processed_tenders() -> set:
    """Učitava listu već poslatih tendera"""
    try:
        with open('processed_tenders.json', 'r') as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_processed_tenders(processed_tenders: set):
    """Čuva listu poslatih tendera"""
    with open('processed_tenders.json', 'w') as f:
        json.dump(list(processed_tenders), f)

def fetch_tenders_from_cejn() -> List[Dict]:
    """Preuzima tendere sa CEJN portala Crne Gore"""
    try:
        # CEJN API endpoint - pokušavamo različite opcije
        urls = [
            'https://cejn.gov.me/api/tenders',
            'https://cejn.gov.me/api/tenderi',
            'https://cejn.gov.me/tenders/json',
            'https://cejn.gov.me/api/public-tenders',
        ]
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'sr,en;q=0.9',
        }
        
        for url in urls:
            try:
                response = requests.get(url, headers=headers, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        # Pokušaj različite strukture
                        for key in ['tenders', 'tenderi', 'data', 'items', 'results']:
                            if key in data and isinstance(data[key], list):
                                return data[key]
                logger.info(f"URL ne radi: {url} - Status: {response.status_code}")
            except:
                continue
        
        # Ako API ne radi, pokušaj web scraping
        logger.warning("API ne radi, pokušavam web scraping...")
        return scrape_cejn_website()
            
    except Exception as e:
        logger.error(f"Greška pri preuzimanju tendera: {e}")
        return []

def scrape_cejn_website() -> List[Dict]:
    """Web scraping CEJN sajta ako API ne radi"""
    try:
        url = 'https://cejn.gov.me/tenderi'
        response = requests.get(url, timeout=30, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
        })
        
        # Ovdje bi trebalo parsirati HTML sajt
        # Ovo je placeholder - treba prilagoditi stvarnoj strukturi sajta
        logger.warning("Web scraping još nije implementiran za CEJN")
        return []
        
    except Exception as e:
        logger.error(f"Greška pri scraping-u: {e}")
        return []

def filter_tenders(tenders: List[Dict], processed_tenders: set) -> List[Dict]:
    """Filtrira tendere prema ključnim rečima"""
    filtered = []
    
    for tender in tenders:
        # Spoji sve tekstualne podatke tendera
        tender_text = ' '.join([
            str(tender.get('name', '')),
            str(tender.get('title', '')),
            str(tender.get('naslov', '')),
            str(tender.get('description', '')),
            str(tender.get('opis', '')),
            str(tender.get('category', '')),
            str(tender.get('kategorija', '')),
            str(tender.get('cpv_code', '')),
            str(tender.get('type', '')),
            str(tender.get('tip', '')),
        ]).lower()
        
        # Proveri da li tender sadrži ključne reči
        if any(keyword.lower() in tender_text for keyword in Config.KEYWORDS):
            tender_id = tender.get('id') or tender.get('url') or tender.get('name')
            
            # Proveri da li je tender već poslat
            if tender_id and tender_id not in processed_tenders:
                filtered.append(tender)
                processed_tenders.add(tender_id)
                
    return filtered

def send_email(tenders: List[Dict]):
    """Šalje email sa novim tenderima"""
    if not tenders:
        logger.info("Nema novih tendera za slanje")
        return False
        
    subject = f"🔔 {len(tenders)} novih tendera za mašinske instalacije - CEJN {datetime.now().strftime('%d.%m.%Y')}"
    
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
        <h2 style="color: #2c3e50;">Pronađeni novi tenderi za mašinske instalacije</h2>
        <p>Portal: CEJN - Crna Gora</p>
        <p>Datum provere: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
        <hr style="border: 1px solid #eee;">
    """
    
    for i, tender in enumerate(tenders, 1):
        deadline = tender.get('deadline', tender.get('end_date', tender.get('rok', 'N/A')))
        url = tender.get('url', tender.get('link', 'https://cejn.gov.me'))
        
        body += f"""
        <div style="margin-bottom: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9;">
            <h3 style="color: #34495e; margin-top: 0;">{i}. {tender.get('name', tender.get('title', tender.get('naslov', 'Nepoznat tender')))}</h3>
            <p><strong>📋 ID:</strong> {tender.get('id', 'N/A')}</p>
            <p><strong>📝 Opis:</strong> {str(tender.get('description', tender.get('opis', 'Nema opisa')))[:300]}...</p>
            <p><strong>⏰ Rok za prijavu:</strong> {deadline}</p>
            <p><strong>💰 Vrijednost:</strong> {tender.get('value', tender.get('vrijednost', 'Nije navedena'))}</p>
            <p><strong>🔗 Link:</strong> <a href="{url}" style="color: #2980b9;">Otvori tender na CEJN</a></p>
        </div>
        """
    
    body += """
        <hr style="border: 1px solid #eee;">
        <p style="color: #7f8c8d; font-size: 12px;">
            Ovo je automatska poruka. Za više informacija posjetite CEJN portal: cejn.gov.me
        </p>
    </body>
    </html>
    """
    
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = Config.EMAIL_USER
    msg['To'] = Config.RECIPIENT_EMAIL
    
    msg.attach(MIMEText(body, 'html'))
    
    try:
        with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.EMAIL_USER, Config.EMAIL_PASSWORD)
            server.send_message(msg)
            
        logger.info(f"✅ Email poslat sa {len(tenders)} novih tendera")
        return True
        
    except Exception as e:
        logger.error(f"❌ Greška pri slanju emaila: {e}")
        return False

def main():
    """Glavna funkcija - pokreće se jednom dnevno"""
    logger.info("=" * 50)
    logger.info("🚀 Počinjem dnevnu proveru tendera sa CEJN-a...")
    
    # Učitaj već poslate tendere
    processed_tenders = load_processed_tenders()
    
    # Preuzmi tendere sa CEJN portala
    logger.info("📥 Preuzimam tendere sa CEJN portala...")
    tenders = fetch_tenders_from_cejn()
    logger.info(f"📊 Preuzeto {len(tenders)} tendera")
    
    # Filtriraj tendere
    logger.info("🔍 Filtriram tendere prema ključnim rečima...")
    filtered_tenders = filter_tenders(tenders, processed_tenders)
    logger.info(f"✨ Pronađeno {len(filtered_tenders)} relevantnih novih tendera")
    
    # Pošalji email ako ima novih tendera
    if filtered_tenders:
        send_email(filtered_tenders)
    else:
        logger.info("📭 Nema novih tendera za slanje")
    
    # Sačuvaj listu poslatih tendera
    save_processed_tenders(processed_tenders)
    
    logger.info("✅ Dnevna provera završena")
    logger.info("=" * 50)

# Test funkcija za email
def test_email():
    test_tender = [{
        'name': 'TEST TENDER - Mašinske instalacije, grijanje i klime CG',
        'id': 'TEST-001',
        'description': 'Ovo je test poruka da potvrdimo da email radi za CEJN tendere. Uključuje mašinske instalacije, grijanje, ventilaciju i klimatizaciju.',
        'deadline': '31.12.2026',
        'value': 'Test',
        'url': 'https://cejn.gov.me'
    }]
    send_email(test_tender)
    logger.info("Test email poslat!")

if __name__ == "__main__":
    # Za testiranje emaila - otkomentariši sljedeću liniju:
    # test_email()
    
    # Za normalan rad:
    main()
