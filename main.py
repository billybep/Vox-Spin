import fastapi
from fastapi.middleware.cors import CORSMiddleware
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
from fastapi.responses import StreamingResponse
import json
from dotenv import load_dotenv

# Muat variabel environment dari file .env (untuk lokal)
load_dotenv()

# 1. Inisialisasi Firebase Admin SDK
try:
    firebase_cred_env = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if firebase_cred_env:
        # Jika ada environment variable JSON (misal di Railway)
        cred_dict = json.loads(firebase_cred_env)
        cred = credentials.Certificate(cred_dict)
    else:
        # Fallback untuk environment lokal
        cred = credentials.Certificate("firebase-service-account.json")
        
    firebase_admin.initialize_app(cred)
    db = firestore.client()
except Exception as e:
    print(f"Error inisialisasi Firebase: {e}")

# 2. Inisialisasi Aplikasi FastAPI
app = fastapi.FastAPI(title="VoxSpin API", version="1.6")

# Konfigurasi CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Konfigurasi SMTP Email Agensi
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

# Konfigurasi Fonnte WhatsApp API
FONNTE_TOKEN = os.getenv("FONNTE_TOKEN")

# Konfigurasi Integrasi GoHighLevel (GHL) API (Opsional)
GHL_API_KEY = os.getenv("GHL_API_KEY")
GHL_LOCATION_ID = os.getenv("GHL_LOCATION_ID")

# 3. Model Skema Data (Pydantic)
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

# --- TAMBAHAN BARU: Model Template ---
class TemplatesUpdate(BaseModel):
    winner_wa: str
    winner_email: str
    followup_wa: str
    followup_email: str
    email_header: Optional[str] = ""
    email_footer: Optional[str] = ""
    header_image_url: Optional[str] = ""

# 4. Helper Fungsi Email & GHL Sync
def send_email(to_email: str, subject: str, html_content: str):
    if not to_email:
        return
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = to_email

        part = MIMEText(html_content, "html")
        msg.attach(part)

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        print(f"Email successfully sent to {to_email}")
    except Exception as e:
        print(f"Failed to send email to {to_email}: {e}")

def sync_to_gohighlevel(participant: Participant):
    if not GHL_API_KEY or "MASUKKAN" in GHL_API_KEY:
        return
    try:
        url = "https://services.leadconnectorhq.com/contacts/"
        headers = {
            "Authorization": GHL_API_KEY,
            "Content-Type": "application/json",
            "Version": "2021-07-28"
        }
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
        print(f"Failed to sync with GoHighLevel: {e}")

def build_full_email_html(body_content: str) -> str:
    templates = get_templates()
    header = templates.get("email_header", "")
    footer = templates.get("email_footer", "")
    banner_url = templates.get("header_image_url", "")
    
    banner_html = f"<div style='text-align:center; margin-bottom:20px;'><img src='{banner_url}' style='max-width:100%; height:auto; border-radius:8px;'/></div>" if banner_url else ""
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="UTF-8"><title>Voxlumedia Notification</title></head>
    <body style="margin: 0; padding: 0; background-color: #030712; font-family: Arial, sans-serif;">
        <table width="100%" style="background-color: #030712; padding: 40px 0;">
            <tr><td align="center">
                <table width="600" style="background-color: #0a1f35; border-radius: 16px; border: 1px solid rgba(139, 92, 246, 0.2); padding: 35px; color: #f8fafc;">
                    <tr><td>
                        {header}
                        {banner_html}
                        {body_content}
                        <br><hr style="border:0; border-top:1px solid rgba(255,255,255,0.05); margin:20px 0;">
                        {footer}
                    </td></tr>
                </table>
            </td></tr>
        </table>
    </body>
    </html>
    """

def get_templates() -> dict:
    doc = db.collection("settings").document("templates").get()
    if doc.exists:
        return doc.to_dict()
    # Templat Default Lengkap Tanpa Emotikon
    return {
        "winner_wa": "Halo tim {company_name}! Selamat, brand Anda terpilih sebagai PEMENANG VoxSpin Weekly Giveaway dari Voxlumedia. Balas pesan ini untuk klaim hadiah Anda.",
        "winner_email": "<h2>Selamat, {company_name}! Anda Menang!</h2><p>Brand Anda terpilih sebagai PEMENANG UTAMA VoxSpin Weekly Giveaway.</p>",
        "followup_wa": "Halo {company_name}! Belum beruntung di VoxSpin minggu ini? Jangan bersedih. Sembari menunggu undian Jumat depan, yuk upgrade visibilitas bisnismu menggunakan VoxCard atau VoxSocial AI secara gratis.",
        "followup_email": "<h2>Tetap Semangat, {company_name}!</h2><p>Anda belum terpilih minggu ini, tapi nama Anda masih ada di dalam undian untuk minggu depan.</p>",
        "email_header": "<div style='text-align:center; padding:15px; background:#0f172a; color:#fff; font-weight:bold;'>Voxlumedia Official Notification</div>",
        "email_footer": "<p style='font-size:12px; color:#64748b; text-align:center;'>Voxlumedia Agency | Branding, Design and Marketing</p>",
        "header_image_url": "https://voxcard.voxlumedia.com/wp-content/uploads/2026/05/VoxMaskot-scaled.webp"
    }

# def get_winner_email_html(company_name: str) -> str:
#     return f"""
#     <!DOCTYPE html>
#     <html>
#     <head><meta charset="UTF-8"><title>VoxSpin Winner Notification</title></head>
#     <body style="margin: 0; padding: 0; background-color: #030712; font-family: Arial, sans-serif;">
#         <table width="100%" style="background-color: #030712; padding: 40px 0;">
#             <tr><td align="center">
#                 <table width="600" style="background-color: #0a1f35; border-radius: 16px; border: 1px solid rgba(139, 92, 246, 0.2); padding: 35px; color: #f8fafc;">
#                     <tr><td>
#                         <h2 style="color: #ffd700; margin-top: 0;">🎉 Selamat, {company_name}!</h2>
#                         <p style="color: #cbd5e1; font-size: 15px; line-height: 1.6;">
#                             Brand Anda terpilih sebagai <b>PEMENANG UTAMA</b> VoxSpin Weekly Giveaway dari Voxlumedia!
#                         </p>
#                         <p style="color: #cbd5e1; font-size: 15px; line-height: 1.6;">
#                             Hadiah Anda: <b>1 Free Premium Social Media Design Content</b> + Sertifikat Digital Resmi.
#                         </p>
#                         <br>
#                         <a href="https://wa.me/6289693009966?text=Halo%20Admin,%20saya%20{company_name}%20pemenang%20VoxSpin." style="background: #8b5cf6; color: #fff; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: bold; display: inline-block;">Klaim Hadiah Sekarang →</a>
#                     </td></tr>
#                 </table>
#             </td></tr>
#         </table>
#     </body>
#     </html>
#     """

def get_registration_email_html(company_name: str) -> str:
    raw_body = f"""
        <h2 style="color: #8b5cf6; margin-top: 0;">Welcome to VoxSpin, {company_name}!</h2>
        <p style="color: #cbd5e1; font-size: 15px; line-height: 1.6;">
            Your business has been successfully registered for the VoxSpin weekly giveaway by Voxlumedia.
        </p>
    """
    # Bungkus dengan global template (header, footer, banner)
    return build_full_email_html(raw_body)

def send_whatsapp_message(phone: str, message: str):
    if not phone:
        return
    try:
        clean_phone = "".join(filter(str.isdigit, phone))
        headers = {"Authorization": FONNTE_TOKEN}
        payload = {
            "target": clean_phone,
            "message": message,
            "countryCode": "62"
        }
        requests.post("https://api.fonnte.com/send", headers=headers, data=payload)
    except Exception as e:
        print(f"Failed to send WhatsApp: {e}")

def generate_certificate(company_name: str, winner_date_str: str, week_num: int) -> str:
    os.makedirs("certificates", exist_ok=True)
    width, height = 1200, 800
    image = Image.new("RGB", (width, height), color="#030712")
    draw = ImageDraw.Draw(image)
    
    try:
        title_font = ImageFont.truetype("arial.ttf", 42)
        name_font = ImageFont.truetype("arial.ttf", 64)
        body_font = ImageFont.truetype("arial.ttf", 24)
    except:
        title_font = ImageFont.load_default()
        name_font = ImageFont.load_default()
        body_font = ImageFont.load_default()

    draw.rectangle([40, 40, width - 40, height - 40], outline="#8b5cf6", width=4)
    draw.rectangle([52, 52, width - 52, height - 52], outline="#d946ef", width=1)
    
    draw.text((width / 2, 160), "VOXLUMEDIA CERTIFICATE OF ACHIEVEMENT", fill="#d946ef", anchor="mm", font=title_font)
    draw.text((width / 2, 240), "THIS IS PROUDLY PRESENTED TO", fill="#94a3b8", anchor="mm", font=body_font)
    draw.text((width / 2, 360), company_name.upper(), fill="#ffffff", anchor="mm", font=name_font)
    
    description = (
        f"As the official Winner of VoxSpin Weekly Giveaway\n"
        f"for winning 1 Free Premium Social Media Design Content.\n\n"
        f"Date: {winner_date_str} | Week #{week_num}"
    )
    draw.multiline_text((width / 2, 520), description, fill="#94a3b8", anchor="mm", font=body_font, align="center")
    draw.text((width / 2, 680), "Verified & Issued by VoxSpin Agency System", fill="#64748b", anchor="mm", font=body_font)
    
    filename = f"certificates/certificate_{company_name.replace(' ', '_').lower()}.png"
    image.save(filename)
    return filename

# 5. Endpoints / API Routes
@app.post("/api/register")
async def register_participant(participant: Participant):
    try:
        doc_ref = db.collection("participants").document()
        doc_ref.set({
            "companyName": participant.companyName,
            "socialMedia": participant.socialMedia.lower(),
            "phone": participant.phone,
            "email": participant.email,
            "website": participant.website,
            "tiktok": participant.tiktok,
            "facebook": participant.facebook,
            "address": participant.address,
            "niche": participant.niche,
            "status": "pending",
            "date": datetime.now(timezone.utc),
            "winnerDate": None
        })

        if participant.email:
            html_body = get_registration_email_html(company_name=participant.companyName)
            send_email(to_email=participant.email, subject="Registration Confirmed - VoxSpin Giveaway", html_content=html_body)

        sync_to_gohighlevel(participant)

        return {"status": "success", "message": "Pendaftaran berhasil dan tersync ke GHL", "id": doc_ref.id}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=f"Gagal mendaftar: {str(e)}")

@app.post("/api/webhook/gohighlevel")
async def ghl_webhook(participant: Participant):
    try:
        existing = db.collection("participants").where("socialMedia", "==", participant.socialMedia.lower()).limit(1).get()
        if len(list(existing)) > 0:
            return {"status": "skipped", "message": "Participant already exists"}

        doc_ref = db.collection("participants").document()
        doc_ref.set({
            "companyName": participant.companyName,
            "socialMedia": participant.socialMedia.lower(),
            "phone": participant.phone,
            "email": participant.email,
            "website": participant.website,
            "tiktok": participant.tiktok,
            "facebook": participant.facebook,
            "address": participant.address,
            "niche": participant.niche,
            "status": "pending",
            "date": datetime.now(timezone.utc),
            "winnerDate": None
        })
        return {"status": "success", "message": "GHL Lead synced successfully", "id": doc_ref.id}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=f"GHL Webhook error: {str(e)}")

@app.get("/api/participants")
async def get_participants():
    try:
        docs = db.collection("participants").order_by("date", direction=firestore.Query.DESCENDING).stream()
        results = []
        for doc in docs:
            data = doc.to_dict()
            if "date" in data and data["date"]:
                data["date"] = data["date"].isoformat()
            if "winnerDate" in data and data["winnerDate"]:
                data["winnerDate"] = data["winnerDate"].isoformat()
            data["id"] = doc.id
            results.append(data)
            
        return {"status": "success", "data": results}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))

@app.post("/api/set-winner/{doc_id}")
async def set_winner(doc_id: str):
    try:
        doc_ref = db.collection("participants").document(doc_id)
        doc = doc_ref.get()
        
        if not doc.exists:
            raise fastapi.HTTPException(status_code=404, detail="Peserta tidak ditemukan")
        
        data = doc.to_dict()
        now_utc = datetime.now(timezone.utc)
        
        doc_ref.update({
            "status": "winner",
            "winnerDate": now_utc
        })
        
        company = data.get("companyName", "Klien")
        phone = data.get("phone", "")
        email = data.get("email", "")
        social = data.get("socialMedia", "")
        
        week_num = now_utc.isocalendar()[1]
        date_str = now_utc.strftime("%B %d, %Y")
        
        cert_path = generate_certificate(company, date_str, week_num)
        templates = get_templates()
        
        
        message = (
            f"Halo tim {company}! Selamat, brand Anda terpilih sebagai PEMENANG "
            f"VoxSpin Weekly Giveaway dari Voxlumedia (@voxlumedia)! "
            f"Sertifikat digital Anda telah diterbitkan. Silakan balas pesan ini untuk klaim 1 Free Premium Social Media Design Content Anda."
        )
        
        # Ganti teks {company_name} dengan nama asli klien
        wa_message = templates.get("winner_wa", "").replace("{company_name}", company)
        send_whatsapp_message(phone, wa_message)

        # Ambil, format, dan bungkus template Email dari database admin dengan layout global
        raw_email_body = templates.get("winner_email", "").replace("{company_name}", company)
        email_html_content = build_full_email_html(raw_email_body)
        
        if email:
            send_email(to_email=email, subject="Selamat, Anda Pemenang VoxSpin Giveaway! 🏆", html_content=email_html_content)
        
        clean_phone = "".join(filter(str.isdigit, phone))
        wa_link = f"https://wa.me/{clean_phone}?text={urllib.parse.quote(wa_message)}"
        
        return {
            "status": "success", 
            "message": "Pemenang ditetapkan, sertifikat digital digenerate, dan WhatsApp terkirim!",
            "winner": {
                "companyName": company,
                "phone": phone,
                "socialMedia": social,
                "certificate": cert_path,
                "whatsapp_link": wa_link
            }
        }
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=f"Gagal menetapkan pemenang: {str(e)}")

@app.get("/api/export/json")
async def export_json():
    try:
        docs = db.collection("participants").stream()
        results = [doc.to_dict() for doc in docs]
        return {"status": "success", "count": len(results), "data": results}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))

@app.post("/api/import/csv")
async def import_csv(file: fastapi.UploadFile = fastapi.File(...)):
    try:
        content = await file.read()
        decoded = content.decode("utf-8")
        reader = csv.DictReader(io.StringIO(decoded))
        
        count = 0
        batch = db.batch()
        for row in reader:
            doc_ref = db.collection("participants").document()
            batch.set(doc_ref, {
                "companyName": row.get("Brand Name", row.get("companyName", "Unknown")),
                "socialMedia": row.get("Instagram", row.get("socialMedia", "")).lower(),
                "phone": row.get("Phone", row.get("phone", "")),
                "email": row.get("Email", row.get("email", "")),
                "website": row.get("Website", row.get("website", "")),
                "tiktok": row.get("TikTok", row.get("tiktok", "")),
                "facebook": row.get("Facebook", row.get("facebook", "")),
                "address": row.get("Address", row.get("address", "")),
                "niche": row.get("Industry", row.get("niche", "")),
                "status": "pending",
                "date": datetime.now(timezone.utc),
                "winnerDate": None
            })
            count += 1
            
        batch.commit()
        return {"status": "success", "message": f"Berhasil mengimpor {count} data peserta ke database."}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=f"Gagal memproses file CSV: {str(e)}")

@app.delete("/api/participants/{doc_id}")
async def delete_participant(doc_id: str):
    try:
        doc_ref = db.collection("participants").document(doc_id)
        if not doc_ref.get().exists:
            raise fastapi.HTTPException(status_code=404, detail="Data tidak ditemukan")
        doc_ref.delete()
        return {"status": "success", "message": "Data peserta berhasil dihapus"}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=f"Gagal menghapus data: {str(e)}")

@app.delete("/api/participants")
async def delete_all_participants():
    try:
        docs = db.collection("participants").stream()
        batch = db.batch()
        count = 0
        for doc in docs:
            batch.delete(doc.reference)
            count += 1
        batch.commit()
        return {"status": "success", "message": f"Berhasil menghapus {count} data peserta"}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=f"Gagal mengosongkan database: {str(e)}")

# Konfigurasi Firebase Web API Key (Ambil dari Firebase Console -> Project Settings -> General -> Web API Key)
FIREBASE_WEB_API_KEY = "AIzaSyDfCJHHC4G_dPGS0qr-S7ZqsTxBXgOphq0"

@app.post("/api/admin/login")
async def admin_login(admin: AdminLogin):
    try:
        input_email = admin.email.strip().lower()
        input_password = admin.password.strip()
        
        if not FIREBASE_WEB_API_KEY or "MASUKKAN" in FIREBASE_WEB_API_KEY:
            raise fastapi.HTTPException(
                status_code=500, 
                detail="Firebase Web API Key belum diatur di main.py!"
            )
            
        # Kirim request verifikasi ke Firebase Auth REST API
        url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
        payload = {
            "email": input_email,
            "password": input_password,
            "returnSecureToken": True
        }
        
        response = requests.post(url, json=payload)
        res_data = response.json()
        
        if response.status_code == 200:
            return {
                "status": "success", 
                "message": "Login berhasil",
                "idToken": res_data.get("idToken"),
                "email": input_email
            }
        else:
            # Ambil pesan error spesifik dari Firebase (misal: INVALID_PASSWORD, EMAIL_NOT_FOUND)
            error_msg = res_data.get("error", {}).get("message", "Gagal autentikasi")
            if "INVALID_PASSWORD" in error_msg or "EMAIL_NOT_FOUND" in error_msg or "INVALID_LOGIN_CREDENTIALS" in error_msg:
                detail_text = "Email atau password yang Anda masukkan salah!"
            else:
                detail_text = f"Login gagal: {error_msg}"
                
            raise fastapi.HTTPException(status_code=401, detail=detail_text)
            
    except fastapi.HTTPException as he:
        raise he
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))
    
# --- ENDPOINT BARU: TEMPLATE EDITOR ---
@app.get("/api/settings/templates")
async def api_get_templates():
    return {"status": "success", "data": get_templates()}

@app.post("/api/settings/templates")
async def api_save_templates(t: TemplatesUpdate):
    db.collection("settings").document("templates").set(t.dict())
    return {"status": "success", "message": "Template berhasil disimpan!"}

# --- ENDPOINT BARU: BLAST AUTO-FOLLOW-UP ---
def run_blast_task(templates, pending_participants):
    for p in pending_participants:
        company = p.get("companyName", "Klien")
        phone = p.get("phone")
        email = p.get("email")

        if phone:
            wa_msg = templates.get("followup_wa", "").replace("{company_name}", company)
            send_whatsapp_message(phone, wa_msg)

        if email:
            raw_email_msg = templates.get("followup_email", "").replace("{company_name}", company)
            # Bungkus dengan global template
            email_msg = build_full_email_html(raw_email_msg)
            send_email(to_email=email, subject="Kejutan Spesial dari Voxlumedia! 🎁", html_content=email_msg)

@app.post("/api/blast-followup")
async def blast_followup(background_tasks: fastapi.BackgroundTasks):
    try:
        docs = db.collection("participants").where("status", "==", "pending").stream()
        pending_list = [doc.to_dict() for doc in docs]
        
        if not pending_list:
            raise fastapi.HTTPException(status_code=400, detail="Tidak ada peserta aktif untuk di-blast.")
            
        templates = get_templates()
        
        # Eksekusi secara Asynchronous (Latar Belakang) agar browser Admin tidak nge-hang
        background_tasks.add_task(run_blast_task, templates, pending_list)
        
        return {"status": "success", "message": f"Proses Blast Follow-Up ke {len(pending_list)} bisnis sedang berjalan di sistem."}
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))