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
    EMAIL_USER = os.environ.get('EMAIL_USER', 'tvoj.email@gmail.com')
    EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD', 'tvoj-app-password')
    RECIPIENT_EMAIL = os.environ.get('RECIPIENT_EMAIL', 'tvoj.email@gmail.com')
    
    # Ključne reči za filtriranje
    KEYWORDS = [
        'mašinske instalacije',
        'machine installation',
        'mechanical installation',
        'HVAC',
        'ventilacija',
        'klima instalacije',
        'grejanje',
        'vodovod',
        'kanalizacija',
        'cevovodi',
        'pumpe',
        'kompresori',
        'industrijske instalacije',
        'procesna oprema',
        'termotehnika',
        'gasne instalacije',
        'montaža',
        'održavanje',
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

def fetch_tenders_from_portal() -> List[Dict]:
    """Preuzima tendere sa Portala javnih nabavki"""
    try:
        # Portal javnih nabavki API
        url = 'https://portal.ujn.gov.rs/api/tenders'
        
        # Datum od juče
        date_from = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        response = requests.get(
            url,
            params={
                'date_from': date_from,
                'status': 'active'
            },
            timeout=30,
            headers={
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json'
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            # Prilagodi prema stvarnoj strukturi API-ja
            return data if isinstance(data, list) else data.get('tenders', [])
        else:
            logger.error(f"Greška pri preuzimanju: {response.status_code}")
            return []
            
    except Exception as e:
        logger.error(f"Greška pri preuzimanju tendera: {e}")
        return []

def filter_tenders(tenders: List[Dict], processed_tenders: set) -> List[Dict]:
    """Filtrira tendere prema ključnim rečima"""
    filtered = []
    
    for tender in tenders:
        # Spoji sve tekstualne podatke tendera
        tender_text = ' '.join([
            str(tender.get('name', '')),
            str(tender.get('title', '')),
            str(tender.get('description', '')),
            str(tender.get('category', '')),
            str(tender.get('cpv_code', '')),
            str(tender.get('type', '')),
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
        
    subject = f"🔔 {len(tenders)} novih tendera za mašinske instalacije - {datetime.now().strftime('%d.%m.%Y')}"
    
    # Kreiraj HTML sadržaj
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif;">
        <h2 style="color: #2c3e50;">Pronađeni novi tenderi za mašinske instalacije</h2>
        <p>Datum provere: {datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
        <hr style="border: 1px solid #eee;">
    """
    
    for i, tender in enumerate(tenders, 1):
        deadline = tender.get('deadline', tender.get('end_date', 'N/A'))
        url = tender.get('url', tender.get('link', '#'))
        
        body += f"""
        <div style="margin-bottom: 20px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #f9f9f9;">
            <h3 style="color: #34495e; margin-top: 0;">{i}. {tender.get('name', tender.get('title', 'Nepoznat tender'))}</h3>
            <p><strong>📋 ID:</strong> {tender.get('id', 'N/A')}</p>
            <p><strong>📝 Opis:</strong> {str(tender.get('description', 'Nema opisa'))[:300]}...</p>
            <p><strong>⏰ Rok za prijavu:</strong> {deadline}</p>
            <p><strong>💰 Vrednost:</strong> {tender.get('value', 'Nije navedena')}</p>
            <p><strong>🔗 Link:</strong> <a href="{url}" style="color: #2980b9;">Otvori tender</a></p>
        </div>
        """
    
    body += """
        <hr style="border: 1px solid #eee;">
        <p style="color: #7f8c8d; font-size: 12px;">
            Ovo je automatska poruka. Za više informacija posetite portal javnih nabavki.
        </p>
    </body>
    </html>
    """
    
    # Kreiraj email poruku
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = Config.EMAIL_USER
    msg['To'] = Config.RECIPIENT_EMAIL
    
    msg.attach(MIMEText(body, 'html'))
    
    try:
        # Pošalji email
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
    logger.info("🚀 Počinjem dnevnu proveru tendera...")
    
    # Učitaj već poslate tendere
    processed_tenders = load_processed_tenders()
    
    # Preuzmi tendere sa portala
    logger.info("📥 Preuzimam tendere sa portala...")
    tenders = fetch_tenders_from_portal()
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

if __name__ == "__main__":
    main()
