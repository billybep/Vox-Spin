import fastapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone
import requests
import urllib.parse
from typing import Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
from PIL import Image, ImageDraw, ImageFont
import csv
import io
import json
from dotenv import load_dotenv
from fastapi import BackgroundTasks

# Load environment variables
load_dotenv()

# 1. Initialize Firebase Admin SDK
try:
    firebase_cred_env = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if firebase_cred_env:
        cred_dict = json.loads(firebase_cred_env)
        cred = credentials.Certificate(cred_dict)
    else:
        cred = credentials.Certificate("firebase-service-account.json")
        
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Error initializing Firebase: {e}")

# 2. Initialize FastAPI Application
app = fastapi.FastAPI(title="VoxSpin API", version="1.8")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ubah default server ke Hostinger
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.hostinger.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "adrian@voxlumedia.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "Adrian_080808")
FONNTE_TOKEN = os.getenv("FONNTE_TOKEN", "MASUKKAN_TOKEN_FONNTE_ANDA_DISINI")
GHL_API_KEY = os.getenv("GHL_API_KEY", "")
GHL_LOCATION_ID = os.getenv("GHL_LOCATION_ID", "")

# 3. Data Models
class Participant(BaseModel):
    companyName: str
    socialMedia: str
    phone: str
    email: Optional[str] = ""
    website: Optional[str] = ""
    tiktok: Optional[str] = ""
    facebook: Optional[str] = ""
    address: Optional[str] = ""
    niche: Optional[str] = ""

class AdminLogin(BaseModel):
    email: str
    password: str

class TemplatesUpdate(BaseModel):
    winner_wa: str
    winner_email: str
    followup_wa: str
    followup_email: str
    email_header: Optional[str] = ""
    email_footer: Optional[str] = ""
    header_image_url: Optional[str] = ""

# 4. Helper Functions (Email, GHL, WA, Certificate)
def send_email(to_email: str, subject: str, html_content: str):
    if not to_email: return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email
        part = MIMEText(html_content, "html")
        msg.attach(part)
        
        # Menggunakan SMTP_SSL khusus untuk port 465 Hostinger
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")

def sync_to_gohighlevel(participant: Participant):
    if not GHL_API_KEY or "MASUKKAN" in GHL_API_KEY: return
    try:
        url = "https://services.leadconnectorhq.com/contacts/"
        headers = {"Authorization": GHL_API_KEY, "Content-Type": "application/json", "Version": "2021-07-28"}
        payload = {
            "locationId": GHL_LOCATION_ID,
            "firstName": participant.companyName,
            "email": participant.email,
            "phone": participant.phone,
            "source": "VoxSpin Weekly Giveaway",
            "customFields": [
                {"key": "instagram", "field_value": participant.socialMedia},
                {"key": "industry_niche", "field_value": participant.niche}
            ]
        }
        requests.post(url, json=payload, headers=headers)
    except Exception as e:
        print(f"Failed GHL sync: {e}")

def get_templates() -> dict:
    doc = db.collection("settings").document("templates").get()
    if doc.exists: return doc.to_dict()
    return {
        "winner_wa": "Hello {company_name} team! Congratulations, your brand has been selected as the WINNER of the VoxSpin Weekly Giveaway by Voxlumedia. Please reply to this message to claim your prize.",
        "winner_email": "<h2>Congratulations, {company_name}! You Won!</h2><p>Your brand has been selected as the MAIN WINNER of the VoxSpin Weekly Giveaway.</p>",
        "followup_wa": "Hello {company_name}! No luck on VoxSpin this week? Don't worry. While waiting for next Friday's draw, let's upgrade your business visibility using VoxCard or VoxSocial AI for free.",
        "followup_email": "<h2>Keep your spirits up, {company_name}!</h2><p>You were not selected this week, but your name remains in the drawing pool for next week's giveaway.</p>",
        "email_header": "<div style='text-align:center; padding:15px; background:#0f172a; color:#fff; font-weight:bold;'>Voxlumedia Official Notification</div>",
        "email_footer": "<p style='font-size:12px; color:#64748b; text-align:center;'>Voxlumedia Agency | Branding, Design and Marketing</p>",
        "header_image_url": "https://voxcard.voxlumedia.com/wp-content/uploads/2026/05/VoxMaskot-scaled.webp"
    }

def build_full_email_html(body_content: str) -> str:
    templates = get_templates()
    header = templates.get("email_header", "")
    footer = templates.get("email_footer", "")
    banner_url = templates.get("header_image_url", "")
    banner_html = f"<div style='text-align:center; margin-bottom:20px;'><img src='{banner_url}' style='max-width:100%; height:auto; border-radius:8px;'/></div>" if banner_url else ""
    
    return f"""
    <!DOCTYPE html>
    <html>
    <body style="margin: 0; padding: 0; background-color: #030712; font-family: Arial, sans-serif;">
        <table width="100%" style="background-color: #030712; padding: 40px 0;">
            <tr><td align="center">
                <table width="600" style="background-color: #0a1f35; border-radius: 16px; border: 1px solid rgba(139, 92, 246, 0.2); padding: 35px; color: #f8fafc;">
                    <tr><td>
                        {header}{banner_html}{body_content}
                        <br><hr style="border:0; border-top:1px solid rgba(255,255,255,0.05); margin:20px 0;">{footer}
                    </td></tr>
                </table>
            </td></tr>
        </table>
    </body></html>
    """

def get_registration_email_html(company_name: str) -> str:
    raw_body = f"<h2 style='color: #8b5cf6;'>Welcome to VoxSpin, {company_name}!</h2><p>Your business has been successfully registered for the weekly giveaway.</p>"
    return build_full_email_html(raw_body)

def send_whatsapp_message(phone: str, message: str):
    if not phone: return
    try:
        clean_phone = "".join(filter(str.isdigit, phone))
        requests.post("https://api.fonnte.com/send", headers={"Authorization": FONNTE_TOKEN}, data={"target": clean_phone, "message": message, "countryCode": "62"})
    except Exception as e:
        print(f"Failed to send WhatsApp: {e}")

def generate_certificate(company_name: str, winner_date_str: str, week_num: int) -> str:
    os.makedirs("certificates", exist_ok=True)
    width, height = 1200, 800
    image = Image.new("RGB", (width, height), color="#030712")
    draw = ImageDraw.Draw(image)
    try:
        title_font, name_font, body_font = ImageFont.truetype("arial.ttf", 42), ImageFont.truetype("arial.ttf", 64), ImageFont.truetype("arial.ttf", 24)
    except:
        title_font = name_font = body_font = ImageFont.load_default()

    draw.rectangle([40, 40, width - 40, height - 40], outline="#8b5cf6", width=4)
    draw.text((width / 2, 160), "VOXLUMEDIA CERTIFICATE", fill="#d946ef", anchor="mm", font=title_font)
    draw.text((width / 2, 360), company_name.upper(), fill="#ffffff", anchor="mm", font=name_font)
    filename = f"certificates/certificate_{company_name.replace(' ', '_').lower()}.png"
    image.save(filename)
    return filename

# Background Task Runners
def run_registration_tasks(participant: Participant):
    if participant.email:
        html_body = get_registration_email_html(company_name=participant.companyName)
        send_email(to_email=participant.email, subject="Registration Confirmed - VoxSpin", html_content=html_body)
    sync_to_gohighlevel(participant)

def run_winner_tasks(company, phone, email, date_str, week_num, templates):
    generate_certificate(company, date_str, week_num)
    wa_message = templates.get("winner_wa", "").replace("{company_name}", company)
    send_whatsapp_message(phone, wa_message)
    if email:
        raw_email_body = templates.get("winner_email", "").replace("{company_name}", company)
        email_html_content = build_full_email_html(raw_email_body)
        send_email(to_email=email, subject="Congratulations! You're a VoxSpin Winner 🏆", html_content=email_html_content)

# 5. Endpoints / API Routes
@app.post("/api/register")
def register_participant(participant: Participant, background_tasks: BackgroundTasks):
    try:
        doc_ref = db.collection("participants").document()
        doc_ref.set({
            "companyName": participant.companyName, "socialMedia": participant.socialMedia.lower(),
            "phone": participant.phone, "email": participant.email, "website": participant.website,
            "tiktok": participant.tiktok, "facebook": participant.facebook, "address": participant.address,
            "niche": participant.niche, "status": "pending", "date": datetime.now(timezone.utc), "winnerDate": None
        })
        background_tasks.add_task(run_registration_tasks, participant)
        return {"status": "success", "message": "Registration successful and synced to GHL", "id": doc_ref.id}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))

@app.get("/api/participants")
def get_participants():
    try:
        docs = db.collection("participants").order_by("date", direction=firestore.Query.DESCENDING).stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            if data.get("date"): data["date"] = data["date"].isoformat()
            if data.get("winnerDate"): data["winnerDate"] = data["winnerDate"].isoformat()
            data["id"] = doc.id
            results.append(data)
        return {"status": "success", "data": results}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))

@app.post("/api/set-winner/{doc_id}")
def set_winner(doc_id: str, background_tasks: BackgroundTasks):
    try:
        doc_ref = db.collection("participants").document(doc_id)
        doc = doc_ref.get()
        if not doc.exists: raise fastapi.HTTPException(status_code=404, detail="Participant not found")
        
        data = doc.to_dict()
        now_utc = datetime.now(timezone.utc)
        doc_ref.update({"status": "winner", "winnerDate": now_utc})
        
        company = data.get("companyName", "Client")
        phone = data.get("phone", "")
        email = data.get("email", "")
        templates = get_templates()
        
        background_tasks.add_task(run_winner_tasks, company, phone, email, now_utc.strftime("%B %d, %Y"), now_utc.isocalendar()[1], templates)
        
        wa_message = templates.get("winner_wa", "").replace("{company_name}", company)
        wa_link = f"https://wa.me/{phone}?text={urllib.parse.quote(wa_message)}"
        return {"status": "success", "message": "Winner set successfully.", "winner": {"whatsapp_link": wa_link}}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))

FIREBASE_WEB_API_KEY = "AIzaSyDfCJHHC4G_dPGS0qr-S7ZqsTxBXgOphq0"

@app.post("/api/admin/login")
def admin_login(admin: AdminLogin):
    try:
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
        payload = {"email": admin.email.strip().lower(), "password": admin.password.strip(), "returnSecureToken": True}
        response = requests.post(url, json=payload)
        res_data = response.json()
        if response.status_code == 200:
            return {"status": "success", "idToken": res_data.get("idToken")}
        raise fastapi.HTTPException(status_code=401, detail="Invalid email or password!")
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings/templates")
def api_get_templates():
    return {"status": "success", "data": get_templates()}

@app.post("/api/settings/templates")
def api_save_templates(t: TemplatesUpdate):
    db.collection("settings").document("templates").set(t.dict())
    return {"status": "success", "message": "Templates saved successfully!"}

def run_blast_task(templates, pending_participants):
    for p in pending_participants:
        company, phone, email = p.get("companyName", "Client"), p.get("phone"), p.get("email")
        if phone: send_whatsapp_message(phone, templates.get("followup_wa", "").replace("{company_name}", company))
        if email: send_email(to_email=email, subject="Special Surprise from Voxlumedia! 🎁", html_content=build_full_email_html(templates.get("followup_email", "").replace("{company_name}", company)))

@app.post("/api/blast-followup")
def blast_followup(background_tasks: BackgroundTasks):
    try:
        pending = [d.to_dict() for d in db.collection("participants").where("status", "==", "pending").stream()]
        if not pending: raise fastapi.HTTPException(status_code=400, detail="No active participants to blast.")
        
        background_tasks.add_task(run_blast_task, get_templates(), pending)
        return {"status": "success", "message": f"Follow-up blast to {len(pending)} businesses is running in the background."}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))

@app.delete("/api/participants/{doc_id}")
def delete_participant(doc_id: str):
    db.collection("participants").document(doc_id).delete()
    return {"status": "success", "message": "Record deleted successfully"}

app.mount("/", StaticFiles(directory=".", html=True), name="static")
@app.delete("/api/participants")
def clear_all_participants():
    try:
        docs = db.collection("participants").stream()
        deleted_count = 0
        for doc in docs:
            doc.reference.delete()
            deleted_count += 1
        return {"status": "success", "message": f"Successfully deleted {deleted_count} records."}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))
