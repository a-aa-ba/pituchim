import os
import json
import base64
import random
import smtplib
import requests
import subprocess
import traceback
import urllib.parse
from datetime import datetime
from typing import Dict, Any, Optional
from email.message import EmailMessage
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import Response
import imageio_ffmpeg
import speech_recognition as sr

app = FastAPI(title="Yemot Sales IVR System")

# ===================================================================
# 1. הגדרה לפתיחה/סגירה של שלוחות תפריט ראשי (True = פתוח, False = סגור)
OPEN_BRANCHES = {
    "1": True,   # שלוחה 1: הודעות
    "2": False,   # שלוחה 2: הזמנות
    "3": False,   # שלוחה 3: אזור אישי
    "4": True,   # שלוחה 4: רישום לצינתוקים כללי
    "5": True    # שלוחה 5: השארת הודעה לגבאי
}

# רשימת מספרי טלפון או ת.ז שמורשים להיכנס למערכת גם כשהשלוחה סגורה (VIP)
ALLOWED_PHONES_WHEN_CLOSED = [
    "0533160009",
    "0527123207"
]

# 2. שימוש בקובצי שמע מוקלטים (אם קובץ חסר, ישתמש ב-TTS אוטומטית)
USE_AUDIO_FILES = False
AUDIO_FOLDER = "הודעות מערכת"
# ===================================================================

# הגדרות ימות המשיח ו-Google Apps Script
YEMOT_TOKEN = os.environ.get("YEMOT_TOKEN", "093136538:112131")
OTP_YEMOT_TOKEN = os.environ.get("OTP_YEMOT_TOKEN", YEMOT_TOKEN)  # טוקן ממערכת אחרת לשכחתי סיסמא
OTP_CALLER_ID = os.environ.get("OTP_CALLER_ID", "")
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")

# הגדרות מייל לשליחת הודעה לגבאי
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
GABAI_EMAIL = os.environ.get("GABAI_EMAIL", "")

# הגדרות סליקת אשראי (נדרים פלוס, תשלום 1 בלבד)
CREDIT_CARD_PROVIDER = "nedarim_plus"
CREDIT_CARD_REGISTER_NO = "4001388"
CREDIT_CARD_MAX_PAYMENTS = "1"
CREDIT_CARD_CURRENCY = os.environ.get("CREDIT_CARD_CURRENCY", "1")  # 1 = שקל

CACHE = {
    "users": {},
    "categories": [],
    "products": [],
    "transactions": [],
    "cities": []
}

SESSIONS: Dict[str, Dict[str, Any]] = {}
SAVED_CARTS: Dict[str, list] = {}
OTP_PENDING: Dict[str, str] = {}

STEP_PARAM_MAP = {
    "WELCOME": ["welcome_choice", "ApiRealAnswer"],
    "LOGIN_ID": ["login_id", "ApiRealAnswer"],
    "LOGIN_ID_NOT_FOUND": ["login_not_found_choice", "ApiRealAnswer"],
    "LOGIN_PASS": ["login_pass", "ApiRealAnswer"],
    "LOGIN_WRONG_PASS": ["wrong_pass_choice", "ApiRealAnswer"],
    "FORGOT_OTP_INPUT": ["forgot_otp_input", "ApiRealAnswer"],
    "FORGOT_NEW_PASS": ["forgot_new_pass", "ApiRealAnswer"],
    "REG_ID": ["reg_id", "ApiRealAnswer"],
    "REG_PHONE": ["reg_phone", "ApiRealAnswer"],
    "REG_NAME": ["reg_name", "my_rec", "ApiRealAnswer"],
    "REG_NAME_CONFIRM": ["reg_name_confirm_choice", "ApiRealAnswer"],
    "REG_CITY": ["reg_city", "ApiRealAnswer"],
    "REG_ADDRESS": ["reg_address", "my_rec", "ApiRealAnswer"],
    "REG_ADDRESS_CONFIRM": ["reg_address_confirm_choice", "ApiRealAnswer"],
    "REG_COMMUNITY_CODE": ["reg_community_code", "ApiRealAnswer"],
    "REG_RETURN_FROM_TZINTUK": [],
    "REG_PASSWORD": ["reg_password", "ApiRealAnswer"],
    "REG_END_MENU": ["reg_end_choice", "ApiRealAnswer"],
    "RESTORE_CART_CHOICE": ["restore_cart_choice", "ApiRealAnswer"],
    "MAIN_MENU": ["cat_choice", "ApiRealAnswer"],
    "SKU_INPUT": ["sku_input", "ApiRealAnswer"],
    "KASHRUT_MENU": ["kashrut_choice", "ApiRealAnswer"],
    "PRODUCT_LIST_MENU": ["prod_list_choice", "ApiRealAnswer"],
    "PRODUCT_LOOP": ["product_choice", "ApiRealAnswer"],
    "QTY_INPUT": ["qty_input", "ApiRealAnswer"],
    "AFTER_ADD_MENU": ["after_add_choice", "ApiRealAnswer"],
    "CONFIRM_CHECKOUT_FEE": ["checkout_confirm_choice", "ApiRealAnswer"],
    "PERSONAL_AREA_MENU": ["personal_choice", "ApiRealAnswer"],
    "UPD_NAME_MENU": ["upd_name_choice", "ApiRealAnswer"],
    "UPD_NAME_REC": ["upd_name_rec", "my_rec", "ApiRealAnswer"],
    "UPD_NAME_CONFIRM": ["upd_name_confirm", "ApiRealAnswer"],
    "UPD_CITY_MENU": ["upd_city_choice", "ApiRealAnswer"],
    "UPD_CITY_SELECT": ["upd_city_select", "ApiRealAnswer"],
    "UPD_ADDR_MENU": ["upd_addr_choice", "ApiRealAnswer"],
    "UPD_ADDR_REC": ["upd_addr_rec", "my_rec", "ApiRealAnswer"],
    "UPD_ADDR_CONFIRM": ["upd_addr_confirm", "ApiRealAnswer"],
    "UPD_PHONE_MENU": ["upd_phone_choice", "ApiRealAnswer"],
    "UPD_PHONE_INPUT": ["upd_phone_input", "ApiRealAnswer"],
    "UPD_COMMUNITY_MENU": ["upd_comm_choice", "ApiRealAnswer"],
    "UPD_COMMUNITY_INPUT": ["upd_comm_input", "ApiRealAnswer"],
    "UPD_PASS_MENU": ["upd_pass_choice", "ApiRealAnswer"],
    "UPD_PASS_INPUT": ["upd_pass_input", "ApiRealAnswer"],
    "UPD_TZINTUK_MENU": ["upd_tzintuk_choice", "ApiRealAnswer"],
    "UPD_RETURN_FROM_TZINTUK": [],
    "TX_HISTORY_LIST": ["tx_list_choice", "ApiRealAnswer"],
    "TX_HISTORY_DETAIL": ["tx_detail_choice", "ApiRealAnswer"],
    "GABAI_AUTH_ID": ["gabai_auth_id", "ApiRealAnswer"],
    "GABAI_TZINTUK_PROMPT": ["gabai_tzintuk_choice", "ApiRealAnswer"],
    "GABAI_RETURN_FROM_TZINTUK": [],
    "GABAI_RECORD_MSG": ["gabai_msg", "my_rec", "ApiRealAnswer"]
}

PROMPT_FILE_MAP = {
    "welcome_choice": "001",
    "login_id": "003",
    "reg_name": "005",
    "reg_id": "007",
    "reg_phone": "009",
    "reg_address": "010",
    "reg_community_code": "012",
    "personal_choice": "014d",
    "upd_comm_input": "015",
    "cat_choice": "017b",
    "kashrut_choice": "017b",
    "qty_input": "020a",
    "product_choice": "022f",
    "after_add_choice": "022g",
    "checkout_confirm_choice": "023b",
    "restore_cart_choice": "026",
    "reg_city": "029"
}

# -------------------------------------------------------------------
# לוגר מרוכז ומתומצת לשרת
# -------------------------------------------------------------------
def log_step(call_id: str, phone: str, step: str, user_input: str, action: str):
    ts = datetime.now().strftime("%H:%M:%S")
    cid = str(call_id)[-6:] if call_id else "------"
    inp = user_input if user_input != "" else "[ריק]"
    print(f"[{ts}] [שיחה:{cid} | טל:{phone}] שלב={step} | קלט={inp} ➔ {action}", flush=True)

# -------------------------------------------------------------------
# 1. המרת שמע + הורדה מימות המשיח + תמלול בעברית
# -------------------------------------------------------------------
def convert_audio_to_pcm_wav(input_path: str, output_path: str) -> bool:
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        audio_filters = "highpass=f=200,lowpass=f=3400,afftdn,dynaudnorm"
        cmd = [
            ffmpeg_exe, "-y",
            "-i", input_path,
            "-af", audio_filters,
            "-ar", "16000",
            "-ac", "1",
            "-f", "wav",
            output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        return True
    except Exception as e:
        print(f"[FFmpeg ERROR]: {e}", flush=True)
        return False

def download_audio_bytes_from_yemot(my_rec_path: str, token: str = None) -> Optional[bytes]:
    if not my_rec_path or not isinstance(my_rec_path, str):
        return None

    active_token = (token or YEMOT_TOKEN or "").strip()
    raw_path = str(my_rec_path).strip()
    clean_path = raw_path.replace("Digits-", "").replace("val_name-", "").strip()
    if clean_path.startswith("ivr2:"):
        clean_path = clean_path[5:]
    clean_path = "/" + clean_path.lstrip('/')

    possible_paths = [f"ivr2:{clean_path}", f"ivr2:{raw_path}", clean_path, clean_path.lstrip('/')]
    for try_path in list(dict.fromkeys(possible_paths)):
        encoded_path = urllib.parse.quote(try_path, safe=':/')
        audio_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={active_token}&path={encoded_path}"
        try:
            r = requests.get(audio_url, timeout=15)
            if r.status_code == 200 and len(r.content) >= 100 and not r.content.startswith(b'<') and not r.content.startswith(b'{'):
                print(f"[שמע] הורד בהצלחה ({try_path}, {len(r.content)}B)", flush=True)
                return r.content
        except Exception as err:
            print(f"[שמע ERROR] {try_path}: {err}", flush=True)
    return None

def transcribe_audio_file_from_yemot(my_rec_path: str, token: str = None) -> str:
    audio_bytes = download_audio_bytes_from_yemot(my_rec_path, token)
    if not audio_bytes:
        print(f"[תמלול ERROR] נכשלה הורדה עבור '{my_rec_path}'", flush=True)
        return ""

    temp_audio = f"downloaded_{os.getpid()}.file"
    converted_wav = f"converted_{os.getpid()}.wav"
    try:
        with open(temp_audio, "wb") as f:
            f.write(audio_bytes)
        target_wav = converted_wav if convert_audio_to_pcm_wav(temp_audio, converted_wav) else temp_audio
        recognizer = sr.Recognizer()
        with sr.AudioFile(target_wav) as source:
            audio_data = recognizer.record(source)
            try:
                text = recognizer.recognize_google(audio_data, language='he-IL')
                print(f"[תמלול] הצלחה: '{text}'", flush=True)
                return text.strip() if text else ""
            except sr.UnknownValueError:
                print("[תמלול] לא זוהו מילים בהקלטה", flush=True)
                return ""
            except sr.RequestError as e:
                print(f"[תמלול ERROR] תקשורת: {e}", flush=True)
                return ""
    except Exception as e:
        print(f"[תמלול ERROR] {e}", flush=True)
        return ""
    finally:
        for p in (temp_audio, converted_wav):
            if os.path.exists(p):
                try: os.remove(p)
                except: pass

# -------------------------------------------------------------------
# 2. פונקציות עזר, ניקוי וניהול נתונים מ-Google Sheets
# -------------------------------------------------------------------
def clean_input(val: str) -> str:
    if not val:
        return ""
    val = str(val).strip()
    val = val.replace("#", "")
    if val.startswith("Digits-"):
        val = val.replace("Digits-", "")
    return val.strip()

def clean_tts(text: str) -> str:
    if not text:
        return ""
    text = str(text)
    for ch in [".", "-", "="]:
        text = text.replace(ch, " ")
    text = text.replace('"', "").replace("'", "")
    return text.strip()

def format_price(val) -> str:
    try:
        num = float(str(val).replace("₪", "").strip())
        return str(int(num)) if num.is_integer() else f"{num:.2f}"
    except Exception:
        return clean_tts(str(val))

def get_field(item: dict, *keys, default=""):
    if not item or not isinstance(item, dict):
        return default
    for k in keys:
        if k in item and item[k] is not None and str(item[k]).strip() != "":
            return item[k]
    return default

def get_user_id(user: dict) -> str:
    return str(get_field(user, "תעודת זהות", "ת.ז", "id_number", "id") or get_field(user, "מספר טלפון", "טלפון", "phone")).strip()

def get_user_phone(user: dict) -> str:
    return str(get_field(user, "מספר טלפון", "טלפון", "phone")).strip()

def get_user_name(user: dict) -> str:
    first = str(get_field(user, "שם פרטי ומשפחה", "שם פרטי", "שם", "first_name")).strip()
    last = str(get_field(user, "שם משפחה", "last_name")).strip()
    return f"{first} {last}".strip()

def get_user_city(user: dict) -> str:
    return str(get_field(user, "עיר", "שם עיר", "city")).strip()

def get_user_address(user: dict) -> str:
    return str(get_field(user, "כתובת", "כתובת מלאה", "address")).strip()

def get_user_community(user: dict) -> str:
    return str(get_field(user, "קוד קהילה", "community_code")).strip()

def get_user_password(user: dict) -> str:
    return str(get_field(user, "סיסמא", "סיסמה", "password", "pass")).strip()

def is_user_personal_tzintuk(user: dict) -> bool:
    val = str(get_field(user, "צינתוק אישי", "רישום לצינתוק אישי", "personal_tzintuk", "tzintuk", default="FALSE")).upper()
    return val in ["TRUE", "1", "YES", "כן"]

def has_community_discount(user: Optional[dict]) -> bool:
    if not user:
        return False
    code = get_user_community(user)
    return bool(code and code not in ["0", "לא עודכן", "ללא", "none", "None"])

def get_product_price_for_user(product: dict, user: Optional[dict]) -> str:
    regular_price = str(product.get("price", "0")).replace("₪", "").strip()
    comm_price = str(product.get("community_price", "")).replace("₪", "").strip()
    if has_community_discount(user) and comm_price:
        try:
            float(comm_price)
            return comm_price
        except ValueError:
            pass
    return regular_price

def sync_user_in_cache(user_obj: dict):
    id_num = str(get_field(user_obj, "תעודת זהות", "ת.ז", "id_number", "id")).strip()
    phone = get_user_phone(user_obj)
    if id_num:
        CACHE["users"][id_num] = user_obj
    if phone:
        CACHE["users"][phone] = user_obj

def load_data_from_sheets():
    if not APPS_SCRIPT_URL:
        print("[Sheets WARNING] APPS_SCRIPT_URL אינו מוגדר", flush=True)
        return
    try:
        response = requests.get(APPS_SCRIPT_URL, timeout=15)
        data = response.json()

        users_dict = {}
        for u in data.get("users", []):
            is_active = str(get_field(u, "פעיל", "is_active", default="TRUE")).upper()
            if is_active in ["TRUE", "1", "YES", "כן"]:
                id_num = str(get_field(u, "תעודת זהות", "ת.ז", "id_number", "id")).strip()
                phone = str(get_field(u, "מספר טלפון", "טלפון", "phone")).strip()
                if id_num:
                    users_dict[id_num] = u
                if phone:
                    users_dict[phone] = u
        CACHE["users"] = users_dict

        cats = []
        for c in data.get("categories", []):
            cats.append({
                "category_id": get_field(c, "מזהה קטגוריה", "category_id", "id"),
                "category_name": get_field(c, "שם קטגוריה", "קטגוריה", "category_name", "category"),
                "kashruts": get_field(c, "כשרויות זמינות", "כשרויות", "כשרות", "kashruts")
            })
        CACHE["categories"] = cats

        cities = []
        for ct in data.get("cities", []):
            is_active = str(get_field(ct, "פעיל", "is_active", default="TRUE")).upper()
            if is_active in ["TRUE", "1", "YES", "כן"]:
                city_name = str(get_field(ct, "שם עיר", "עיר", "city_name", "city")).strip()
                if city_name:
                    cities.append({
                        "city_id": str(get_field(ct, "מזהה עיר", "מזהה", "city_id", "id")).strip(),
                        "city_name": city_name
                    })
        CACHE["cities"] = cities

        prods = []
        for p in data.get("products", []):
            in_stock = str(get_field(p, "במלאי", "מלאי", "in_stock", default="TRUE")).upper()
            if in_stock in ["TRUE", "1", "YES", "כן"]:
                p_sku = str(get_field(p, "מקט", "מק\"ט", "מזהה מוצר", "מזהה", "sku")).strip()
                p_name = str(get_field(p, "שם מוצר", "שם המוצר", "שם", "מוצר", "name", "product_name")).strip()
                p_price = str(get_field(p, "מחיר ליחידה", "מחיר מוצר", "מחיר", "מחיר יחידה", "price", "unit_price")).strip()
                p_community_price = str(get_field(p, "מחיר קהילה", "מחיר לקהילה", "community_price")).strip()
                p_notes = str(get_field(p, "הערות", "הערה", "notes", "description")).strip()
                p_cat = str(get_field(p, "קטגוריה", "שם קטגוריה", "category_name", "category")).strip()
                p_kashrut = str(get_field(p, "כשרות", "כשרויות", "kashrut")).strip()
                if p_name:
                    prods.append({
                        "sku": p_sku,
                        "name": p_name,
                        "price": p_price,
                        "community_price": p_community_price,
                        "notes": p_notes,
                        "category_name": p_cat,
                        "kashrut": p_kashrut
                    })
        CACHE["products"] = prods

        txs = []
        for t in data.get("transactions", []):
            txs.append({
                "transaction_id": str(get_field(t, "מזהה עסקה", "מספר עסקה", "transaction_id", "id")),
                "timestamp": str(get_field(t, "תאריך", "חותמת זמן", "timestamp", "date")),
                "user_identifier": str(get_field(t, "מזהה משתמש", "תעודת זהות", "user_identifier", "id_number")),
                "user_name": str(get_field(t, "שם משתמש", "שם", "user_name")),
                "items_detail": str(get_field(t, "פירוט מוצרים", "פרטי הזמנה", "items_detail")),
                "total_amount": str(get_field(t, "סכום כולל", "סכום", "total_amount")),
                "status": str(get_field(t, "סטטוס", "status"))
            })
        CACHE["transactions"] = txs

        print(f"[CACHE] נטענו: {len(CACHE['users'])} מפתחות משתמש | {len(cats)} קטגוריות | {len(cities)} ערים | {len(prods)} מוצרים | {len(txs)} עסקאות", flush=True)
    except Exception as e:
        print(f"[Sheets ERROR] טעינה נכשלה: {e}", flush=True)

@app.on_event("startup")
async def startup_event():
    load_data_from_sheets()

@app.get("/refresh-cache")
async def refresh_cache():
    load_data_from_sheets()
    return {
        "status": "success",
        "products_count": len(CACHE["products"]),
        "cities_count": len(CACHE["cities"]),
        "transactions_count": len(CACHE["transactions"])
    }

def post_to_apps_script(payload: dict):
    if not APPS_SCRIPT_URL:
        return
    try:
        res = requests.post(APPS_SCRIPT_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=15)
        print(f"[Sheets POST:{payload.get('type')}] סטטוס {res.status_code}", flush=True)
    except Exception as e:
        print(f"[Sheets POST ERROR:{payload.get('type')}] {e}", flush=True)

def log_general_event(call_id: str, phone: str, event_type: str, details: str):
    post_to_apps_script({
        "type": "general_log",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "call_id": str(call_id),
        "phone": str(phone),
        "event_type": event_type,
        "details": details
    })

def save_new_user_to_sheet(user_data: dict):
    post_to_apps_script({
        "type": "register_user",
        "id_number": str(user_data.get("id_number", "")),
        "phone": str(user_data.get("phone", "")),
        "first_name": str(user_data.get("first_name", "")),
        "last_name": "",
        "city": str(user_data.get("city", "")),
        "address": str(user_data.get("address", "")),
        "community_code": str(user_data.get("community_code", "")),
        "password": str(user_data.get("password", "")),
        "personal_tzintuk": str(user_data.get("personal_tzintuk", "FALSE"))
    })

def update_user_in_sheet(user_data: dict):
    post_to_apps_script({
        "type": "update_user",
        "id_number": get_user_id(user_data),
        "phone": get_user_phone(user_data),
        "first_name": get_user_name(user_data),
        "city": get_user_city(user_data),
        "address": get_user_address(user_data),
        "community_code": get_user_community(user_data),
        "password": get_user_password(user_data),
        "personal_tzintuk": "TRUE" if is_user_personal_tzintuk(user_data) else "FALSE"
    })

def log_transaction_to_sheet(session_data: dict):
    user = session_data.get("user", {})
    cart = session_data.get("cart", [])
    items_summary = "; ".join([f"{item['name']} מקט {item['sku']} כמות {item['qty']} סך הכל {format_price(item['total'])} שח" for item in cart])
    total_sum = session_data.get("total_sum_with_fee", sum(item['total'] for item in cart) + 10)
    user_id = get_user_id(user)
    user_name = get_user_name(user)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    tx_record = {
        "type": "transaction",
        "transaction_id": str(session_data.get("call_id")),
        "timestamp": ts,
        "user_identifier": str(user_id),
        "user_name": user_name,
        "items_detail": items_summary,
        "total_amount": total_sum,
        "status": "הועבר לסליקה"
    }
    CACHE["transactions"].append(tx_record)
    post_to_apps_script(tx_record)

# -------------------------------------------------------------------
# 3. צינתוק אישי (UpdateExtension ל-/C + RunTzintuk + SendTTS ל-OTP) + גבאי
# -------------------------------------------------------------------
def update_yemot_tzintuk_extension(list_name: str, end_goto: str = "/"):
    """מגדיר בימות המשיח את שלוחה /C לרשימת הצינתוק האישית שמספרה כמספר המאזין"""
    if not YEMOT_TOKEN or not list_name:
        print("[UpdateExtension /C ERROR] חסר טוקן או שם רשימה", flush=True)
        return False
    try:
        res = requests.post(
            "https://www.call2all.co.il/ym/api/UpdateExtension",
            data={
                "token": YEMOT_TOKEN,
                "path": "ivr2:/C",
                "type": "tzintuk",
                "list_tzintuk": list_name,
                "tzintuk_end": end_goto
            },
            timeout=8
        )
        print(f"[UpdateExtension /C] list_tzintuk={list_name} | תגובה: {res.text[:120]}", flush=True)
        return True
    except Exception as e:
        print(f"[UpdateExtension /C ERROR] {e}", flush=True)
        return False

def send_personal_tzintuk_by_list(target_phone: str):
    """שולח צינתוק אישי לרשימה ששמה כמספר הטלפון של הלקוח (tzl:<phone>)"""
    if not target_phone or not YEMOT_TOKEN:
        print("[RunTzintuk ERROR] חסר טלפון או טוקן", flush=True)
        return False
    params = {
        "token": YEMOT_TOKEN,
        "phones": f"tzl:{target_phone}",
        "TzintukTimeOut": "16"
    }
    if OTP_CALLER_ID:
        params["callerId"] = OTP_CALLER_ID
    try:
        res = requests.get("https://www.call2all.co.il/ym/api/RunTzintuk", params=params, timeout=15)
        print(f"[RunTzintuk] נשלח לרשימה tzl:{target_phone} | תגובה: {res.text[:120]}", flush=True)
        return True
    except Exception as e:
        print(f"[RunTzintuk ERROR] {e}", flush=True)
        return False

@app.api_route("/send-personal-tzintuk", methods=["GET", "POST"])
async def trigger_personal_tzintuk(phone: str, background_tasks: BackgroundTasks):
    """נתיב עזר לשליחת צינתוק אישי יזום (למשל במתן תשובה מהגבאי)"""
    clean_phone = clean_input(phone)
    background_tasks.add_task(send_personal_tzintuk_by_list, clean_phone)
    return {"status": "queued", "list": f"tzl:{clean_phone}"}

def send_otp_tzintuk_call(target_phone: str, otp_code: str):
    if not target_phone or not OTP_YEMOT_TOKEN:
        print("[OTP ERROR] חסר טלפון או טוקן", flush=True)
        return
    digits_spaced = " ".join(list(otp_code))
    tts_msg = f"שלום, קוד האימות שלך לאיפוס הסיסמא הוא: {digits_spaced}."
    OTP_PENDING[target_phone] = otp_code

    params = {
        "token": OTP_YEMOT_TOKEN,
        "phones": target_phone,
        "ttsMessage": tts_msg,
        "repeatFile": "3",
        "ttsRate": "-2"
    }
    if OTP_CALLER_ID:
        params["callerId"] = OTP_CALLER_ID

    try:
        res = requests.get("https://www.call2all.co.il/ym/api/SendTTS", params=params, timeout=15)
        print(f"[OTP SendTTS] ל-{target_phone} קוד={otp_code} | תגובה: {res.text[:120]}", flush=True)
    except Exception as e:
        print(f"[OTP SendTTS ERROR] {e}", flush=True)

@app.api_route("/otp-play", methods=["GET", "POST"])
async def otp_play_endpoint(request: Request):
    params = dict(request.query_params)
    phone = params.get("ApiPhone", "").strip()
    code = params.get("code") or OTP_PENDING.get(phone, "")
    if not code:
        return Response(content="go_to_folder=hangup", media_type="text/plain; charset=utf-8")
    digits_spaced = " ".join(list(code))
    msg = f"קוד האימות שלך הוא {digits_spaced}. " * 3
    return Response(content=f"id_list_message=t-{clean_tts(msg)}&go_to_folder=hangup", media_type="text/plain; charset=utf-8")

def process_gabai_message(rec_path: str, caller_phone: str, user: Optional[dict], token: str):
    audio_bytes = download_audio_bytes_from_yemot(rec_path, token)
    transcription = transcribe_audio_file_from_yemot(rec_path, token) if audio_bytes else ""
    sender_name = get_user_name(user) if user else "מאזין לא רשום"
    sender_id = get_user_id(user) if user else caller_phone
    tzintuk_status = "רשום לצינתוק אישי" if (user and is_user_personal_tzintuk(user)) else "אינו רשום לצינתוק אישי"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    body_text = (
        f"התקבלה הודעה חדשה לגבאי במערכת המכירות\n"
        f"תאריך ושעה: {ts}\n"
        f"שם: {sender_name}\n"
        f"תעודת זהות / מזהה: {sender_id}\n"
        f"טלפון מחייג: {caller_phone}\n"
        f"סטטוס צינתוק אישי: {tzintuk_status}\n"
        f"נתיב בשלוחה 5: {rec_path}\n\n"
        f"תמלול אוטומטי:\n{transcription or 'לא זוהה טקסט / שמע מצורף'}\n"
    )

    if SMTP_USER and SMTP_PASS and GABAI_EMAIL:
        try:
            msg = EmailMessage()
            msg["Subject"] = f"הודעה חדשה לגבאי מאת {sender_name} ({caller_phone})"
            msg["From"] = SMTP_USER
            msg["To"] = GABAI_EMAIL
            msg.set_content(body_text)
            if audio_bytes:
                filename = os.path.basename(rec_path) or "gabai_message.wav"
                msg.add_attachment(audio_bytes, maintype="audio", subtype="wav", filename=filename)
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)
            print(f"[Gabai Email] נשלח בהצלחה אל {GABAI_EMAIL}", flush=True)
        except Exception as e:
            print(f"[Gabai Email ERROR] {e}", flush=True)

    post_to_apps_script({
        "type": "gabai_message",
        "timestamp": ts,
        "phone": caller_phone,
        "user_id": sender_id,
        "user_name": sender_name,
        "tzintuk_status": tzintuk_status,
        "audio_path": rec_path,
        "transcription": transcription,
        "gabai_email": GABAI_EMAIL,
        "audio_base64": base64.b64encode(audio_bytes).decode("ascii") if audio_bytes else ""
    })

# -------------------------------------------------------------------
# 4. פונקציות מענה לימות המשיח (הקראה רובוטית בלבד כרגע)
# -------------------------------------------------------------------
def build_sound(text: str, file_num: str = "") -> str:
    clean_text = clean_tts(text)
    if USE_AUDIO_FILES and file_num:
        return f"f-/{AUDIO_FOLDER}/{file_num}.t-{clean_text}"
    return f"t-{clean_text}"

def yemot_read(text: str, var_name: str, options: str = "no,1,1,7,No,no,no,*/,,,,,,no", file_num: str = "") -> Response:
    sound_str = build_sound(text, file_num)
    content = f"read={sound_str}={var_name},{options}&rate=3&tts_rate=3"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def yemot_read_record(text: str, var_name: str, record_folder: str = "", file_num: str = "") -> Response:
    sound_str = build_sound(text, file_num)
    if record_folder and record_folder != "/":
        content = f"read={sound_str}={var_name},no,record,{record_folder}"
    else:
        content = f"read={sound_str}={var_name},no,record"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def yemot_msg(text: str, file_num: str = "") -> Response:
    sound_str = build_sound(text, file_num)
    content = f"id_list_message={sound_str}&rate=3&tts_rate=3"
    return Response(content=content, media_type="text/plain; charset=utf-8")

# -------------------------------------------------------------------
# 5. מסכי תפריט ראשי, הזמנות, אזור אישי, הרשמה וקופה
# -------------------------------------------------------------------
WELCOME_TEXT = (
    "שלום וברוכים הבאים למערכת המכירות. "
    "להודעות הקישו 1, לכניסה למערכת ההזמנות הקישו 2, "
    "לאזור האישי הקישו 3, לרישום לצינתוקים כללי הקישו 4, "
    "להשארת הודעה לגבאי הקישו 5"
)

def show_welcome(session: dict, prefix: str = "") -> Response:
    session["step"] = "WELCOME"
    msg = f"{prefix}{WELCOME_TEXT}" if prefix else WELCOME_TEXT
    return yemot_read(msg, "welcome_choice", "no,1,1,7,No,no,no,*/,,,,,,no", "001")

def show_cities_menu(session: dict, target_step: str, var_name: str, prefix: str = "") -> Response:
    cities = CACHE["cities"]
    if not cities:
        if target_step == "REG_CITY":
            session["step"] = "REG_ADDRESS"
            return yemot_read_record("אנא אמרו בקול ברור את כתובת המגורים שלכם, רחוב ומספר בית ללא שם העיר, ולאחר מכן הקישו סולמית", "reg_address", "", "010")
        return show_update_field_step(session, "UPD_ADDR_MENU", prefix="לא הוגדרו ערים ברשימה, ")

    cities_text = "".join([f"ל{ct['city_name']} הקישו {i}, " for i, ct in enumerate(cities, 1)])
    max_d = max(1, len(str(len(cities))))
    session["step"] = target_step
    msg = f"{prefix}אנא בחרו את עיר המגורים שלכם. {cities_text}"
    return yemot_read(msg, var_name, f"no,{max_d},1,7,No,no,no,*/,,,,,,no", "029")

def check_abandoned_cart_or_proceed(session: dict) -> Response:
    user = session.get("user", {})
    user_id = get_user_id(user) or session.get("phone")
    if user_id and SAVED_CARTS.get(user_id):
        session["step"] = "RESTORE_CART_CHOICE"
        msg = "המערכת מזהה כי יש לך הזמנה פתוחה במערכת, להמשך קנייה זו הקישו 1, להתחלת קנייה חדשה הקישו 2"
        return yemot_read(msg, "restore_cart_choice", "no,1,1,7,No,no,no,*/,,,,,,no", "026")
    session["step"] = "MAIN_MENU"
    return show_categories(session)

def show_categories(session: dict, prefix: str = "") -> Response:
    cats = CACHE["categories"]
    if not cats:
        return yemot_msg("מצטערים, אין כרגע קטגוריות זמינות")

    cats_text = "".join([f"ל{c['category_name']} הקישו {i}, " for i, c in enumerate(cats, 1)])
    max_d = max(1, len(str(len(cats))))
    msg = f"{prefix}לתפריט ההזמנות: {cats_text} לבחירת מוצר לפי מקט הקישו 0. למעבר לתשלום בכל עת הקישו כוכבית"
    session["step"] = "MAIN_MENU"
    return yemot_read(msg, "cat_choice", f"no,{max_d},1,7,No,no,no,*/,,,,,,no", "017a")

def show_category_products_menu(session: dict, prefix: str = "") -> Response:
    cat = str(session.get("selected_cat", "")).strip()
    kashrut = str(session.get("selected_kashrut") or "").strip()

    filtered = [
        p for p in CACHE["products"]
        if str(p.get("category_name", "")).strip().lower() == cat.lower()
        and (not kashrut or str(p.get("kashrut", "")).strip().lower() == kashrut.lower())
    ]
    if not filtered:
        return show_categories(session, prefix="לא נמצאו מוצרים בקטגוריה זו, ")

    session["filtered_products"] = filtered
    prods_text = "".join([f"ל{p['name']} הקישו {i}, " for i, p in enumerate(filtered, 1)])
    max_d = max(1, len(str(len(filtered))))
    msg = f"{prefix}{prods_text} לבחירת מוצר לפי מקט הקישו 0, למעבר לתשלום בכל עת הקישו כוכבית"
    session["step"] = "PRODUCT_LIST_MENU"
    return yemot_read(msg, "prod_list_choice", f"no,{max_d},1,7,No,no,no,*/,,,,,,no")

def play_current_product(session: dict, prefix: str = "") -> Response:
    products = session.get("filtered_products", [])
    if not products:
        return show_categories(session, prefix="לא נמצאו מוצרים, ")

    idx = session.get("product_index", 0) % len(products)
    session["product_index"] = idx
    p = products[idx]

    p_name = clean_tts(p["name"])
    p_sku = clean_tts(p["sku"])
    effective_price = get_product_price_for_user(p, session.get("user"))
    p_price = format_price(effective_price)
    p_notes = clean_tts(p["notes"]) if p.get("notes") else ""

    notes_str = f" הערה: {p_notes}," if p_notes else ""
    msg = (
        f"{clean_tts(prefix)}מוצר {p_name}, מקט {p_sku}, "
        f"מחיר המוצר {p_price} שקלים,{notes_str} "
        f"להוספת המוצר לסל הקישו 1, למוצר הבא הקישו 2 או המתינו, למעבר לתשלום הקישו כוכבית"
    )
    sound_chain = f"t-{msg}"
    if USE_AUDIO_FILES:
        sound_chain = (
            f"{f't-{clean_tts(prefix)}.' if prefix else ''}"
            f"f-/{AUDIO_FOLDER}/022a.t-מוצר.t-{p_name}."
            f"f-/{AUDIO_FOLDER}/022b.t-מקט.t-{p_sku}."
            f"f-/{AUDIO_FOLDER}/022c.t-מחיר המוצר.n-{p_price}."
            f"f-/{AUDIO_FOLDER}/022d.t-שקלים."
            + (f"f-/{AUDIO_FOLDER}/022e.t-הערה.t-{p_notes}." if p_notes else "")
            + f"f-/{AUDIO_FOLDER}/022f.t-להוספת המוצר לסל הקישו 1, למוצר הבא הקישו 2 או המתינו, למעבר לתשלום הקישו כוכבית"
        )

    session["step"] = "PRODUCT_LOOP"
    options = "no,1,1,5,No,no,no,,,1,ok,TIMEOUT"
    return Response(content=f"read={sound_chain}=product_choice,{options}&rate=3&tts_rate=3", media_type="text/plain; charset=utf-8")

def initiate_checkout(session: dict) -> Response:
    cart = session.get("cart", [])
    if not cart:
        return show_categories(session, prefix="סל הקניות שלך ריק, ")

    cart_sum = sum(float(item["total"]) for item in cart)
    total_with_fee = cart_sum + 10
    total_str = format_price(total_with_fee)
    session["total_sum_with_fee"] = int(total_with_fee) if float(total_with_fee).is_integer() else round(total_with_fee, 2)
    session["step"] = "CONFIRM_CHECKOUT_FEE"

    part1 = "על כל קניה תחויבו בנוסף לתשלום הכולל סך של 10 שקלים דמי ניהול תחנה. הסכום לתשלום הינו"
    part2 = "שקלים. לאישור ומעבר לתשלום הקישו 1, לביטול ההזמנה הקישו 2"

    if USE_AUDIO_FILES:
        sound_chain = f"f-/{AUDIO_FOLDER}/023a.t-{clean_tts(part1)}.n-{total_str}.f-/{AUDIO_FOLDER}/023b.t-{clean_tts(part2)}"
    else:
        sound_chain = f"t-{clean_tts(part1)}.n-{total_str}.t-{clean_tts(part2)}"

    return Response(content=f"read={sound_chain}=checkout_confirm_choice,no,1,1,7,No,no,no,*/,,,,,,no&rate=3&tts_rate=3", media_type="text/plain; charset=utf-8")

def finish_checkout(session: dict, background_tasks: BackgroundTasks) -> Response:
    cart = session.get("cart", [])
    call_id = session.get("call_id")
    phone = session.get("phone", "")
    if not cart:
        return yemot_msg("סל הקניות שלך ריק, תודה ולהתראות", "019")

    cart_sum = sum(float(item["total"]) for item in cart)
    total_sum = session.get("total_sum_with_fee") or (cart_sum + 10)
    total_str = format_price(total_sum)

    user = session.get("user") or {}
    user_id = get_user_id(user) or phone
    if user_id and user_id in SAVED_CARTS:
        del SAVED_CARTS[user_id]

    log_step(call_id, phone, "CHECKOUT", "1", f"סליקה בנדרים פלוס בסך {total_str} ש\"ח")
    background_tasks.add_task(log_transaction_to_sheet, dict(session))
    background_tasks.add_task(log_general_event, call_id, phone, "הזמנה הושלמה - מעבר לסליקה", f"סה\"כ {total_str} ש\"ח")

    if call_id in SESSIONS:
        del SESSIONS[call_id]

    part1 = "סך הכל לתשלום"
    part2 = "שקלים מועברים כעת לסליקת אשראי"
    if USE_AUDIO_FILES:
        msg_chain = f"f-/{AUDIO_FOLDER}/025a.t-{clean_tts(part1)}.n-{total_str}.f-/{AUDIO_FOLDER}/025b.t-{clean_tts(part2)}"
    else:
        msg_chain = f"t-{clean_tts(part1)}.n-{total_str}.t-{clean_tts(part2)}"

    credit_card_cmd = f"credit_card={CREDIT_CARD_PROVIDER},{total_str},{CREDIT_CARD_MAX_PAYMENTS},{CREDIT_CARD_CURRENCY},,,,{CREDIT_CARD_REGISTER_NO}"
    return Response(content=f"id_list_message={msg_chain}&{credit_card_cmd}", media_type="text/plain; charset=utf-8")

def show_personal_area_menu(session: dict, prefix: str = "") -> Response:
    session["step"] = "PERSONAL_AREA_MENU"
    msg = (
        f"{prefix}לאזור האישי. לעדכון פרטים הקישו 1, להיסטוריית עסקאות הקישו 2, "
        "להודעות מהגבאי הקישו 3, לרישום ראשוני הקישו 4, לחזרה לתפריט הראשי הקישו 9"
    )
    return yemot_read(msg, "personal_choice", "no,1,1,7,No,no,no,*/,,,,,,no", "014d")

def show_update_field_step(session: dict, field_step: str, prefix: str = "") -> Response:
    user = session.get("user") or {}
    session["step"] = field_step

    if field_step == "UPD_NAME_MENU":
        val = clean_tts(get_user_name(user)) or "לא עודכן"
        return yemot_read(f"{prefix}שם: {val}. לעדכון הקישו 1, להמשך הקישו 2", "upd_name_choice", "no,1,1,7,No,no,no,*/,,,,,,no")
    if field_step == "UPD_CITY_MENU":
        val = clean_tts(get_user_city(user)) or "לא עודכנה"
        return yemot_read(f"{prefix}עיר: {val}. לעדכון הקישו 1, להמשך הקישו 2", "upd_city_choice", "no,1,1,7,No,no,no,*/,,,,,,no")
    if field_step == "UPD_ADDR_MENU":
        val = clean_tts(get_user_address(user)) or "לא עודכנה"
        return yemot_read(f"{prefix}כתובת: {val}. לעדכון הקישו 1, להמשך הקישו 2", "upd_addr_choice", "no,1,1,7,No,no,no,*/,,,,,,no")
    if field_step == "UPD_PHONE_MENU":
        val = clean_tts(get_user_phone(user)) or "לא עודכן"
        return yemot_read(f"{prefix}טלפון: {val}. לעדכון הקישו 1, להמשך הקישו 2", "upd_phone_choice", "no,1,1,7,No,no,no,*/,,,,,,no")
    if field_step == "UPD_COMMUNITY_MENU":
        val = clean_tts(get_user_community(user)) or "לא עודכן"
        return yemot_read(f"{prefix}קוד קהילה: {val}. לעדכון הקישו 1, להמשך הקישו 2", "upd_comm_choice", "no,1,1,7,No,no,no,*/,,,,,,no")
    if field_step == "UPD_PASS_MENU":
        val = clean_tts(get_user_password(user)) or "לא הוגדרה"
        return yemot_read(f"{prefix}סיסמא: {val}. לעדכון הקישו 1, להמשך הקישו 2", "upd_pass_choice", "no,1,1,7,No,no,no,*/,,,,,,no")
    if field_step == "UPD_TZINTUK_MENU":
        status = "רשום" if is_user_personal_tzintuk(user) else "אינך רשום"
        return yemot_read(f"{prefix}סטטוס קבלת צינתוק אישי: {status}. לרישום לקבלת צינתוק אישי הקישו 1, לסיום וחזרה לאזור האישי הקישו 2", "upd_tzintuk_choice", "no,1,1,7,No,no,no,*/,,,,,,no")
    return show_personal_area_menu(session)

def show_tx_history_list(session: dict, prefix: str = "") -> Response:
    user = session.get("user") or {}
    user_id = get_user_id(user)
    user_phone = get_user_phone(user)

    user_txs = [t for t in CACHE["transactions"] if str(t.get("user_identifier", "")).strip() in [user_id, user_phone]]
    if not user_txs:
        user_txs = list(CACHE["transactions"])

    last_10 = list(reversed(user_txs))[:10]
    if not last_10:
        return show_personal_area_menu(session, prefix="לא נמצאו עסקאות קודמות במערכת, ")

    session["tx_list"] = last_10
    session["step"] = "TX_HISTORY_LIST"

    txt = f"{prefix}להלן 10 העסקאות האחרונות. "
    for i, tx in enumerate(last_10, 1):
        amt = format_price(tx.get("total_amount", "0"))
        dt = clean_tts(tx.get("timestamp", ""))
        txt += f"לעסקה מתאריך {dt} בסכום {amt} שקלים הקישו {i}, "
    txt += "לחזרה הקישו כוכבית"

    max_d = max(1, len(str(len(last_10))))
    return yemot_read(txt, "tx_list_choice", f"no,{max_d},1,7,No,no,no,*/,,,,,,no")

def start_registration(session: dict, return_to: str = "MAIN_MENU", prefill_id: str = "") -> Response:
    session["reg_data"] = {}
    session["reg_return_to"] = return_to
    if prefill_id:
        session["reg_data"]["id_number"] = prefill_id
        session["step"] = "REG_PHONE"
        msg = "עוברים לתהליך הרשמה. מספר תעודת הזהות נקלט. אנא הקישו את מספר הטלפון שלכם בן 9 עד 10 ספרות ולאחר מכן הקישו סולמית"
        return yemot_read(msg, "reg_phone", "no,10,9,7,Digits,yes,no,*/", "009")

    session["step"] = "REG_ID"
    msg = "תהליך הרשמה. אנא הקישו את מספר תעודת הזהות שלכם בן 8 עד 9 ספרות ולאחר מכן הקישו סולמית"
    return yemot_read(msg, "reg_id", "no,9,8,7,Digits,yes,no,*/", "007")

def start_forgot_password(session: dict, background_tasks: BackgroundTasks) -> Response:
    user = session.get("pending_login_user") or session.get("user")
    if not user:
        session["step"] = "LOGIN_ID"
        return yemot_read("לא זוהה חשבון. אנא הקישו את מספר תעודת הזהות שלכם ולאחר מכן הקישו סולמית", "login_id", "no,9,8,7,Digits,yes,no,*/", "003")

    target_phone = get_user_phone(user) or session.get("phone", "")
    otp_code = f"{random.randint(100000, 999999)}"
    session["forgot_otp"] = otp_code
    session["step"] = "FORGOT_OTP_INPUT"

    background_tasks.add_task(send_otp_tzintuk_call, target_phone, otp_code)
    background_tasks.add_task(log_general_event, session.get("call_id", ""), session.get("phone", ""), "שכחתי סיסמא", f"נשלח קוד OTP ל-{target_phone}")

    msg = "שיחת קוד אימות נשלחה כעת למספר הטלפון הרשום בחשבונך. לאחר קבלת הקוד בן 6 הספרות הקישו אותו כאן"
    return yemot_read(msg, "forgot_otp_input", "no,6,6,15,No,no,no,*/,,,,,,no")

# -------------------------------------------------------------------
# 6. Webhook ראשי
# -------------------------------------------------------------------
@app.api_route("/", methods=["GET", "POST", "HEAD"])
async def ivr_handler(request: Request, background_tasks: BackgroundTasks):
    if request.method == "HEAD":
        return Response(content="OK", media_type="text/plain")

    call_id = "default_session"
    try:
        params = dict(request.query_params)
        if request.method == "POST":
            form_data = await request.form()
            params.update(dict(form_data))

        call_id = params.get("ApiCallId") or params.get("phone") or "default_session"
        phone = params.get("ApiPhone", "").strip()
        token = params.get("token") or YEMOT_TOKEN

        if call_id not in SESSIONS:
            SESSIONS[call_id] = {
                "step": "WELCOME",
                "user": None,
                "orders_authenticated": False,
                "pending_login_user": None,
                "pending_unauth_id": "",
                "cart": [],
                "selected_cat": None,
                "selected_kashrut": None,
                "filtered_products": [],
                "product_index": 0,
                "call_id": call_id,
                "phone": phone,
                "reg_data": {},
                "reg_return_to": "MAIN_MENU",
                "auth_target": "MAIN_MENU"
            }
            log_step(call_id, phone, "NEW_CALL", "", "פתיחת שיחה חדשה ➔ תפריט ראשי")
            background_tasks.add_task(log_general_event, call_id, phone, "כניסה לשיחה", "התחלת שיחה חדשה")

        session = SESSIONS[call_id]
        step = session["step"]

        # ---------------------------------------------------------
        # טיפול בחזרה משלוחה /C (ללא שימוש בפרמטרים ישנים מה-URL)
        # ---------------------------------------------------------
        if step == "REG_RETURN_FROM_TZINTUK":
            session["reg_data"]["personal_tzintuk"] = "TRUE"
            session["step"] = "REG_PASSWORD"
            log_step(call_id, phone, step, "", "חזר משלוחה /C ➔ בקשת קוד אישי בן 6 ספרות")
            return yemot_read("הרישום לצינתוקים האישיים הושלם. כעת אנא הקישו קוד סיסמא אישי בן 6 ספרות ולאחר מכן הקישו סולמית", "reg_password", "no,6,6,7,Digits,yes,no,*/")

        if step == "UPD_RETURN_FROM_TZINTUK":
            log_step(call_id, phone, step, "", "חזר משלוחה /C ➔ חזרה לאזור אישי")
            return show_personal_area_menu(session, prefix="נרשמתם בהצלחה לצינתוקים אישיים, ")

        if step == "GABAI_RETURN_FROM_TZINTUK":
            session["step"] = "GABAI_RECORD_MSG"
            log_step(call_id, phone, step, "", "חזר משלוחה /C ➔ מעבר להקלטת הודעה לגבאי")
            return yemot_read_record("נרשמתם לצינתוק אישי. כעת אנא השאירו את הודעתכם לגבאי ולאחר מכן הקישו סולמית", "gabai_msg", "/5")

        # שליפת קלט נוכחי מהבקשה
        raw_user_input = ""
        expected_keys = STEP_PARAM_MAP.get(step, [])
        for key in expected_keys:
            if params.get(key) is not None and str(params.get(key)).strip() != "":
                raw_user_input = str(params.get(key)).strip()
                break

        if not raw_user_input and step != "WELCOME":
            for k, v in params.items():
                if not k.startswith("Api") and v is not None and str(v).strip() != "":
                    raw_user_input = str(v).strip()
                    break

        user_input = clean_input(raw_user_input)

        # ---------------------------------------------------------
        # תפריט ראשי
        # ---------------------------------------------------------
        if step == "WELCOME":
            if not user_input:
                log_step(call_id, phone, step, "", "השמעת תפריט ראשי")
                return show_welcome(session)

            user_obj = session.get("user") or CACHE["users"].get(phone) or {}
            user_id = get_user_id(user_obj) or phone
            is_vip = (phone in ALLOWED_PHONES_WHEN_CLOSED) or (user_id in ALLOWED_PHONES_WHEN_CLOSED)

            if user_input in ["1", "2", "3", "4", "5"] and not OPEN_BRANCHES.get(user_input, True) and not is_vip:
                log_step(call_id, phone, step, user_input, "שלוחה סגורה (אין הרשאת VIP)")
                return show_welcome(session, prefix="שלוחה זו סגורה כעת, ")

            if user_input == "1":
                log_step(call_id, phone, step, "1", "מעבר לשלוחה /1 (הודעות)")
                return Response(content="go_to_folder=/1", media_type="text/plain; charset=utf-8")

            elif user_input == "2":
                if session.get("orders_authenticated") and session.get("user"):
                    log_step(call_id, phone, step, "2", "כבר מזוהה בשיחה ➔ כניסה להזמנות")
                    return check_abandoned_cart_or_proceed(session)
                session["auth_target"] = "MAIN_MENU"
                session["step"] = "LOGIN_ID"
                log_step(call_id, phone, step, "2", "בקשת ת.ז לכניסה להזמנות")
                return yemot_read("לכניסה למערכת ההזמנות אנא הקישו את מספר תעודת הזהות שלכם בן 8 עד 9 ספרות ולאחר מכן הקישו סולמית", "login_id", "no,9,8,7,Digits,yes,no,*/", "003")

            elif user_input == "3":
                log_step(call_id, phone, step, "3", "מעבר לאזור אישי")
                return show_personal_area_menu(session)

            elif user_input == "4":
                log_step(call_id, phone, step, "4", "מעבר לשלוחה /4 (צינתוקים כללי)")
                return Response(content="go_to_folder=/4", media_type="text/plain; charset=utf-8")

            elif user_input == "5":
                user = session.get("user") or CACHE["users"].get(phone)
                if user:
                    session["user"] = user
                    if is_user_personal_tzintuk(user):
                        session["step"] = "GABAI_RECORD_MSG"
                        log_step(call_id, phone, step, "5", "רשום לצינתוק אישי ➔ הקלטה לגבאי (/5)")
                        return yemot_read_record("אנא השאירו את הודעתכם לגבאי ולאחר מכן הקישו סולמית", "gabai_msg", "/5")
                    session["step"] = "GABAI_TZINTUK_PROMPT"
                    log_step(call_id, phone, step, "5", "לא רשום לצינתוק אישי ➔ הצעת רישום לפני גבאי")
                    return yemot_read("שימו לב, אינכם רשומים באזור האישי לקבלת צינתוק אישי בעת קבלת תשובה. לרישום לצינתוק אישי הקישו 1, להמשך השארת הודעה לגבאי הקישו 2", "gabai_tzintuk_choice", "no,1,1,7,No,no,no,*/,,,,,,no")
                session["step"] = "GABAI_AUTH_ID"
                log_step(call_id, phone, step, "5", "לא זוהה טלפונית ➔ בקשת ת.ז או כוכבית לפני גבאי")
                return yemot_read("להשארת הודעה לגבאי אנא הקישו את מספר תעודת הזהות שלכם לבדיקת רישום לצינתוק אישי, או הקישו כוכבית להשארת הודעה ישירה", "gabai_auth_id", "no,10,1,7,No,no,no,*/")

            else:
                log_step(call_id, phone, step, user_input, "הקשה שגויה בתפריט ראשי")
                return show_welcome(session, prefix="הקשה שגויה, ")

        # ---------------------------------------------------------
        # התחברות להזמנות ולאזור אישי
        # ---------------------------------------------------------
        elif step == "LOGIN_ID":
            if not user_input:
                log_step(call_id, phone, step, "", "קלט ריק ➔ בקשת ת.ז חוזרת")
                return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם בן 8 עד 9 ספרות ולאחר מכן הקישו סולמית", "login_id", "no,9,8,7,Digits,yes,no,*/", "003")

            if user_input in CACHE["users"]:
                user = CACHE["users"][user_input]
                session["pending_login_user"] = user
                saved_pass = get_user_password(user)
                if not saved_pass:
                    session["step"] = "FORGOT_NEW_PASS"
                    log_step(call_id, phone, step, user_input, "נמצא משתמש ללא סיסמא ➔ הגדרת סיסמא חדשה")
                    return yemot_read("טרם הוגדרה סיסמא לחשבונך. אנא בחרו סיסמא חדשה בת 6 עד 10 ספרות ולאחר מכן הקישו סולמית", "forgot_new_pass", "no,10,6,7,Digits,yes,no,*/")

                session["step"] = "LOGIN_PASS"
                log_step(call_id, phone, step, user_input, "נמצא משתמש ➔ בקשת סיסמא")
                return yemot_read("אנא הקישו את הסיסמא שלכם בת 6 עד 10 ספרות ולאחר מכן הקישו סולמית. אם שכחתם את הסיסמא הקישו כוכבית", "login_pass", "no,10,6,7,Digits,yes,no,*/")
            else:
                session["pending_unauth_id"] = user_input
                session["step"] = "LOGIN_ID_NOT_FOUND"
                log_step(call_id, phone, step, user_input, "ת.ז לא נמצאה ➔ בחירה: מספר אחר (1) או רישום (2)")
                return yemot_read("מספר תעודת הזהות אינו מזוהה במערכת. להקשת מספר אחר הקישו 1, למעבר לרישום הקישו 2", "login_not_found_choice", "no,1,1,7,No,no,no,*/,,,,,,no")

        elif step == "LOGIN_ID_NOT_FOUND":
            if user_input == "1":
                session["step"] = "LOGIN_ID"
                log_step(call_id, phone, step, "1", "חזרה להקשת ת.ז אחרת")
                return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם בן 8 עד 9 ספרות ולאחר מכן הקישו סולמית", "login_id", "no,9,8,7,Digits,yes,no,*/", "003")
            elif user_input == "2":
                target = session.get("auth_target", "MAIN_MENU")
                reg_return = "PERSONAL_AREA_MENU" if target in ["PERSONAL_UPDATE", "TX_HISTORY"] else "MAIN_MENU"
                prefill_id = session.get("pending_unauth_id", "")
                log_step(call_id, phone, step, "2", f"מעבר לרישום עם ת.ז מוזנת אוטומטית ({prefill_id}) ➔ טלפון")
                return start_registration(session, return_to=reg_return, prefill_id=prefill_id)
            else:
                log_step(call_id, phone, step, user_input, "הקשה שגויה ➔ בקשה חוזרת (1 אחר / 2 רישום)")
                return yemot_read("הקשה שגויה. להקשת מספר אחר הקישו 1, למעבר לרישום הקישו 2", "login_not_found_choice", "no,1,1,7,No,no,no,*/,,,,,,no")

        elif step == "LOGIN_PASS":
            if user_input == "*":
                log_step(call_id, phone, step, "*", "בקשת שכחתי סיסמא")
                return start_forgot_password(session, background_tasks)

            user = session.get("pending_login_user")
            if not user:
                session["step"] = "LOGIN_ID"
                return yemot_read("אנא הקישו תעודת זהות ולאחר מכן סולמית", "login_id", "no,9,8,7,Digits,yes,no,*/", "003")

            if user_input == get_user_password(user):
                session["user"] = user
                session["orders_authenticated"] = True
                session["pending_login_user"] = None
                log_step(call_id, phone, step, "******", f"סיסמא תקינה (ת.ז {get_user_id(user)}) ➔ כניסה")
                background_tasks.add_task(log_general_event, call_id, phone, "כניסה מוצלחת", f"התחבר ת.ז {get_user_id(user)}")

                target = session.get("auth_target", "MAIN_MENU")
                if target == "PERSONAL_UPDATE":
                    return show_update_field_step(session, "UPD_NAME_MENU")
                elif target == "TX_HISTORY":
                    return show_tx_history_list(session)
                return check_abandoned_cart_or_proceed(session)
            else:
                session["step"] = "LOGIN_WRONG_PASS"
                log_step(call_id, phone, step, "******", "סיסמא שגויה ➔ ניסיון נוסף (1) או שכחתי (2)")
                return yemot_read("הסיסמא שהוקשה שגויה. לניסיון הקשה נוסף הקישו 1, לשכחתי סיסמא ואיפוס הקישו 2", "wrong_pass_choice", "no,1,1,7,No,no,no,*/,,,,,,no")

        elif step == "LOGIN_WRONG_PASS":
            if user_input == "1":
                session["step"] = "LOGIN_PASS"
                log_step(call_id, phone, step, "1", "ניסיון סיסמא חוזר")
                return yemot_read("אנא הקישו את הסיסמא שלכם בת 6 עד 10 ספרות ולאחר מכן הקישו סולמית", "login_pass", "no,10,6,7,Digits,yes,no,*/")
            elif user_input == "2":
                log_step(call_id, phone, step, "2", "מעבר לשכחתי סיסמא")
                return start_forgot_password(session, background_tasks)
            else:
                return yemot_read("הקשה שגויה, לניסיון נוסף הקישו 1, לשכחתי סיסמא הקישו 2", "wrong_pass_choice", "no,1,1,7,No,no,no,*/,,,,,,no")

        # ---------------------------------------------------------
        # שכחתי סיסמא
        # ---------------------------------------------------------
        elif step == "FORGOT_OTP_INPUT":
            expected = session.get("forgot_otp", "")
            if user_input == expected and expected:
                session["step"] = "FORGOT_NEW_PASS"
                log_step(call_id, phone, step, user_input, "קוד OTP אומת ➔ הזנת סיסמא חדשה")
                return yemot_read("הקוד אומת בהצלחה. אנא הקישו סיסמא חדשה בת 6 עד 10 ספרות ולאחר מכן הקישו סולמית", "forgot_new_pass", "no,10,6,7,Digits,yes,no,*/")
            else:
                log_step(call_id, phone, step, user_input, "קוד OTP שגוי")
                return yemot_read("קוד האימות שגוי. אנא הקישו שוב את 6 הספרות שקיבלתם בשיחה", "forgot_otp_input", "no,6,6,15,No,no,no,*/,,,,,,no")

        elif step == "FORGOT_NEW_PASS":
            if not user_input or len(user_input) < 6 or len(user_input) > 10:
                log_step(call_id, phone, step, user_input, "סיסמא חדשה לא באורך 6-10")
                return yemot_read("סיסמא חייבת להיות בת 6 עד 10 ספרות, אנא הקישו שנית", "forgot_new_pass", "no,10,6,7,Digits,yes,no,*/")

            user = session.get("pending_login_user") or session.get("user")
            if user:
                user["password"] = user_input
                user["סיסמא"] = user_input
                sync_user_in_cache(user)
                session["user"] = user
                session["orders_authenticated"] = True
                session["pending_login_user"] = None
                background_tasks.add_task(update_user_in_sheet, dict(user))
                background_tasks.add_task(log_general_event, call_id, phone, "איפוס סיסמא", f"סיסמא עודכנה עבור {get_user_id(user)}")

            log_step(call_id, phone, step, "******", "סיסמא חדשה נשמרה בהצלחה")
            target = session.get("auth_target", "MAIN_MENU")
            if target == "PERSONAL_UPDATE":
                return show_update_field_step(session, "UPD_NAME_MENU", prefix="הסיסמא עודכנה בהצלחה, ")
            elif target == "TX_HISTORY":
                return show_tx_history_list(session, prefix="הסיסמא עודכנה בהצלחה, ")
            return show_categories(session, prefix="הסיסמא עודכנה בהצלחה, ")

        # ---------------------------------------------------------
        # תהליך רישום:
        # ת.ז -> טלפון -> שם -> עיר -> כתובת ללא עיר -> קוד קהילה (*# לדילוג) -> צינתוק אישי /C -> קוד 6 ספרות -> שמירה
        # ---------------------------------------------------------
        elif step == "REG_ID":
            if not user_input or len(user_input) < 8 or len(user_input) > 9:
                log_step(call_id, phone, step, user_input, "ת.ז לא תקינה")
                return yemot_read("אנא הקישו תעודת זהות תקינה בת 8 עד 9 ספרות ולאחר מכן הקישו סולמית", "reg_id", "no,9,8,7,Digits,yes,no,*/", "007")
            if user_input in CACHE["users"]:
                log_step(call_id, phone, step, user_input, "ת.ז כבר רשומה במערכת")
                return yemot_read("מספר תעודת זהות זה כבר רשום במערכת, אנא הקישו מספר תעודת זהות אחר", "reg_id", "no,9,8,7,Digits,yes,no,*/", "008")

            session["reg_data"]["id_number"] = user_input
            session["step"] = "REG_PHONE"
            log_step(call_id, phone, step, user_input, "ת.ז נקלטה ➔ בקשת טלפון")
            return yemot_read("אנא הקישו את מספר הטלפון שלכם בן 9 עד 10 ספרות ולאחר מכן הקישו סולמית", "reg_phone", "no,10,9,7,Digits,yes,no,*/", "009")

        elif step == "REG_PHONE":
            if not user_input or len(user_input) < 9 or len(user_input) > 10:
                log_step(call_id, phone, step, user_input, "טלפון לא תקין")
                return yemot_read("אנא הקישו מספר טלפון תקין בן 9 עד 10 ספרות ולאחר מכן הקישו סולמית", "reg_phone", "no,10,9,7,Digits,yes,no,*/", "009")

            session["reg_data"]["phone"] = user_input
            session["step"] = "REG_NAME"
            log_step(call_id, phone, step, user_input, "טלפון נקלט ➔ הקלטת שם")
            return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "", "005")

        elif step == "REG_NAME":
            if not raw_user_input:
                return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "", "005")

            transcribed_text = transcribe_audio_file_from_yemot(raw_user_input, token)
            if not transcribed_text:
                log_step(call_id, phone, step, raw_user_input, "תמלול שם נכשל ➔ הקלטה חוזרת")
                return yemot_read_record("לא הצלחנו לפענח את ההקלטה, אנא אמרו שוב בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "", "006")

            session["reg_data"]["temp_name"] = transcribed_text
            session["step"] = "REG_NAME_CONFIRM"
            log_step(call_id, phone, step, transcribed_text, "שם תומלל ➔ בקשת אישור שם")
            clean_name = clean_tts(transcribed_text)
            return yemot_read(f"השם שנקלט הוא {clean_name}. לאישור הקישו 1, להקלטה מחדש הקישו 2", "reg_name_confirm_choice", "no,1,1,7,No,no,no,*/,,,,,,no")

        elif step == "REG_NAME_CONFIRM":
            if user_input == "1":
                session["reg_data"]["first_name"] = session["reg_data"].get("temp_name", "")
                log_step(call_id, phone, step, "1", "שם אושר ➔ תפריט ערים")
                return show_cities_menu(session, "REG_CITY", "reg_city")
            elif user_input == "2":
                session["step"] = "REG_NAME"
                log_step(call_id, phone, step, "2", "הקלטת שם מחדש")
                return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "", "005")
            else:
                clean_name = clean_tts(session["reg_data"].get("temp_name", ""))
                return yemot_read(f"הקשה שגויה. השם שנקלט הוא {clean_name}. לאישור הקישו 1, להקלטה מחדש הקישו 2", "reg_name_confirm_choice", "no,1,1,7,No,no,no,*/,,,,,,no")

        elif step == "REG_CITY":
            cities = CACHE["cities"]
            try:
                idx = int(user_input) - 1
                if 0 <= idx < len(cities):
                    chosen_city = cities[idx]["city_name"]
                    session["reg_data"]["city"] = chosen_city
                    session["step"] = "REG_ADDRESS"
                    log_step(call_id, phone, step, user_input, f"נבחרה עיר '{chosen_city}' ➔ הקלטת רחוב ומספר בית")
                    return yemot_read_record(f"נבחרה העיר {clean_tts(chosen_city)}. כעת אנא אמרו בקול ברור את הרחוב ומספר הבית בלבד ללא שם העיר ולאחר מכן הקישו סולמית", "reg_address", "", "010")
                return show_cities_menu(session, "REG_CITY", "reg_city", prefix="הקשה שגויה, ")
            except ValueError:
                return show_cities_menu(session, "REG_CITY", "reg_city", prefix="הקשה שגויה, ")

        elif step == "REG_ADDRESS":
            if not raw_user_input:
                return yemot_read_record("אנא אמרו בקול ברור את הרחוב ומספר הבית בלבד ללא שם העיר ולאחר מכן הקישו סולמית", "reg_address", "", "010")

            transcribed_text = transcribe_audio_file_from_yemot(raw_user_input, token)
            if not transcribed_text:
                log_step(call_id, phone, step, raw_user_input, "תמלול כתובת נכשל ➔ הקלטה חוזרת")
                return yemot_read_record("לא הצלחנו לפענח את ההקלטה, אנא אמרו שוב בקול ברור את הרחוב ומספר הבית ללא שם העיר ולאחר מכן הקישו סולמית", "reg_address", "", "011")

            session["reg_data"]["temp_address"] = transcribed_text
            session["step"] = "REG_ADDRESS_CONFIRM"
            log_step(call_id, phone, step, transcribed_text, "כתובת תומללה ➔ בקשת אישור כתובת")
            clean_addr = clean_tts(transcribed_text)
            return yemot_read(f"הכתובת שנקלטה היא {clean_addr}. לאישור הקישו 1, להקלטה מחדש הקישו 2", "reg_address_confirm_choice", "no,1,1,7,No,no,no,*/,,,,,,no")

        elif step == "REG_ADDRESS_CONFIRM":
            if user_input == "1":
                session["reg_data"]["address"] = session["reg_data"].get("temp_address", "")
                session["step"] = "REG_COMMUNITY_CODE"
                log_step(call_id, phone, step, "1", "כתובת אושרה ➔ בקשת קוד קהילה (*# לדילוג)")
                return yemot_read("אנא הקישו את קוד הקהילה שלכם בן 6 ספרות ולאחר מכן הקישו סולמית. לדילוג הקישו כוכבית סולמית", "reg_community_code", "no,6,1,7,Digits,yes,no,*/", "012")
            elif user_input == "2":
                session["step"] = "REG_ADDRESS"
                log_step(call_id, phone, step, "2", "הקלטת כתובת מחדש")
                return yemot_read_record("אנא אמרו בקול ברור את הרחוב ומספר הבית בלבד ללא שם העיר ולאחר מכן הקישו סולמית", "reg_address", "", "010")
            else:
                clean_addr = clean_tts(session["reg_data"].get("temp_address", ""))
                return yemot_read(f"הקשה שגויה. הכתובת שנקלטה היא {clean_addr}. לאישור הקישו 1, להקלטה מחדש הקישו 2", "reg_address_confirm_choice", "no,1,1,7,No,no,no,*/,,,,,,no")

        elif step == "REG_COMMUNITY_CODE":
            if user_input in ["*", "*#", "0", ""]:
                community_code = ""
                log_step(call_id, phone, step, raw_user_input or "*", "דילוג על קוד קהילה (ריק)")
            elif len(user_input) == 6 and user_input.isdigit():
                community_code = user_input
                log_step(call_id, phone, step, community_code, "קוד קהילה נקלט")
            else:
                log_step(call_id, phone, step, user_input, "קוד קהילה לא תקין")
                return yemot_read("קוד קהילה חייב להיות בן 6 ספרות, או הקישו כוכבית סולמית לדילוג", "reg_community_code", "no,6,1,7,Digits,yes,no,*/", "012")

            session["reg_data"]["community_code"] = community_code

            # הכנת שלוחה C לפי מספר הטלפון של המאזין והעברה אליה
            tzintuk_list_name = phone or session["reg_data"].get("phone", "")
            session["reg_data"]["tzintuk_list"] = tzintuk_list_name
            update_yemot_tzintuk_extension(tzintuk_list_name, end_goto="/")
            session["step"] = "REG_RETURN_FROM_TZINTUK"
            log_step(call_id, phone, step, community_code or "[ריק]", f"מעבר לשלוחה /C לרישום צינתוק אישי (רשימה: {tzintuk_list_name})")
            return Response(content="go_to_folder=/C", media_type="text/plain; charset=utf-8")

        elif step == "REG_PASSWORD":
            if not user_input or not user_input.isdigit() or len(user_input) != 6:
                log_step(call_id, phone, step, user_input, "קוד לא תקין (נדרשות 6 ספרות)")
                return yemot_read("הקוד חייב להיות בן 6 ספרות בלבד, אנא הקישו שוב ולאחר מכן סולמית", "reg_password", "no,6,6,7,Digits,yes,no,*/")

            session["reg_data"]["password"] = user_input
            user_info = session["reg_data"]
            new_user = {
                "id_number": user_info.get("id_number", ""),
                "phone": user_info.get("phone", ""),
                "first_name": user_info.get("first_name", ""),
                "last_name": "",
                "city": user_info.get("city", ""),
                "address": user_info.get("address", ""),
                "community_code": user_info.get("community_code", ""),
                "password": user_input,
                "personal_tzintuk": user_info.get("personal_tzintuk", "TRUE"),
                "is_active": "TRUE"
            }
            sync_user_in_cache(new_user)
            session["user"] = new_user
            session["orders_authenticated"] = True
            background_tasks.add_task(save_new_user_to_sheet, dict(new_user))
            background_tasks.add_task(log_general_event, call_id, phone, "הרשמה הושלמה", f"נרשם: {new_user['first_name']} | עיר: {new_user['city']} | צינתוק: {new_user['personal_tzintuk']}")

            log_step(call_id, phone, step, "******", f"משתמש חדש נשמר ({new_user['id_number']}) ➔ תפריט סיום הרשמה")
            ret = session.get("reg_return_to", "MAIN_MENU")
            if ret == "PERSONAL_AREA_MENU":
                return show_personal_area_menu(session, prefix="הרישום הושלם בהצלחה, ")

            session["step"] = "REG_END_MENU"
            return yemot_read("הרישום הושלם בהצלחה. למעבר לתפריט ההזמנות הקישו 1, לחזרה לתפריט הראשי הקישו 2", "reg_end_choice", "no,1,1,7,No,no,no,*/,,,,,,no", "013")

        elif step == "REG_END_MENU":
            if user_input == "1":
                log_step(call_id, phone, step, "1", "מעבר לתפריט ההזמנות")
                return show_categories(session)
            log_step(call_id, phone, step, user_input, "חזרה לתפריט ראשי")
            return show_welcome(session)

        # ---------------------------------------------------------
        # שחזור סל פתוח + תפריט ההזמנות
        # ---------------------------------------------------------
        elif step == "RESTORE_CART_CHOICE":
            user = session.get("user") or {}
            user_id = get_user_id(user) or phone
            if user_input == "1":
                session["cart"] = SAVED_CARTS.get(user_id, [])
                log_step(call_id, phone, step, "1", "שחזור סל פתוח")
                return show_categories(session, prefix="ממשיכים את ההזמנה הקודמת, ")
            elif user_input == "2":
                session["cart"] = []
                if user_id in SAVED_CARTS:
                    del SAVED_CARTS[user_id]
                log_step(call_id, phone, step, "2", "איפוס סל והתחלת קנייה חדשה")
                return show_categories(session, prefix="מתחילים הזמנה חדשה, ")
            else:
                return yemot_read("הקשה שגויה, להמשך קנייה קודמת הקישו 1, לקנייה חדשה הקישו 2", "restore_cart_choice", "no,1,1,7,No,no,no,*/,,,,,,no", "026")

        elif step == "MAIN_MENU":
            if user_input == "*":
                log_step(call_id, phone, step, "*", "מעבר לתשלום מהקטגוריות")
                return initiate_checkout(session)
            if user_input == "0":
                session["step"] = "SKU_INPUT"
                log_step(call_id, phone, step, "0", "בחירת מוצר לפי מק\"ט (4 ספרות)")
                return yemot_read("אנא הקישו את מספר המקט בן 4 ספרות ולאחר מכן הקישו סולמית", "sku_input", "no,4,4,7,Digits,yes,no,*/")

            cats = CACHE["categories"]
            try:
                choice_idx = int(user_input) - 1
                if 0 <= choice_idx < len(cats):
                    selected_cat = cats[choice_idx]
                    session["selected_cat"] = selected_cat["category_name"]
                    kashruts = [k.strip() for k in str(selected_cat.get("kashruts", "")).split(",") if k.strip()]
                    session["available_kashruts"] = kashruts
                    if not kashruts:
                        session["selected_kashrut"] = None
                        log_step(call_id, phone, step, user_input, f"נבחרה קטגוריה '{selected_cat['category_name']}' ➔ רשימת מוצרים")
                        return show_category_products_menu(session)

                    session["step"] = "KASHRUT_MENU"
                    log_step(call_id, phone, step, user_input, f"נבחרה קטגוריה '{selected_cat['category_name']}' ➔ תפריט כשרויות")
                    k_text = "".join([f"לכשרות {k} הקישו {i}, " for i, k in enumerate(kashruts, 1)]) + "למעבר לתשלום בכל עת הקישו כוכבית"
                    max_d = max(1, len(str(len(kashruts))))
                    return yemot_read(k_text, "kashrut_choice", f"no,{max_d},1,7,No,no,no,*/,,,,,,no")
                return show_categories(session, prefix="הקשה שגויה, ")
            except ValueError:
                return show_categories(session, prefix="הקשה שגויה, ")

        elif step == "SKU_INPUT":
            if user_input == "*":
                log_step(call_id, phone, step, "*", "מעבר לתשלום")
                return initiate_checkout(session)

            matched = next((p for p in CACHE["products"] if p["sku"] == user_input or p["sku"].zfill(4) == user_input.zfill(4)), None)
            if not matched:
                log_step(call_id, phone, step, user_input, "מק\"ט לא נמצא")
                return yemot_read("לא נמצא מוצר עם מקט זה, אנא הקישו מקט בן 4 ספרות שוב או כוכבית לתשלום", "sku_input", "no,4,4,7,Digits,yes,no,*/")

            cat_prods = [p for p in CACHE["products"] if str(p.get("category_name", "")).strip().lower() == str(matched.get("category_name", "")).strip().lower()]
            session["filtered_products"] = cat_prods or [matched]
            try:
                session["product_index"] = session["filtered_products"].index(matched)
            except ValueError:
                session["product_index"] = 0
            log_step(call_id, phone, step, user_input, f"נמצא מק\"ט '{matched['name']}' ➔ הצגת מוצר")
            return play_current_product(session)

        elif step == "KASHRUT_MENU":
            if user_input == "*":
                return initiate_checkout(session)
            kashruts = session.get("available_kashruts", [])
            try:
                choice_idx = int(user_input) - 1
                if 0 <= choice_idx < len(kashruts):
                    session["selected_kashrut"] = kashruts[choice_idx]
                    log_step(call_id, phone, step, user_input, f"נבחרה כשרות '{kashruts[choice_idx]}' ➔ רשימת מוצרים")
                    return show_category_products_menu(session)
                return yemot_read("הקשה שגויה, אנא בחרו כשרות מתוך הרשימה", "kashrut_choice", "no,1,1,7,No,no,no,*/,,,,,,no")
            except ValueError:
                return yemot_read("הקשה שגויה, אנא בחרו כשרות מתוך הרשימה", "kashrut_choice", "no,1,1,7,No,no,no,*/,,,,,,no")

        elif step == "PRODUCT_LIST_MENU":
            if user_input == "*":
                return initiate_checkout(session)
            if user_input == "0":
                session["step"] = "SKU_INPUT"
                log_step(call_id, phone, step, "0", "מעבר לחיפוש מק\"ט")
                return yemot_read("אנא הקישו את מספר המקט בן 4 ספרות ולאחר מכן הקישו סולמית", "sku_input", "no,4,4,7,Digits,yes,no,*/")

            products = session.get("filtered_products", [])
            try:
                choice_idx = int(user_input) - 1
                if 0 <= choice_idx < len(products):
                    session["product_index"] = choice_idx
                    log_step(call_id, phone, step, user_input, f"נבחר מוצר '{products[choice_idx]['name']}'")
                    return play_current_product(session)
                return show_category_products_menu(session, prefix="הקשה שגויה, ")
            except ValueError:
                return show_category_products_menu(session, prefix="הקשה שגויה, ")

        elif step == "PRODUCT_LOOP":
            if user_input == "*":
                log_step(call_id, phone, step, "*", "מעבר לתשלום")
                return initiate_checkout(session)
            products = session.get("filtered_products", [])
            idx = session.get("product_index", 0)

            if user_input == "1":
                session["step"] = "QTY_INPUT"
                p = products[idx]
                log_step(call_id, phone, step, "1", f"בחירת כמות למוצר '{p['name']}'")
                return yemot_read(f"אנא הקישו את כמות היחידות ממוצר {clean_tts(p['name'])} אותם תרצו להוסיף לסל", "qty_input", "no,3,1,7,Digits,no,no,*/", "020a")
            elif user_input in ["2", "TIMEOUT", "ok", "None", ""]:
                session["product_index"] = (idx + 1) % len(products)
                log_step(call_id, phone, step, user_input or "TIMEOUT", "דילוג למוצר הבא")
                return play_current_product(session)
            elif user_input == "3":
                log_step(call_id, phone, step, "3", "חזרה לקטגוריות")
                return show_categories(session)
            else:
                return play_current_product(session, prefix="הקשה שגויה, ")

        elif step == "QTY_INPUT":
            if user_input == "*":
                return initiate_checkout(session)
            try:
                qty = int(user_input)
                if qty <= 0:
                    return yemot_read("כמות חייבת להיות גדולה מאפס, אנא הקש כמות תקינה", "qty_input", "no,3,1,7,Digits,no,no,*/", "020b")

                p = session["filtered_products"][session["product_index"]]
                effective_price = get_product_price_for_user(p, session.get("user"))
                item_total = qty * float(effective_price)
                session["cart"].append({"sku": p["sku"], "name": p["name"], "qty": qty, "total": item_total})

                user = session.get("user") or {}
                user_id = get_user_id(user) or phone
                if user_id:
                    SAVED_CARTS[user_id] = session["cart"]

                log_step(call_id, phone, step, str(qty), f"נוסף לסל: {p['name']} x{qty} (מחיר יח': {effective_price}, סה\"כ: {format_price(item_total)})")
                background_tasks.add_task(log_general_event, call_id, phone, "הוספה לסל", f"{p['name']} x {qty} (מחיר ליח': {effective_price})")
                cart_total = sum(float(i["total"]) for i in session["cart"])

                session["step"] = "AFTER_ADD_MENU"
                msg = (
                    f"המוצר נוסף לסל, המחיר הכולל עבור מוצר זה הינו {format_price(item_total)} שקלים, "
                    f"סך הכל בסל הקניות {format_price(cart_total)} שקלים. "
                    "למוצר הבא הקישו 1, לבחירת קטגוריה אחרת הקישו 2, למעבר לתשלום הקישו כוכבית"
                )
                return yemot_read(msg, "after_add_choice", "no,1,1,7,No,no,no,*/,,,,,,no", "022g")
            except ValueError:
                return yemot_read("הקשה שגויה, אנא הקש כמות במספרים בלבד", "qty_input", "no,3,1,7,Digits,no,no,*/", "021")

        elif step == "AFTER_ADD_MENU":
            if user_input in ["*", "9"]:
                log_step(call_id, phone, step, user_input, "מעבר לתשלום")
                return initiate_checkout(session)
            elif user_input == "1":
                session["product_index"] = (session["product_index"] + 1) % len(session["filtered_products"])
                log_step(call_id, phone, step, "1", "מעבר למוצר הבא")
                return play_current_product(session)
            elif user_input == "2":
                log_step(call_id, phone, step, "2", "חזרה לקטגוריות")
                return show_categories(session)
            else:
                return yemot_read("הקשה שגויה, למוצר הבא הקישו 1, לקטגוריה אחרת הקישו 2, לתשלום הקישו כוכבית", "after_add_choice", "no,1,1,7,No,no,no,*/,,,,,,no", "022g")

        elif step == "CONFIRM_CHECKOUT_FEE":
            if user_input == "1":
                return finish_checkout(session, background_tasks)
            elif user_input == "2":
                session["cart"] = []
                user = session.get("user") or {}
                user_id = get_user_id(user) or phone
                if user_id and user_id in SAVED_CARTS:
                    del SAVED_CARTS[user_id]
                log_step(call_id, phone, step, "2", "הזמנה בוטלה והסל נוקה")
                return show_categories(session, prefix="ההזמנה בוטלה, ")
            else:
                return initiate_checkout(session)

        # ---------------------------------------------------------
        # אזור אישי: תפריט, עדכון פרטים סדרתי והיסטוריית עסקאות
        # ---------------------------------------------------------
        elif step == "PERSONAL_AREA_MENU":
            if user_input == "1":
                if not session.get("user"):
                    session["auth_target"] = "PERSONAL_UPDATE"
                    session["step"] = "LOGIN_ID"
                    log_step(call_id, phone, step, "1", "עדכון פרטים ➔ בקשת ת.ז לזיהוי")
                    return yemot_read("לעדכון פרטים אנא הקישו תעודת זהות בת 8 עד 9 ספרות ולאחר מכן סולמית", "login_id", "no,9,8,7,Digits,yes,no,*/", "003")
                log_step(call_id, phone, step, "1", "עדכון פרטים ➔ מעבר לשם")
                return show_update_field_step(session, "UPD_NAME_MENU")
            elif user_input == "2":
                if not session.get("user"):
                    session["auth_target"] = "TX_HISTORY"
                    session["step"] = "LOGIN_ID"
                    log_step(call_id, phone, step, "2", "היסטוריית עסקאות ➔ בקשת ת.ז לזיהוי")
                    return yemot_read("לצפייה בהיסטוריית עסקאות אנא הקישו תעודת זהות בת 8 עד 9 ספרות ולאחר מכן סולמית", "login_id", "no,9,8,7,Digits,yes,no,*/", "003")
                log_step(call_id, phone, step, "2", "הצגת 10 עסקאות אחרונות")
                return show_tx_history_list(session)
            elif user_input == "3":
                log_step(call_id, phone, step, "3", "מעבר לשלוחה /1/3 (הודעות מהגבאי)")
                return Response(content="go_to_folder=/1/3", media_type="text/plain; charset=utf-8")
            elif user_input == "4":
                log_step(call_id, phone, step, "4", "רישום ראשוני מתוך אזור אישי")
                return start_registration(session, return_to="PERSONAL_AREA_MENU")
            elif user_input in ["9", "*"]:
                log_step(call_id, phone, step, user_input, "חזרה לתפריט ראשי")
                return show_welcome(session)
            else:
                return show_personal_area_menu(session, prefix="הקשה שגויה, ")

        elif step == "UPD_NAME_MENU":
            if user_input == "1":
                session["step"] = "UPD_NAME_REC"
                return yemot_read_record("אנא אמרו בקול ברור את השם המעודכן ולאחר מכן הקישו סולמית", "upd_name_rec", "", "005")
            elif user_input == "2":
                return show_update_field_step(session, "UPD_CITY_MENU")
            return show_update_field_step(session, "UPD_NAME_MENU", prefix="הקשה שגויה, ")

        elif step == "UPD_NAME_REC":
            text = transcribe_audio_file_from_yemot(raw_user_input, token)
            if not text:
                return yemot_read_record("לא הצלחנו לפענח, אנא אמרו שוב את השם ולאחר מכן סולמית", "upd_name_rec", "", "006")
            session["reg_data"]["temp_upd_name"] = text
            session["step"] = "UPD_NAME_CONFIRM"
            return yemot_read(f"השם שנקלט הוא {clean_tts(text)}. לאישור הקישו 1, להקלטה מחדש הקישו 2", "upd_name_confirm", "no,1,1,7,No,no,no,*/,,,,,,no")

        elif step == "UPD_NAME_CONFIRM":
            if user_input == "1":
                user = session["user"]
                new_name = session["reg_data"].get("temp_upd_name", "")
                user["first_name"] = new_name
                user["שם פרטי ומשפחה"] = new_name
                user["last_name"] = ""
                sync_user_in_cache(user)
                background_tasks.add_task(update_user_in_sheet, dict(user))
                log_step(call_id, phone, step, "1", f"שם עודכן ל-'{new_name}'")
                return show_update_field_step(session, "UPD_CITY_MENU", prefix="השם עודכן בהצלחה, ")
            session["step"] = "UPD_NAME_REC"
            return yemot_read_record("אנא אמרו בקול ברור את השם המעודכן ולאחר מכן הקישו סולמית", "upd_name_rec", "", "005")

        elif step == "UPD_CITY_MENU":
            if user_input == "1":
                return show_cities_menu(session, "UPD_CITY_SELECT", "upd_city_select")
            elif user_input == "2":
                return show_update_field_step(session, "UPD_ADDR_MENU")
            return show_update_field_step(session, "UPD_CITY_MENU", prefix="הקשה שגויה, ")

        elif step == "UPD_CITY_SELECT":
            cities = CACHE["cities"]
            try:
                idx = int(user_input) - 1
                if 0 <= idx < len(cities):
                    user = session["user"]
                    new_city = cities[idx]["city_name"]
                    user["city"] = new_city
                    user["עיר"] = new_city
                    sync_user_in_cache(user)
                    background_tasks.add_task(update_user_in_sheet, dict(user))
                    log_step(call_id, phone, step, user_input, f"עיר עודכנה ל-'{new_city}'")
                    return show_update_field_step(session, "UPD_ADDR_MENU", prefix="העיר עודכנה בהצלחה, ")
                return show_cities_menu(session, "UPD_CITY_SELECT", "upd_city_select", prefix="הקשה שגויה, ")
            except ValueError:
                return show_cities_menu(session, "UPD_CITY_SELECT", "upd_city_select", prefix="הקשה שגויה, ")

        elif step == "UPD_ADDR_MENU":
            if user_input == "1":
                session["step"] = "UPD_ADDR_REC"
                return yemot_read_record("אנא אמרו בקול ברור את הרחוב ומספר הבית המעודכנים ללא שם העיר ולאחר מכן הקישו סולמית", "upd_addr_rec", "", "010")
            elif user_input == "2":
                return show_update_field_step(session, "UPD_PHONE_MENU")
            return show_update_field_step(session, "UPD_ADDR_MENU", prefix="הקשה שגויה, ")

        elif step == "UPD_ADDR_REC":
            text = transcribe_audio_file_from_yemot(raw_user_input, token)
            if not text:
                return yemot_read_record("לא הצלחנו לפענח, אנא אמרו שוב את הרחוב ומספר הבית ללא שם העיר ולאחר מכן סולמית", "upd_addr_rec", "", "011")
            session["reg_data"]["temp_upd_addr"] = text
            session["step"] = "UPD_ADDR_CONFIRM"
            return yemot_read(f"הכתובת שנקלטה היא {clean_tts(text)}. לאישור הקישו 1, להקלטה מחדש הקישו 2", "upd_addr_confirm", "no,1,1,7,No,no,no,*/,,,,,,no")

        elif step == "UPD_ADDR_CONFIRM":
            if user_input == "1":
                user = session["user"]
                new_addr = session["reg_data"].get("temp_upd_addr", "")
                user["address"] = new_addr
                user["כתובת"] = new_addr
                sync_user_in_cache(user)
                background_tasks.add_task(update_user_in_sheet, dict(user))
                log_step(call_id, phone, step, "1", f"כתובת עודכנה ל-'{new_addr}'")
                return show_update_field_step(session, "UPD_PHONE_MENU", prefix="הכתובת עודכנה בהצלחה, ")
            session["step"] = "UPD_ADDR_REC"
            return yemot_read_record("אנא אמרו בקול ברור את הרחוב ומספר הבית המעודכנים ללא שם העיר ולאחר מכן הקישו סולמית", "upd_addr_rec", "", "010")

        elif step == "UPD_PHONE_MENU":
            if user_input == "1":
                session["step"] = "UPD_PHONE_INPUT"
                return yemot_read("אנא הקישו מספר טלפון מעודכן בן 9 עד 10 ספרות ולאחר מכן סולמית", "upd_phone_input", "no,10,9,7,Digits,yes,no,*/", "009")
            elif user_input == "2":
                return show_update_field_step(session, "UPD_COMMUNITY_MENU")
            return show_update_field_step(session, "UPD_PHONE_MENU", prefix="הקשה שגויה, ")

        elif step == "UPD_PHONE_INPUT":
            if not user_input or len(user_input) < 9 or len(user_input) > 10:
                return yemot_read("מספר לא תקין, הקישו מספר טלפון בן 9 עד 10 ספרות ולאחר מכן סולמית", "upd_phone_input", "no,10,9,7,Digits,yes,no,*/", "009")
            user = session["user"]
            user["phone"] = user_input
            user["מספר טלפון"] = user_input
            sync_user_in_cache(user)
            background_tasks.add_task(update_user_in_sheet, dict(user))
            log_step(call_id, phone, step, user_input, "טלפון עודכן")
            return show_update_field_step(session, "UPD_COMMUNITY_MENU", prefix="הטלפון עודכן בהצלחה, ")

        elif step == "UPD_COMMUNITY_MENU":
            if user_input == "1":
                session["step"] = "UPD_COMMUNITY_INPUT"
                return yemot_read("אנא הקישו קוד קהילה חדש בן 6 ספרות ולאחר מכן סולמית", "upd_comm_input", "no,6,6,7,Digits,yes,no,*/", "015")
            elif user_input == "2":
                return show_update_field_step(session, "UPD_PASS_MENU")
            return show_update_field_step(session, "UPD_COMMUNITY_MENU", prefix="הקשה שגויה, ")

        elif step == "UPD_COMMUNITY_INPUT":
            if not user_input or len(user_input) != 6:
                return yemot_read("קוד קהילה חייב להיות בן 6 ספרות, אנא הקישו שנית ולאחר מכן סולמית", "upd_comm_input", "no,6,6,7,Digits,yes,no,*/", "015")
            user = session["user"]
            user["community_code"] = user_input
            user["קוד קהילה"] = user_input
            sync_user_in_cache(user)
            background_tasks.add_task(update_user_in_sheet, dict(user))
            log_step(call_id, phone, step, user_input, "קוד קהילה עודכן")
            return show_update_field_step(session, "UPD_PASS_MENU", prefix="קוד הקהילה עודכן בהצלחה, ")

        elif step == "UPD_PASS_MENU":
            if user_input == "1":
                session["step"] = "UPD_PASS_INPUT"
                return yemot_read("אנא הקישו סיסמא חדשה בת 6 עד 10 ספרות ולאחר מכן סולמית", "upd_pass_input", "no,10,6,7,Digits,yes,no,*/")
            elif user_input == "2":
                return show_update_field_step(session, "UPD_TZINTUK_MENU")
            return show_update_field_step(session, "UPD_PASS_MENU", prefix="הקשה שגויה, ")

        elif step == "UPD_PASS_INPUT":
            if not user_input or len(user_input) < 6 or len(user_input) > 10:
                return yemot_read("סיסמא חייבת להיות בת 6 עד 10 ספרות, אנא הקישו שנית ולאחר מכן סולמית", "upd_pass_input", "no,10,6,7,Digits,yes,no,*/")
            user = session["user"]
            user["password"] = user_input
            user["סיסמא"] = user_input
            sync_user_in_cache(user)
            background_tasks.add_task(update_user_in_sheet, dict(user))
            log_step(call_id, phone, step, "******", "סיסמא עודכנה")
            return show_update_field_step(session, "UPD_TZINTUK_MENU", prefix="הסיסמא עודכנה בהצלחה, ")

        elif step == "UPD_TZINTUK_MENU":
            if user_input == "1":
                user = session["user"]
                user["personal_tzintuk"] = "TRUE"
                sync_user_in_cache(user)
                background_tasks.add_task(update_user_in_sheet, dict(user))
                tzintuk_list = phone or get_user_phone(user)
                update_yemot_tzintuk_extension(tzintuk_list, end_goto="/")
                session["step"] = "UPD_RETURN_FROM_TZINTUK"
                log_step(call_id, phone, step, "1", f"מעבר לשלוחה /C לרישום צינתוק אישי ({tzintuk_list})")
                return Response(content="go_to_folder=/C", media_type="text/plain; charset=utf-8")
            elif user_input == "2":
                return show_personal_area_menu(session, prefix="עדכון הפרטים הסתיים, ")
            return show_update_field_step(session, "UPD_TZINTUK_MENU", prefix="הקשה שגויה, ")

        # --- היסטוריית עסקאות ---
        elif step == "TX_HISTORY_LIST":
            if user_input in ["*", "9"]:
                return show_personal_area_menu(session)
            tx_list = session.get("tx_list", [])
            try:
                idx = int(user_input) - 1
                if 0 <= idx < len(tx_list):
                    tx = tx_list[idx]
                    session["step"] = "TX_HISTORY_DETAIL"
                    log_step(call_id, phone, step, user_input, f"צפייה בפרטי עסקה {tx.get('transaction_id', '')}")
                    detail_msg = (
                        f"פירוט עסקה מתאריך {clean_tts(tx.get('timestamp', ''))}. "
                        f"מוצרים: {clean_tts(tx.get('items_detail', ''))}. "
                        f"סכום כולל: {format_price(tx.get('total_amount', '0'))} שקלים. "
                        f"סטטוס: {clean_tts(tx.get('status', ''))}. "
                        "לחזרה לרשימת העסקאות הקישו 1, לחזרה לאזור האישי הקישו 2"
                    )
                    return yemot_read(detail_msg, "tx_detail_choice", "no,1,1,7,No,no,no,*/,,,,,,no")
                return show_tx_history_list(session, prefix="הקשה שגויה, ")
            except ValueError:
                return show_tx_history_list(session, prefix="הקשה שגויה, ")

        elif step == "TX_HISTORY_DETAIL":
            if user_input == "1":
                return show_tx_history_list(session)
            return show_personal_area_menu(session)

        # ---------------------------------------------------------
        # שלוחה 5: השארת הודעה לגבאי
        # ---------------------------------------------------------
        elif step == "GABAI_AUTH_ID":
            if user_input == "*":
                session["step"] = "GABAI_RECORD_MSG"
                log_step(call_id, phone, step, "*", "דילוג על זיהוי ➔ הקלטה לגבאי (/5)")
                return yemot_read_record("אנא השאירו את הודעתכם לגבאי ולאחר מכן הקישו סולמית", "gabai_msg", "/5")

            if user_input in CACHE["users"]:
                user = CACHE["users"][user_input]
                session["user"] = user
                if is_user_personal_tzintuk(user):
                    session["step"] = "GABAI_RECORD_MSG"
                    log_step(call_id, phone, step, user_input, "משתמש רשום לצינתוק אישי ➔ הקלטה לגבאי (/5)")
                    return yemot_read_record("אנא השאירו את הודעתכם לגבאי ולאחר מכן הקישו סולמית", "gabai_msg", "/5")
                session["step"] = "GABAI_TZINTUK_PROMPT"
                log_step(call_id, phone, step, user_input, "משתמש לא רשום לצינתוק אישי ➔ הצעת רישום")
                return yemot_read("שימו לב, אינכם רשומים באזור האישי לקבלת צינתוק אישי בעת קבלת תשובה. לרישום לצינתוק אישי הקישו 1, להמשך השארת הודעה לגבאי הקישו 2", "gabai_tzintuk_choice", "no,1,1,7,No,no,no,*/,,,,,,no")
            session["step"] = "GABAI_TZINTUK_PROMPT"
            return yemot_read("אינכם מזוהים כרשומים לצינתוק אישי. לרישום לצינתוק אישי הקישו 1, להשארת הודעה לגבאי הקישו 2", "gabai_tzintuk_choice", "no,1,1,7,No,no,no,*/,,,,,,no")

        elif step == "GABAI_TZINTUK_PROMPT":
            if user_input == "1":
                user = session.get("user")
                tzintuk_list = phone or (get_user_phone(user) if user else "")
                if user:
                    user["personal_tzintuk"] = "TRUE"
                    sync_user_in_cache(user)
                    background_tasks.add_task(update_user_in_sheet, dict(user))
                update_yemot_tzintuk_extension(tzintuk_list, end_goto="/")
                session["step"] = "GABAI_RETURN_FROM_TZINTUK"
                log_step(call_id, phone, step, "1", f"מעבר לשלוחה /C לרישום צינתוק אישי ({tzintuk_list})")
                return Response(content="go_to_folder=/C", media_type="text/plain; charset=utf-8")
            elif user_input == "2":
                session["step"] = "GABAI_RECORD_MSG"
                log_step(call_id, phone, step, "2", "הקלטה לגבאי ללא צינתוק (/5)")
                return yemot_read_record("אנא השאירו את הודעתכם לגבאי ולאחר מכן הקישו סולמית", "gabai_msg", "/5")
            return yemot_read("הקשה שגויה, לרישום לצינתוק אישי הקישו 1, להמשך השארת הודעה הקישו 2", "gabai_tzintuk_choice", "no,1,1,7,No,no,no,*/,,,,,,no")

        elif step == "GABAI_RECORD_MSG":
            if not raw_user_input:
                return yemot_read_record("אנא השאירו את הודעתכם לגבאי ולאחר מכן הקישו סולמית", "gabai_msg", "/5")

            log_step(call_id, phone, step, raw_user_input, "הודעה נשמרה ב-/5 ונשלחת למייל הגבאי")
            background_tasks.add_task(process_gabai_message, raw_user_input, phone, session.get("user"), token)
            background_tasks.add_task(log_general_event, call_id, phone, "הודעה לגבאי", f"נשמרה ב-/5 ונשלחה למייל: {raw_user_input}")
            return show_welcome(session, prefix="הודעתכם נשמרה במערכת ונשלחה למייל הגבאי בהצלחה, ")

        return yemot_msg("אירעה שגיאה במערכת, השיחה תנותק")

    except Exception as e:
        print(f"[CRITICAL ERROR] {e}\n{traceback.format_exc()}", flush=True)
        return show_welcome(SESSIONS.get(call_id, {}), prefix="אירעה שגיאה זמנית, ")
