
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

# 2. הקראה רובוטית בלבד בינתיים (False = TTS בלבד ללא קבצי הקלטה)
USE_AUDIO_FILES = False
AUDIO_FOLDER = "הודעות מערכת"
# ===================================================================

# הגדרות ימות המשיח ו-Google Apps Script
YEMOT_TOKEN = os.environ.get("YEMOT_TOKEN", "093136538:112131")
OTP_YEMOT_TOKEN = os.environ.get("OTP_YEMOT_TOKEN", YEMOT_TOKEN)
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

PENDING_FILE = "/tmp/pending_tzintuk_returns.json"
SAVED_CARTS_FILE = "/tmp/saved_carts.json"

CACHE = {
    "users": {},
    "community_codes": {},
    "categories": [],
    "products": [],
    "transactions": [],
    "cities": []
}

SESSIONS: Dict[str, Dict[str, Any]] = {}
SAVED_CARTS: Dict[str, Dict[str, Any]] = {}
OTP_PENDING: Dict[str, str] = {}
PENDING_TZINTUK: Dict[str, Dict[str, Any]] = {}

STEP_PARAM_MAP = {
    "ENTRY_ABANDONED_CART_CHOICE": ["entry_cart_choice", "ApiRealAnswer"],
    "WELCOME": ["welcome_choice", "ApiRealAnswer"],
    "LOGIN_ID": ["login_id", "ApiRealAnswer"],
    "LOGIN_ID_NOT_FOUND": ["login_not_found_choice", "ApiRealAnswer"],
    "LOGIN_PASS": ["login_pass", "ApiRealAnswer"],
    "LOGIN_WRONG_PASS": ["wrong_pass_choice", "ApiRealAnswer"],
    "FORGOT_OTP_INPUT": ["forgot_otp_input", "ApiRealAnswer"],
    "FORGOT_NEW_PASS": ["forgot_new_pass", "ApiRealAnswer"],
    "REG_ID": ["reg_id", "ApiRealAnswer"],
    "REG_PHONE_CHOICE": ["reg_phone_choice", "ApiRealAnswer"],
    "REG_PHONE": ["reg_phone", "ApiRealAnswer"],
    "REG_NAME": ["reg_name", "my_rec", "ApiRealAnswer"],
    "REG_NAME_CONFIRM": ["reg_name_confirm_choice", "ApiRealAnswer"],
    "REG_CITY": ["reg_city", "ApiRealAnswer"],
    "REG_ADDRESS": ["reg_address", "my_rec", "ApiRealAnswer"],
    "REG_ADDRESS_CONFIRM": ["reg_address_confirm_choice", "ApiRealAnswer"],
    "REG_COMMUNITY_CHOICE": ["reg_community_choice", "ApiRealAnswer"],
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
# לוגר מרוכז + ניהול סלי קניות וצינתוקים
# -------------------------------------------------------------------
def log_step(call_id: str, phone: str, step: str, user_input: str, action: str):
    ts = datetime.now().strftime("%H:%M:%S")
    cid = str(call_id)[-6:] if call_id else "------"
    inp = user_input if user_input != "" else "[ריק]"
    print(f"[{ts}] [שיחה:{cid} | טל:{phone}] שלב={step} | קלט={inp} ➔ {action}", flush=True)

def get_public_base_url(request: Request) -> str:
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    if host and "localhost" not in host and "127.0.0.1" not in host:
        proto = "https"
    if host:
        return f"{proto}://{host}"
    return str(request.base_url).rstrip("/")

def _load_json_file(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_json_file(path: str, data: dict):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass

def save_abandoned_cart(user_id: str, phone: str, cart: list, user: Optional[dict]):
    if not cart:
        return
    record = {
        "cart": list(cart),
        "user_id": str(user_id or ""),
        "phone": str(phone or ""),
        "user": user,
        "updated_at": datetime.now().timestamp()
    }
    disk = _load_json_file(SAVED_CARTS_FILE)
    if user_id:
        SAVED_CARTS[f"uid:{user_id}"] = record
        disk[f"uid:{user_id}"] = record
    if phone:
        SAVED_CARTS[f"ph:{phone}"] = record
        disk[f"ph:{phone}"] = record
    user_phone = get_user_phone(user) if user else ""
    if user_phone and user_phone != phone:
        SAVED_CARTS[f"ph:{user_phone}"] = record
        disk[f"ph:{user_phone}"] = record
    _save_json_file(SAVED_CARTS_FILE, disk)

def get_abandoned_cart(user_id: str = "", phone: str = "") -> Optional[dict]:
    keys = []
    if user_id:
        keys.append(f"uid:{user_id}")
    if phone:
        keys.append(f"ph:{phone}")

    for k in keys:
        rec = SAVED_CARTS.get(k)
        if rec and rec.get("cart"):
            return rec

    disk = _load_json_file(SAVED_CARTS_FILE)
    for k in keys:
        rec = disk.get(k)
        if rec and rec.get("cart"):
            SAVED_CARTS[k] = rec
            return rec
    return None

def delete_abandoned_cart(user_id: str = "", phone: str = ""):
    disk = _load_json_file(SAVED_CARTS_FILE)
    keys_to_remove = set()
    if user_id:
        keys_to_remove.add(f"uid:{user_id}")
    if phone:
        keys_to_remove.add(f"ph:{phone}")

    for store in (SAVED_CARTS, disk):
        for k in list(keys_to_remove):
            rec = store.get(k)
            if rec:
                if rec.get("user_id"):
                    keys_to_remove.add(f"uid:{rec['user_id']}")
                if rec.get("phone"):
                    keys_to_remove.add(f"ph:{rec['phone']}")

    for k in keys_to_remove:
        SAVED_CARTS.pop(k, None)
        disk.pop(k, None)
    _save_json_file(SAVED_CARTS_FILE, disk)

def save_pending_tzintuk(call_id: str, phone: str, return_type: str, session: dict):
    record = {
        "return_type": return_type,
        "reg_data": dict(session.get("reg_data", {})),
        "reg_return_to": session.get("reg_return_to", "MAIN_MENU"),
        "user": session.get("user"),
        "timestamp": datetime.now().timestamp()
    }
    disk = _load_json_file(PENDING_FILE)
    if call_id:
        PENDING_TZINTUK[f"cid:{call_id}"] = record
        disk[f"cid:{call_id}"] = record
    if phone:
        PENDING_TZINTUK[f"ph:{phone}"] = record
        disk[f"ph:{phone}"] = record
    _save_pending_file(disk)

def pop_pending_tzintuk(call_id: str, phone: str) -> Optional[dict]:
    now = datetime.now().timestamp()
    keys = []
    if call_id:
        keys.append(f"cid:{call_id}")
    if phone:
        keys.append(f"ph:{phone}")

    found = None
    for k in keys:
        if k in PENDING_TZINTUK:
            found = PENDING_TZINTUK.pop(k, None)
            break

    disk = _load_json_file(PENDING_FILE)
    if not found:
        for k in keys:
            if k in disk:
                found = disk.get(k)
                break

    for k in keys:
        PENDING_TZINTUK.pop(k, None)
        disk.pop(k, None)
    _save_pending_file(disk)

    if found and (now - found.get("timestamp", 0)) <= 600:
        return found
    return None

# -------------------------------------------------------------------
# 1. שמע, תמלול ופילטרים
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
# 2. עזר, ניקוי, אימות קהילה וניהול נתונים מ-Sheets
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

    clean_map = {}
    for actual_k, actual_v in item.items():
        ck = str(actual_k).strip().replace('"', '').replace("'", '').replace("_", "").replace(" ", "")
        if ck and actual_v is not None and str(actual_v).strip() != "":
            clean_map[ck] = actual_v

    for k in keys:
        target_ck = str(k).strip().replace('"', '').replace("'", '').replace("_", "").replace(" ", "")
        if target_ck in clean_map:
            return clean_map[target_ck]

    return default

def normalize_code(val: Any) -> str:
    s = str(val or "").strip()
    if s.endswith(".0"):
        s = s[:-2]
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits

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
    raw = get_field(user, "קוד קהילה", "קוד הקהילה", "קוד_קהילה", "קוד", "קהילה", "community_code", "community")
    return normalize_code(raw)

def get_user_password(user: dict) -> str:
    return str(get_field(user, "סיסמא", "סיסמה", "password", "pass")).strip()

def is_user_personal_tzintuk(user: dict) -> bool:
    val = str(get_field(user, "צינתוק אישי", "רישום לצינתוק אישי", "personal_tzintuk", "tzintuk", default="FALSE")).upper()
    return val in ["TRUE", "1", "YES", "כן"]

def validate_community_code(code: str) -> tuple[bool, str]:
    clean_c = normalize_code(code)
    if not clean_c or clean_c in ["0", "000000"]:
        return False, "קוד ריק"

    if CACHE.get("community_codes"):
        for raw_c, info in CACHE["community_codes"].items():
            norm_c = normalize_code(raw_c)
            if norm_c and (norm_c == clean_c or norm_c.zfill(6) == clean_c.zfill(6) or norm_c.lstrip("0") == clean_c.lstrip("0")):
                if not info.get("active", True):
                    return False, "קוד מושבת"
                return True, info.get("name") or "קהילה מאומתת"

    if 4 <= len(clean_c) <= 9 and clean_c.isdigit():
        return True, "קהילה כללית"

    return False, "קוד לא תקין"

def has_community_discount(user: Optional[dict]) -> bool:
    """
    בודק האם למשתמש יש זכאות למחיר קהילה:
    1. קוד קהילה תקין בכרטיס המשתמש, או
    2. תעודת הזהות של המשתמש מופיעה בעמודת 'תעודת זהות' בטבלת 'קודי קהילה'.
    """
    if not user:
        return False

    u_id = normalize_code(get_user_id(user))
    u_code = normalize_code(get_user_community(user))

    # 1. בדיקה לפי קוד קהילה
    if u_code and u_code not in ["0", "000000"]:
        if CACHE.get("community_codes"):
            for raw_c, info in CACHE["community_codes"].items():
                norm_c = normalize_code(raw_c)
                if norm_c and (norm_c == u_code or norm_c.zfill(6) == u_code.zfill(6) or norm_c.lstrip("0") == u_code.lstrip("0")):
                    return bool(info.get("active", True))
        return True

    # 2. בדיקה האם ת.ז של המשתמש מופיעה תחת עמודת תעודת זהות בקודי קהילה
    if u_id and CACHE.get("community_codes"):
        for raw_c, info in CACHE["community_codes"].items():
            owner_id = normalize_code(info.get("owner", ""))
            if owner_id and (owner_id == u_id or owner_id.zfill(9) == u_id.zfill(9) or owner_id.lstrip("0") == u_id.lstrip("0")):
                if info.get("active", True):
                    user["community_code"] = raw_c
                    user["קוד קהילה"] = raw_c
                    return True

    return False

def get_product_price_for_user(product: dict, user: Optional[dict]) -> str:
    regular_price = str(product.get("price", "0")).replace("₪", "").strip()
    comm_price = str(product.get("community_price", "")).replace("₪", "").strip()

    if regular_price.endswith(".0"): regular_price = regular_price[:-2]
    if comm_price.endswith(".0"): comm_price = comm_price[:-2]

    user_has_discount = has_community_discount(user)
    selected_price = regular_price

    if user_has_discount and comm_price:
        try:
            val = float(comm_price)
            if val > 0:
                selected_price = comm_price
        except ValueError:
            pass

    u_id = get_user_id(user) if user else "אנונימי"
    u_code = get_user_community(user) if user else "[ללא]"
    print(f"[חישוב מחיר] מוצר: {product.get('name')} | משתמש: {u_id} | קוד קהילה: '{u_code}' | זכאי להנחה: {user_has_discount} | מחיר רגיל: {regular_price} | מחיר לקהילות: {comm_price} ➔ נבחר: {selected_price}", flush=True)

    return selected_price

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
                id_num = str(get_field(u, "תעודת זהות", "ת.ז", "ת.ז.", "תז", "id_number", "id")).strip()
                phone = str(get_field(u, "מספר טלפון", "טלפון", "phone")).strip()
                if id_num:
                    users_dict[id_num] = u
                if phone:
                    users_dict[phone] = u
        CACHE["users"] = users_dict

        comm_dict = {}
        for cc in data.get("community_codes", []):
            code_val = normalize_code(get_field(cc, "קוד קהילה", "קוד הקהילה", "קוד", "code"))
            name_val = str(get_field(cc, "שם קהילה", "קהילה", "community_name", "name")).strip()
            # קריאת תעודת הזהות מעמודה C בקודי קהילה
            owner_val = str(get_field(cc, "תעודת זהות", "ת.ז", "ת.ז.", "תז", "מזהה", "פרטי זיהוי בעל הקוד", "פרטי זיהוי", "זיהוי", "איש קשר", "owner", "id_number", "id")).strip()
            is_act = str(get_field(cc, "פעיל", "is_active", default="TRUE")).upper() in ["TRUE", "1", "YES", "כן"]
            if code_val:
                comm_dict[code_val] = {
                    "name": name_val,
                    "owner": owner_val,
                    "active": is_act
                }
        CACHE["community_codes"] = comm_dict

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
                
                # קריאת עמודה D ("מחיר לקהילות") שמופיעה בין מחיר ליחידה להערות
                p_community_price = str(get_field(p, "מחיר לקהילות", "מחיר קהילות", "מחיר קהילה", "מחיר לקהילה", "מחיר קהילתי", "מחיר מוזל", "הנחת קהילה", "community_price", "comm_price")).strip()
                if not p_community_price:
                    for k, v in p.items():
                        clean_k = str(k).strip()
                        if "קהיל" in clean_k and str(v).strip():
                            p_community_price = str(v).strip()
                            break

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

        print(f"[CACHE] נטענו: {len(CACHE['users'])} משתמשים | {len(comm_dict)} קודי קהילה | {len(cats)} קטגוריות | {len(cities)} ערים | {len(prods)} מוצרים | {len(txs)} עסקאות", flush=True)
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
        "community_codes_count": len(CACHE["community_codes"]),
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
    user_id = get_user_id(user) or session_data.get("phone", "")
    user_name = get_user_name(user) or "מאזין"
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

def log_incomplete_transaction_to_sheet(session_data: dict):
    user = session_data.get("user") or {}
    cart = session_data.get("cart", [])
    if not cart:
        return
    items_summary = "; ".join([f"{item['name']} מקט {item['sku']} כמות {item['qty']} סך הכל {format_price(item['total'])} שח" for item in cart])
    cart_sum = sum(float(item["total"]) for item in cart)
    user_id = get_user_id(user) or session_data.get("phone", "")
    user_name = get_user_name(user) or "מאזין"
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    tx_record = {
        "type": "transaction",
        "transaction_id": str(session_data.get("call_id")),
        "timestamp": ts,
        "user_identifier": str(user_id),
        "user_name": user_name,
        "items_detail": items_summary,
        "total_amount": format_price(cart_sum),
        "status": "לא הושלמה"
    }
    CACHE["transactions"].append(tx_record)
    post_to_apps_script(tx_record)

# -------------------------------------------------------------------
# 3. צינתוק אישי (/C -> /D) + OTP + גבאי
# -------------------------------------------------------------------
def update_yemot_tzintuk_extensions(list_name: str, base_url: str):
    if not YEMOT_TOKEN or not list_name:
        print("[UpdateExtension ERROR] חסר טוקן או שם רשימה", flush=True)
        return False

    return_api_url = f"{base_url.rstrip('/')}/tzintuk-done"
    try:
        res_d = requests.post(
            "https://www.call2all.co.il/ym/api/UpdateExtension",
            data={"token": YEMOT_TOKEN, "path": "ivr2:/D", "type": "api", "api_link": return_api_url},
            timeout=8
        )
        print(f"[UpdateExtension ivr2:/D] api_link={return_api_url} | תגובה: {res_d.text[:150]}", flush=True)
    except Exception as e:
        print(f"[UpdateExtension ivr2:/D ERROR] {e}", flush=True)

    for target_path in ["ivr2:/C", "ivr2:C"]:
        try:
            res_c = requests.post(
                "https://www.call2all.co.il/ym/api/UpdateExtension",
                data={"token": YEMOT_TOKEN, "path": target_path, "type": "tzintuk", "list_tzintuk": list_name, "tzintuk_end": "/D"},
                timeout=8
            )
            print(f"[UpdateExtension {target_path}] list_tzintuk={list_name} tzintuk_end=/D | תגובה: {res_c.text[:150]}", flush=True)
            if '"OK"' in res_c.text or '"responseStatus":"OK"' in res_c.text:
                return True
        except Exception as e:
            print(f"[UpdateExtension {target_path} ERROR] {e}", flush=True)
    return False

def redirect_to_tzintuk_c(session: dict, call_id: str, phone: str, return_type: str, request: Request) -> Response:
    user = session.get("user")
    tzintuk_list_name = phone or session.get("reg_data", {}).get("phone", "") or (get_user_phone(user) if user else "")
    if return_type == "REG":
        session["reg_data"]["tzintuk_list"] = tzintuk_list_name
        session["step"] = "REG_RETURN_FROM_TZINTUK"
    elif return_type == "UPD":
        session["step"] = "UPD_RETURN_FROM_TZINTUK"
    else:
        session["step"] = "GABAI_RETURN_FROM_TZINTUK"

    base_url = get_public_base_url(request)
    update_yemot_tzintuk_extensions(tzintuk_list_name, base_url)
    save_pending_tzintuk(call_id, phone, return_type, session)
    log_step(call_id, phone, session["step"], "", f"מעבר לשלוחה /C (רשימה: {tzintuk_list_name}, חזרה דרך /D)")
    return Response(content="go_to_folder=/C", media_type="text/plain; charset=utf-8")

def send_personal_tzintuk_by_list(target_phone: str):
    if not target_phone or not YEMOT_TOKEN:
        return False
    clean_p = normalize_code(target_phone)
    params = {"token": YEMOT_TOKEN, "phones": f"tzl:{clean_p}", "TzintukTimeOut": "16"}
    if OTP_CALLER_ID:
        params["callerId"] = OTP_CALLER_ID
    try:
        res = requests.get("https://www.call2all.co.il/ym/api/RunTzintuk", params=params, timeout=15)
        print(f"[RunTzintuk] נשלח לרשימה tzl:{clean_p} | תגובה: {res.text[:120]}", flush=True)
        return True
    except Exception as e:
        print(f"[RunTzintuk ERROR] {e}", flush=True)
        return False

@app.api_route("/send-personal-tzintuk", methods=["GET", "POST"])
async def trigger_personal_tzintuk(phone: str, background_tasks: BackgroundTasks):
    clean_phone = clean_input(phone)
    background_tasks.add_task(send_personal_tzintuk_by_list, clean_phone)
    return {"status": "queued", "list": f"tzl:{clean_phone}"}

def send_otp_tzintuk_call(target_phone: str, otp_code: str):
    if not target_phone or not OTP_YEMOT_TOKEN:
        return
    digits_spaced = " ".join(list(otp_code))
    tts_msg = f"שלום, קוד האימות שלך לאיפוס הסיסמא הוא: {digits_spaced}."
    OTP_PENDING[target_phone] = otp_code

    params = {"token": OTP_YEMOT_TOKEN, "phones": target_phone, "ttsMessage": tts_msg, "repeatFile": "3", "ttsRate": "-2"}
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
# 4. פונקציות עזר לפורמט read= של ימות המשיח
# -------------------------------------------------------------------
def opts_menu(max_d: int = 1, min_d: int = 1, sec: int = 7, allow_star: bool = True) -> str:
    block_star = "no" if allow_star else "yes"
    return f"no,{max_d},{min_d},{sec},No,{block_star},no,,,,,,,no"

def opts_digits_confirm(max_d: int, min_d: int = 1, sec: int = 7, allow_star: bool = True) -> str:
    block_star = "no" if allow_star else "yes"
    return f"no,{max_d},{min_d},{sec},Digits,{block_star},no"

def opts_digits_no_confirm(max_d: int, min_d: int = 1, sec: int = 7, allow_star: bool = True) -> str:
    block_star = "no" if allow_star else "yes"
    return f"no,{max_d},{min_d},{sec},Digits,{block_star},no,,,,,,,no"

def build_sound(text: str, file_num: str = "") -> str:
    clean_text = clean_tts(text)
    if USE_AUDIO_FILES and file_num:
        return f"f-/{AUDIO_FOLDER}/{file_num}.t-{clean_text}"
    return f"t-{clean_text}"

def yemot_read(text: str, var_name: str, options: str = None, file_num: str = "") -> Response:
    opts = options or opts_menu()
    sound_str = build_sound(text, file_num)
    content = f"read={sound_str}={var_name},{opts}&rate=3&tts_rate=3"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def yemot_read_record(text: str, var_name: str, record_folder: str = "", file_num: str = "", skip_menu: bool = True) -> Response:
    sound_str = build_sound(text, file_num)
    folder = record_folder if (record_folder and record_folder != "/") else ""
    end_menu = "no" if skip_menu else ""
    content = f"read={sound_str}={var_name},no,record,{folder},,{end_menu}"
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

def get_checkout_key(items_count: int) -> str:
    return "9" if items_count < 9 else "00"

def show_welcome(session: dict, prefix: str = "", return_to_root: bool = False) -> Response:
    session["step"] = "WELCOME"
    if return_to_root:
        if prefix:
            return Response(content=f"id_list_message=t-{clean_tts(prefix)}&go_to_folder=/", media_type="text/plain; charset=utf-8")
        return Response(content="go_to_folder=/", media_type="text/plain; charset=utf-8")
    msg = f"{prefix}{WELCOME_TEXT}" if prefix else WELCOME_TEXT
    return yemot_read(msg, "welcome_choice", opts_menu(1, 1, 7, allow_star=True), "001")

def show_cities_menu(session: dict, target_step: str, var_name: str, prefix: str = "") -> Response:
    cities = CACHE["cities"]
    if not cities:
        if target_step == "REG_CITY":
            session["step"] = "REG_ADDRESS"
            return yemot_read_record("אנא אמרו בקול ברור את כתובת המגורים שלכם, רחוב ומספר בית ללא שם העיר, ולאחר מכן הקישו סולמית", "reg_address", "", "010", skip_menu=True)
        return show_update_field_step(session, "UPD_ADDR_MENU", prefix="לא הוגדרו ערים ברשימה, ")

    cities_text = "".join([f"ל{ct['city_name']} הקישו {i}, " for i, ct in enumerate(cities, 1)])
    max_d = max(1, len(str(len(cities))))
    session["step"] = target_step
    msg = f"{prefix}אנא בחרו את עיר המגורים שלכם. {cities_text} לחזרה לתפריט קודם הקישו כוכבית"
    return yemot_read(msg, var_name, opts_menu(max_d, 1, 7, allow_star=True), "029")

def check_abandoned_cart_or_proceed(session: dict) -> Response:
    user = session.get("user", {})
    user_id = get_user_id(user) or session.get("phone", "")
    phone = session.get("phone", "")
    saved = get_abandoned_cart(user_id=user_id, phone=phone)
    if saved and saved.get("cart"):
        session["step"] = "RESTORE_CART_CHOICE"
        msg = "המערכת מזהה כי ישנה עיסקה פעילה במערכת שעדיין לא הושלמה. למעבר להמשך ההזמנה הקישו 1, למחיקת ההזמנה הקישו 2"
        return yemot_read(msg, "restore_cart_choice", opts_menu(1, 1, 7, allow_star=True), "026")
    session["step"] = "MAIN_MENU"
    return show_categories(session)

def show_categories(session: dict, prefix: str = "") -> Response:
    cats = CACHE["categories"]
    if not cats:
        return yemot_msg("מצטערים, אין כרגע קטגוריות זמינות")

    ckey = get_checkout_key(len(cats))
    cats_text = "".join([f"ל{c['category_name']} הקישו {i}, " for i, c in enumerate(cats, 1)])
    max_d = max(2 if ckey == "00" else 1, len(str(len(cats))))
    msg = f"{prefix}לתפריט ההזמנות: {cats_text} לבחירת מוצר לפי מקט הקישו 0, למעבר לתשלום הקישו {ckey}, לחזרה לתפריט הראשי הקישו כוכבית"
    session["step"] = "MAIN_MENU"
    return yemot_read(msg, "cat_choice", opts_menu(max_d, 1, 7, allow_star=True), "017a")

def show_kashruts_menu(session: dict, prefix: str = "") -> Response:
    kashruts = session.get("available_kashruts", [])
    if not kashruts:
        return show_category_products_menu(session)
    ckey = get_checkout_key(len(kashruts))
    k_text = "".join([f"לכשרות {k} הקישו {i}, " for i, k in enumerate(kashruts, 1)])
    max_d = max(2 if ckey == "00" else 1, len(str(len(kashruts))))
    msg = f"{prefix}{k_text} למעבר לתשלום הקישו {ckey}, לחזרה לקטגוריות הקישו כוכבית"
    session["step"] = "KASHRUT_MENU"
    return yemot_read(msg, "kashrut_choice", opts_menu(max_d, 1, 7, allow_star=True))

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
    ckey = get_checkout_key(len(filtered))
    prods_text = "".join([f"ל{p['name']} הקישו {i}, " for i, p in enumerate(filtered, 1)])
    max_d = max(2 if ckey == "00" else 1, len(str(len(filtered))))
    msg = f"{prefix}{prods_text} לבחירת מוצר לפי מקט הקישו 0, למעבר לתשלום הקישו {ckey}, לחזרה לתפריט הקודם הקישו כוכבית"
    session["step"] = "PRODUCT_LIST_MENU"
    return yemot_read(msg, "prod_list_choice", opts_menu(max_d, 1, 7, allow_star=True))

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
        f"להוספת המוצר לסל הקישו 1, למוצר הבא הקישו 2 או המתינו, למעבר לקטגוריות הקישו 3, לתשלום הקישו 9, לחזרה לרשימת המוצרים הקישו כוכבית"
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
            + f"f-/{AUDIO_FOLDER}/022f.t-להוספת המוצר לסל הקישו 1, למוצר הבא הקישו 2 או המתינו, למעבר לקטגוריות הקישו 3, לתשלום הקישו 9, לחזרה הקישו כוכבית"
        )

    session["step"] = "PRODUCT_LOOP"
    options = "no,1,1,5,No,no,no,,,1,Ok,TIMEOUT,,no"
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
    part2 = "שקלים. לאישור ומעבר לתשלום הקישו 1, לביטול ההזמנה הקישו 2, לחזרה לתפריט הקישו כוכבית"

    if USE_AUDIO_FILES:
        sound_chain = f"f-/{AUDIO_FOLDER}/023a.t-{clean_tts(part1)}.n-{total_str}.f-/{AUDIO_FOLDER}/023b.t-{clean_tts(part2)}"
    else:
        sound_chain = f"t-{clean_tts(part1)}.n-{total_str}.t-{clean_tts(part2)}"

    return Response(content=f"read={sound_chain}=checkout_confirm_choice,{opts_menu(1, 1, 7, allow_star=True)}&rate=3&tts_rate=3", media_type="text/plain; charset=utf-8")

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
    delete_abandoned_cart(user_id=user_id, phone=phone)
    session["checkout_completed"] = True

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
        "להודעות מהגבאי הקישו 3, לרישום ראשוני הקישו 4, לחזרה לתפריט הראשי הקישו כוכבית"
    )
    return yemot_read(msg, "personal_choice", opts_menu(1, 1, 7, allow_star=True), "014d")

def show_update_field_step(session: dict, field_step: str, prefix: str = "") -> Response:
    user = session.get("user") or {}
    session["step"] = field_step

    if field_step == "UPD_NAME_MENU":
        val = clean_tts(get_user_name(user)) or "לא עודכן"
        return yemot_read(f"{prefix}שם: {val}. לעדכון הקישו 1, להמשך הקישו 2, לחזרה הקישו כוכבית", "upd_name_choice", opts_menu())
    if field_step == "UPD_CITY_MENU":
        val = clean_tts(get_user_city(user)) or "לא עודכנה"
        return yemot_read(f"{prefix}עיר: {val}. לעדכון הקישו 1, להמשך הקישו 2, לחזרה הקישו כוכבית", "upd_city_choice", opts_menu())
    if field_step == "UPD_ADDR_MENU":
        val = clean_tts(get_user_address(user)) or "לא עודכנה"
        return yemot_read(f"{prefix}כתובת: {val}. לעדכון הקישו 1, להמשך הקישו 2, לחזרה הקישו כוכבית", "upd_addr_choice", opts_menu())
    if field_step == "UPD_PHONE_MENU":
        val = clean_tts(get_user_phone(user)) or "לא עודכן"
        return yemot_read(f"{prefix}טלפון: {val}. לעדכון הקישו 1, להמשך הקישו 2, לחזרה הקישו כוכבית", "upd_phone_choice", opts_menu())
    if field_step == "UPD_COMMUNITY_MENU":
        comm_code = get_user_community(user)
        valid, comm_name = validate_community_code(comm_code)
        val_desc = f"{comm_code} ({comm_name})" if valid else ("לא מוגדר או מושבת" if comm_code else "לא עודכן")
        return yemot_read(f"{prefix}קוד קהילה: {val_desc}. לעדכון הקישו 1, להמשך הקישו 2, לחזרה הקישו כוכבית", "upd_comm_choice", opts_menu())
    if field_step == "UPD_PASS_MENU":
        val = clean_tts(get_user_password(user)) or "לא הוגדרה"
        return yemot_read(f"{prefix}סיסמא: {val}. לעדכון הקישו 1, להמשך הקישו 2, לחזרה הקישו כוכבית", "upd_pass_choice", opts_menu())
    if field_step == "UPD_TZINTUK_MENU":
        status = "רשום" if is_user_personal_tzintuk(user) else "אינך רשום"
        return yemot_read(f"{prefix}סטטוס קבלת צינתוק אישי: {status}. לרישום לקבלת צינתוק אישי הקישו 1, לסיום וחזרה לאזור האישי הקישו 2, לחזרה הקישו כוכבית", "upd_tzintuk_choice", opts_menu())
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
    return yemot_read(txt, "tx_list_choice", opts_menu(max_d, 1, 7, allow_star=True))

def start_registration(session: dict, return_to: str = "MAIN_MENU", prefill_id: str = "") -> Response:
    session["reg_data"] = {}
    session["reg_return_to"] = return_to
    session["reg_prefilled"] = bool(prefill_id)
    if prefill_id:
        session["reg_data"]["id_number"] = prefill_id
        session["step"] = "REG_PHONE_CHOICE"
        msg = "עוברים לתהליך הרשמה. מספר תעודת הזהות נקלט. לרישום עם מספר הטלפון ממנו אתם מחייגים הקישו 1, להקשת מספר טלפון אחר הקישו 2, לחזרה הקישו כוכבית"
        return yemot_read(msg, "reg_phone_choice", opts_menu())

    session["step"] = "REG_ID"
    msg = "תהליך הרשמה. אנא הקישו את מספר תעודת הזהות שלכם בן 8 עד 9 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית"
    return yemot_read(msg, "reg_id", opts_digits_confirm(9, 1, 7, allow_star=True), "007")

def start_forgot_password(session: dict, background_tasks: BackgroundTasks) -> Response:
    user = session.get("pending_login_user") or session.get("user")
    if not user:
        session["step"] = "LOGIN_ID"
        return yemot_read("לא זוהה חשבון. אנא הקישו את מספר תעודת הזהות שלכם ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "login_id", opts_digits_confirm(9, 1, 7, allow_star=True), "003")

    target_phone = get_user_phone(user) or session.get("phone", "")
    otp_code = f"{random.randint(100000, 999999)}"
    session["forgot_otp"] = otp_code
    session["step"] = "FORGOT_OTP_INPUT"

    background_tasks.add_task(send_otp_tzintuk_call, target_phone, otp_code)
    background_tasks.add_task(log_general_event, session.get("call_id", ""), session.get("phone", ""), "שכחתי סיסמא", f"נשלח קוד OTP ל-{target_phone}")

    msg = "שיחת קוד אימות נשלחה כעת למספר הטלפון הרשום בחשבונך. לאחר קבלת הקוד בן 6 הספרות הקישו אותו כאן, לחזרה הקישו כוכבית וסולמית"
    return yemot_read(msg, "forgot_otp_input", opts_menu(6, 1, 15, allow_star=True))

# -------------------------------------------------------------------
# 6. Webhook ראשי
# -------------------------------------------------------------------
@app.api_route("/tzintuk-done", methods=["GET", "POST", "HEAD"])
async def tzintuk_done_handler(request: Request, background_tasks: BackgroundTasks):
    return await handle_ivr_request(request, background_tasks, from_tzintuk_endpoint=True)

@app.api_route("/", methods=["GET", "POST", "HEAD"])
async def ivr_handler(request: Request, background_tasks: BackgroundTasks):
    return await handle_ivr_request(request, background_tasks, from_tzintuk_endpoint=False)

async def handle_ivr_request(request: Request, background_tasks: BackgroundTasks, from_tzintuk_endpoint: bool = False):
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
        api_ext = params.get("ApiExtension", "").strip()

        # ---------------------------------------------------------
        # טיפול בניתוק שיחה + שמירת עסקה שלא הושלמה בשיטס
        # ---------------------------------------------------------
        if params.get("hangup") == "yes":
            ext_hangup = params.get("ApiHangupExtension", "")
            sess = SESSIONS.get(call_id)
            if sess and sess.get("cart") and not sess.get("checkout_completed") and not sess.get("incomplete_logged"):
                sess["incomplete_logged"] = True
                u = sess.get("user") or {}
                uid = get_user_id(u) or phone
                save_abandoned_cart(uid, phone, sess["cart"], u if u else None)
                background_tasks.add_task(log_incomplete_transaction_to_sheet, dict(sess))
                log_step(call_id, phone, "HANGUP", "", f"ניתוק באמצע הזמנה (שלוחה {ext_hangup}) ➔ נשמרה בזיכרון ונרשמה בשיטס בסטטוס 'לא הושלמה'")
            else:
                log_step(call_id, phone, "HANGUP", "", f"השיחה נותקה בשלוחה {ext_hangup}")
            return Response(content="ok", media_type="text/plain; charset=utf-8")

        if call_id not in SESSIONS:
            SESSIONS[call_id] = {
                "step": "WELCOME",
                "user": None,
                "orders_authenticated": False,
                "entry_cart_handled": False,
                "checkout_completed": False,
                "incomplete_logged": False,
                "pending_login_user": None,
                "pending_unauth_id": "",
                "cart": [],
                "selected_cat": None,
                "selected_kashrut": None,
                "available_kashruts": [],
                "filtered_products": [],
                "product_index": 0,
                "call_id": call_id,
                "phone": phone,
                "reg_data": {},
                "reg_return_to": "MAIN_MENU",
                "reg_prefilled": False,
                "auth_target": "MAIN_MENU"
            }
            log_step(call_id, phone, "NEW_CALL", "", "פתיחת שיחה חדשה")
            background_tasks.add_task(log_general_event, call_id, phone, "כניסה לשיחה", "התחלת שיחה חדשה")

        session = SESSIONS[call_id]
        step = session["step"]

        non_api_params = {k: v for k, v in params.items() if not k.startswith("Api")}
        print(f"[REQ ext={api_ext or '/'} ep={'D' if from_tzintuk_endpoint else '/'}] שיחה:{str(call_id)[-6:]} | טל:{phone} | שלב={step} | פרמטרים={non_api_params}", flush=True)

        # ---------------------------------------------------------
        # שחזור וחזרה אוטומטית משלוחה /C -> /D (/tzintuk-done)
        # ---------------------------------------------------------
        is_awaiting_c = step in ["REG_RETURN_FROM_TZINTUK", "UPD_RETURN_FROM_TZINTUK", "GABAI_RETURN_FROM_TZINTUK"]
        if is_awaiting_c or (from_tzintuk_endpoint and "reg_password" not in params and "reg_end_choice" not in params and step in ["WELCOME", "REG_RETURN_FROM_TZINTUK", "UPD_RETURN_FROM_TZINTUK", "GABAI_RETURN_FROM_TZINTUK"]):
            pending_c = pop_pending_tzintuk(call_id, phone)
            rtype = (pending_c or {}).get("return_type")
            if not rtype:
                if step == "UPD_RETURN_FROM_TZINTUK":
                    rtype = "UPD"
                elif step == "GABAI_RETURN_FROM_TZINTUK":
                    rtype = "GABAI"
                else:
                    rtype = "REG"

            if rtype == "REG":
                if pending_c:
                    session["reg_data"] = pending_c.get("reg_data", {})
                    session["reg_return_to"] = pending_c.get("reg_return_to", "MAIN_MENU")
                session["reg_data"]["personal_tzintuk"] = "TRUE"
                session["step"] = "REG_PASSWORD"
                log_step(call_id, phone, "RETURN_FROM_C(/D)", "", "חזר מרישום צינתוק ➔ מבקש קוד סיסמא בן 6 ספרות")
                return yemot_read("הרישום לצינתוקים האישיים הושלם. כעת לסיום הרישום אנא הקישו קוד סיסמא אישי בן 6 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "reg_password", opts_digits_confirm(6, 1, 7, allow_star=True))

            if rtype == "UPD":
                if pending_c and pending_c.get("user"):
                    session["user"] = pending_c["user"]
                log_step(call_id, phone, "RETURN_FROM_C(/D)", "", "חזר מרישום צינתוק ➔ חזרה לאזור אישי")
                return show_personal_area_menu(session, prefix="נרשמתם בהצלחה לצינתוקים אישיים, ")

            if rtype == "GABAI":
                if pending_c and pending_c.get("user"):
                    session["user"] = pending_c["user"]
                session["step"] = "GABAI_RECORD_MSG"
                log_step(call_id, phone, "RETURN_FROM_C(/D)", "", "חזר מרישום צינתוק ➔ הקלטת הודעה לגבאי (/5)")
                return yemot_read_record("נרשמתם לצינתוק אישי. כעת אנא השאירו את הודעתכם לגבאי ולאחר מכן הקישו סולמית", "gabai_msg", "/5", skip_menu=False)

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
        is_back = (user_input == "*")

        # ---------------------------------------------------------
        # בדיקת עסקה פעילה בכניסה לשיחה
        # ---------------------------------------------------------
        if step == "ENTRY_ABANDONED_CART_CHOICE":
            known_user = CACHE["users"].get(phone) or {}
            saved = get_abandoned_cart(user_id=get_user_id(known_user), phone=phone)

            if user_input == "1":
                session["entry_cart_handled"] = True
                if saved and saved.get("cart"):
                    session["cart"] = list(saved["cart"])
                    if saved.get("user"):
                        session["user"] = saved["user"]
                    elif known_user:
                        session["user"] = known_user
                    session["orders_authenticated"] = True
                    cart_sum = sum(float(i["total"]) for i in session["cart"])
                    log_step(call_id, phone, step, "1", f"המשך הזמנה פעילה מכניסה (סכום {format_price(cart_sum)} ש\"ח) ➔ קטגוריות")
                    return show_categories(session, prefix=f"סכום ההזמנה הנוכחי עומד על {format_price(cart_sum)} שקלים. ")
                return show_welcome(session, prefix="לא נמצאה הזמנה פעילה, ")

            elif user_input == "2":
                session["entry_cart_handled"] = True
                log_step(call_id, phone, step, "2", "שמירת ההזמנה בהמתנה עד לכניסה להזמנות ➔ תפריט ראשי")
                return show_welcome(session, prefix="ההזמנה נשמרה בהמתנה עד לכניסה למערכת ההזמנות. ")

            elif user_input == "3":
                session["entry_cart_handled"] = True
                session["cart"] = []
                delete_abandoned_cart(user_id=get_user_id(known_user), phone=phone)
                log_step(call_id, phone, step, "3", "מחיקת הזמנה מהזיכרון ➔ תפריט ראשי")
                return show_welcome(session, prefix="ההזמנה נמחקה. ")

            else:
                msg = (
                    "הקשה שגויה. המערכת מזהה כי ישנה עיסקה פעילה במערכת שעדיין לא הושלמה. "
                    "למעבר להמשך ההזמנה הקישו 1, לשמירת ההזמנה במצב המתנה עד לכניסה הבאה למערכת ההזמנות הקישו 2, למחיקת ההזמנה הקישו 3"
                )
                return yemot_read(msg, "entry_cart_choice", opts_menu(1, 1, 7, allow_star=False))

        # ---------------------------------------------------------
        # תפריט ראשי
        # ---------------------------------------------------------
        if step == "WELCOME":
            if not user_input and not session.get("entry_cart_handled"):
                known_user = CACHE["users"].get(phone) or {}
                saved_entry = get_abandoned_cart(user_id=get_user_id(known_user), phone=phone)
                if saved_entry and saved_entry.get("cart"):
                    session["step"] = "ENTRY_ABANDONED_CART_CHOICE"
                    log_step(call_id, phone, "WELCOME", "", "זוהתה עסקה פעילה שלא שולמה בכניסה ➔ שאלת המשך/המתנה/מחיקה")
                    msg = (
                        "המערכת מזהה כי ישנה עיסקה פעילה במערכת שעדיין לא הושלמה. "
                        "למעבר להמשך ההזמנה הקישו 1, לשמירת ההזמנה במצב המתנה עד לכניסה הבאה למערכת ההזמנות הקישו 2, למחיקת ההזמנה הקישו 3"
                    )
                    return yemot_read(msg, "entry_cart_choice", opts_menu(1, 1, 7, allow_star=False))

            if not user_input or is_back:
                log_step(call_id, phone, step, user_input, "השמעת תפריט ראשי")
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
                return yemot_read("לכניסה למערכת ההזמנות אנא הקישו את מספר תעודת הזהות שלכם בן 8 עד 9 ספרות ולאחר מכן הקישו סולמית, לחזרה לתפריט הראשי הקישו כוכבית וסולמית", "login_id", opts_digits_confirm(9, 1, 7, allow_star=True), "003")

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
                        return yemot_read_record("אנא השאירו את הודעתכם לגבאי ולאחר מכן הקישו סולמית", "gabai_msg", "/5", skip_menu=False)
                    session["step"] = "GABAI_TZINTUK_PROMPT"
                    log_step(call_id, phone, step, "5", "לא רשום לצינתוק אישי ➔ הצעת רישום לפני גבאי")
                    return yemot_read("שימו לב, אינכם רשומים באזור האישי לקבלת צינתוק אישי בעת קבלת תשובה. לרישום לצינתוק אישי הקישו 1, להמשך השארת הודעה לגבאי הקישו 2, לחזרה הקישו כוכבית", "gabai_tzintuk_choice", opts_menu())
                session["step"] = "GABAI_AUTH_ID"
                log_step(call_id, phone, step, "5", "לא זוהה טלפונית ➔ בקשת ת.ז או 0 לפני גבאי")
                return yemot_read("להשארת הודעה לגבאי אנא הקישו את מספר תעודת הזהות שלכם לבדיקת רישום לצינתוק אישי, להשארת הודעה ללא זיהוי הקישו 0 וסולמית, לחזרה הקישו כוכבית וסולמית", "gabai_auth_id", opts_menu(10, 1, 7, allow_star=True))

            else:
                log_step(call_id, phone, step, user_input, "הקשה שגויה בתפריט ראשי")
                return show_welcome(session, prefix="הקשה שגויה, ")

        # ---------------------------------------------------------
        # התחברות להזמנות ולאזור אישי
        # ---------------------------------------------------------
        elif step == "LOGIN_ID":
            if is_back:
                log_step(call_id, phone, step, "*", "חזרה לתפריט ראשי")
                return show_welcome(session, return_to_root=from_tzintuk_endpoint)

            if not user_input or not user_input.isdigit() or len(user_input) < 8 or len(user_input) > 9:
                log_step(call_id, phone, step, user_input, "ת.ז לא תקינה ➔ בקשה חוזרת")
                return yemot_read("אנא הקישו מספר תעודת זהות תקין בן 8 עד 9 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "login_id", opts_digits_confirm(9, 1, 7, allow_star=True), "003")

            if user_input in CACHE["users"]:
                user = CACHE["users"][user_input]
                session["pending_login_user"] = user
                saved_pass = get_user_password(user)
                if not saved_pass:
                    session["step"] = "FORGOT_NEW_PASS"
                    log_step(call_id, phone, step, user_input, "נמצא משתמש ללא סיסמא ➔ הגדרת סיסמא חדשה")
                    return yemot_read("טרם הוגדרה סיסמא לחשבונך. אנא בחרו סיסמא חדשה בת 6 עד 10 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "forgot_new_pass", opts_digits_confirm(10, 1, 7, allow_star=True))

                session["step"] = "LOGIN_PASS"
                log_step(call_id, phone, step, user_input, "נמצא משתמש ➔ בקשת סיסמא")
                return yemot_read("אנא הקישו את הסיסמא שלכם בת 6 עד 10 ספרות ולאחר מכן הקישו סולמית. אם שכחתם את הסיסמא הקישו 0 וסולמית, לחזרה הקישו כוכבית וסולמית", "login_pass", opts_digits_confirm(10, 1, 7, allow_star=True))
            else:
                session["pending_unauth_id"] = user_input
                session["step"] = "LOGIN_ID_NOT_FOUND"
                log_step(call_id, phone, step, user_input, "ת.ז לא נמצאה ➔ בחירה: מספר אחר (1) או רישום (2)")
                return yemot_read("מספר תעודת הזהות אינו מזוהה במערכת. להקשת מספר אחר הקישו 1, למעבר לרישום הקישו 2, לחזרה לתפריט הראשי הקישו כוכבית", "login_not_found_choice", opts_menu())

        elif step == "LOGIN_ID_NOT_FOUND":
            if is_back or user_input == "1":
                session["step"] = "LOGIN_ID"
                log_step(call_id, phone, step, user_input, "חזרה להקשת ת.ז")
                return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם בן 8 עד 9 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "login_id", opts_digits_confirm(9, 1, 7, allow_star=True), "003")
            elif user_input == "2":
                target = session.get("auth_target", "MAIN_MENU")
                reg_return = "PERSONAL_AREA_MENU" if target in ["PERSONAL_UPDATE", "TX_HISTORY"] else "MAIN_MENU"
                prefill_id = session.get("pending_unauth_id", "")
                log_step(call_id, phone, step, "2", f"מעבר לרישום עם ת.ז מוזנת ({prefill_id}) ➔ בחירת טלפון")
                return start_registration(session, return_to=reg_return, prefill_id=prefill_id)
            else:
                return yemot_read("הקשה שגויה. להקשת מספר אחר הקישו 1, למעבר לרישום הקישו 2, לחזרה הקישו כוכבית", "login_not_found_choice", opts_menu())

        elif step == "LOGIN_PASS":
            if is_back:
                session["step"] = "LOGIN_ID"
                log_step(call_id, phone, step, "*", "חזרה להקשת ת.ז")
                return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם בן 8 עד 9 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "login_id", opts_digits_confirm(9, 1, 7, allow_star=True), "003")
            if user_input == "0":
                log_step(call_id, phone, step, "0", "בקשת שכחתי סיסמא")
                return start_forgot_password(session, background_tasks)

            user = session.get("pending_login_user")
            if not user:
                session["step"] = "LOGIN_ID"
                return yemot_read("אנא הקישו תעודת זהות ולאחר מכן סולמית", "login_id", opts_digits_confirm(9, 1, 7, allow_star=True), "003")

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
                return yemot_read("הסיסמא שהוקשה שגויה. לניסיון הקשה נוסף הקישו 1, לשכחתי סיסמא ואיפוס הקישו 2, לחזרה הקישו כוכבית", "wrong_pass_choice", opts_menu())

        elif step == "LOGIN_WRONG_PASS":
            if is_back:
                session["step"] = "LOGIN_ID"
                return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם בן 8 עד 9 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "login_id", opts_digits_confirm(9, 1, 7, allow_star=True), "003")
            if user_input == "1":
                session["step"] = "LOGIN_PASS"
                log_step(call_id, phone, step, "1", "ניסיון סיסמא חוזר")
                return yemot_read("אנא הקישו את הסיסמא שלכם בת 6 עד 10 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "login_pass", opts_digits_confirm(10, 1, 7, allow_star=True))
            elif user_input == "2":
                log_step(call_id, phone, step, "2", "מעבר לשכחתי סיסמא")
                return start_forgot_password(session, background_tasks)
            else:
                return yemot_read("הקשה שגויה, לניסיון נוסף הקישו 1, לשכחתי סיסמא הקישו 2, לחזרה הקישו כוכבית", "wrong_pass_choice", opts_menu())

        # ---------------------------------------------------------
        # שכחתי סיסמא
        # ---------------------------------------------------------
        elif step == "FORGOT_OTP_INPUT":
            if is_back:
                session["step"] = "LOGIN_PASS"
                return yemot_read("אנא הקישו את הסיסמא שלכם בת 6 עד 10 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "login_pass", opts_digits_confirm(10, 1, 7, allow_star=True))
            expected = session.get("forgot_otp", "")
            if user_input == expected and expected:
                session["step"] = "FORGOT_NEW_PASS"
                log_step(call_id, phone, step, user_input, "קוד OTP אומת ➔ הזנת סיסמא חדשה")
                return yemot_read("הקוד אומת בהצלחה. אנא הקישו סיסמא חדשה בת 6 עד 10 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "forgot_new_pass", opts_digits_confirm(10, 1, 7, allow_star=True))
            else:
                log_step(call_id, phone, step, user_input, "קוד OTP שגוי")
                return yemot_read("קוד האימות שגוי. אנא הקישו שוב את 6 הספרות שקיבלתם בשיחה, לחזרה הקישו כוכבית וסולמית", "forgot_otp_input", opts_menu(6, 1, 15, allow_star=True))

        elif step == "FORGOT_NEW_PASS":
            if is_back:
                session["step"] = "LOGIN_ID"
                return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם ולאחר מכן סולמית, לחזרה הקישו כוכבית וסולמית", "login_id", opts_digits_confirm(9, 1, 7, allow_star=True), "003")
            if not user_input or not user_input.isdigit() or len(user_input) < 6 or len(user_input) > 10:
                log_step(call_id, phone, step, user_input, "סיסמא חדשה לא באורך 6-10")
                return yemot_read("סיסמא חייבת להיות בת 6 עד 10 ספרות, אנא הקישו שנית ולאחר מכן סולמית, לחזרה הקישו כוכבית וסולמית", "forgot_new_pass", opts_digits_confirm(10, 1, 7, allow_star=True))

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
            return check_abandoned_cart_or_proceed(session)

        # ---------------------------------------------------------
        # תהליך רישום
        # ---------------------------------------------------------
        elif step == "REG_ID":
            if is_back:
                log_step(call_id, phone, step, "*", "חזרה לתפריט קודם")
                if session.get("reg_return_to") == "PERSONAL_AREA_MENU":
                    return show_personal_area_menu(session)
                return show_welcome(session, return_to_root=from_tzintuk_endpoint)

            if not user_input or not user_input.isdigit() or len(user_input) < 8 or len(user_input) > 9:
                log_step(call_id, phone, step, user_input, "ת.ז לא תקינה")
                return yemot_read("אנא הקישו תעודת זהות תקינה בת 8 עד 9 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "reg_id", opts_digits_confirm(9, 1, 7, allow_star=True), "007")
            if user_input in CACHE["users"]:
                log_step(call_id, phone, step, user_input, "ת.ז כבר רשומה במערכת")
                return yemot_read("מספר תעודת זהות זה כבר רשום במערכת, אנא הקישו מספר תעודת זהות אחר, לחזרה הקישו כוכבית וסולמית", "reg_id", opts_digits_confirm(9, 1, 7, allow_star=True), "008")

            session["reg_data"]["id_number"] = user_input
            session["step"] = "REG_PHONE_CHOICE"
            log_step(call_id, phone, step, user_input, "ת.ז נקלטה ➔ בחירת טלפון (1 מחייג / 2 אחר)")
            return yemot_read("לרישום עם מספר הטלפון ממנו אתם מחייגים הקישו 1, להקשת מספר טלפון אחר הקישו 2, לחזרה הקישו כוכבית", "reg_phone_choice", opts_menu())

        elif step == "REG_PHONE_CHOICE":
            if is_back:
                if session.get("reg_prefilled"):
                    session["step"] = "LOGIN_ID"
                    return yemot_read("אנא הקישו מספר תעודת זהות ולאחר מכן סולמית, לחזרה הקישו כוכבית וסולמית", "login_id", opts_digits_confirm(9, 1, 7, allow_star=True), "003")
                session["step"] = "REG_ID"
                return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם בן 8 עד 9 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "reg_id", opts_digits_confirm(9, 1, 7, allow_star=True), "007")

            if user_input == "1":
                if phone and phone.isdigit() and len(phone) >= 9:
                    session["reg_data"]["phone"] = phone
                    session["step"] = "REG_NAME"
                    log_step(call_id, phone, step, "1", f"נבחר מספר מחייג ({phone}) ➔ הקלטת שם")
                    return yemot_read_record("נקלט המספר ממנו אתם מחייגים. כעת אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "", "005", skip_menu=True)
                session["step"] = "REG_PHONE"
                log_step(call_id, phone, step, "1", "מספר מחייג אינו מזוהה ➔ מעבר להקשה ידנית")
                return yemot_read("המספר ממנו אתם מחייגים אינו מזוהה. אנא הקישו את מספר הטלפון שלכם בן 9 עד 10 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "reg_phone", opts_digits_confirm(10, 1, 7, allow_star=True), "009")
            elif user_input == "2":
                session["step"] = "REG_PHONE"
                log_step(call_id, phone, step, "2", "בחירה להקיש טלפון אחר")
                return yemot_read("אנא הקישו את מספר הטלפון שלכם בן 9 עד 10 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "reg_phone", opts_digits_confirm(10, 1, 7, allow_star=True), "009")
            else:
                return yemot_read("הקשה שגויה. לרישום עם מספר הטלפון ממנו אתם מחייגים הקישו 1, להקשת מספר אחר הקישו 2, לחזרה הקישו כוכבית", "reg_phone_choice", opts_menu())

        elif step == "REG_PHONE":
            if is_back:
                session["step"] = "REG_PHONE_CHOICE"
                return yemot_read("לרישום עם מספר הטלפון ממנו אתם מחייגים הקישו 1, להקשת מספר טלפון אחר הקישו 2, לחזרה הקישו כוכבית", "reg_phone_choice", opts_menu())

            if not user_input or not user_input.isdigit() or len(user_input) < 9 or len(user_input) > 10:
                log_step(call_id, phone, step, user_input, "טלפון לא תקין")
                return yemot_read("מספר לא תקין. אנא הקישו מספר טלפון בן 9 עד 10 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "reg_phone", opts_digits_confirm(10, 1, 7, allow_star=True), "009")

            session["reg_data"]["phone"] = user_input
            session["step"] = "REG_NAME"
            log_step(call_id, phone, step, user_input, "טלפון נקלט ➔ הקלטת שם (ללא תפריט הקלטה)")
            return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "", "005", skip_menu=True)

        elif step == "REG_NAME":
            if not raw_user_input:
                return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "", "005", skip_menu=True)

            transcribed_text = transcribe_audio_file_from_yemot(raw_user_input, token)
            if not transcribed_text:
                log_step(call_id, phone, step, raw_user_input, "תמלול שם נכשל ➔ הקלטה חוזרת")
                return yemot_read_record("לא הצלחנו לפענח את ההקלטה, אנא אמרו שוב בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "", "006", skip_menu=True)

            session["reg_data"]["temp_name"] = transcribed_text
            session["step"] = "REG_NAME_CONFIRM"
            log_step(call_id, phone, step, transcribed_text, "שם תומלל ➔ בקשת אישור שם")
            clean_name = clean_tts(transcribed_text)
            return yemot_read(f"השם שנקלט הוא {clean_name}. לאישור הקישו 1, להקלטה מחדש הקישו 2, לחזרה הקישו כוכבית", "reg_name_confirm_choice", opts_menu())

        elif step == "REG_NAME_CONFIRM":
            if is_back:
                session["step"] = "REG_PHONE_CHOICE"
                return yemot_read("לרישום עם מספר הטלפון ממנו אתם מחייגים הקישו 1, להקשת מספר טלפון אחר הקישו 2, לחזרה הקישו כוכבית", "reg_phone_choice", opts_menu())
            if user_input == "1":
                session["reg_data"]["first_name"] = session["reg_data"].get("temp_name", "")
                log_step(call_id, phone, step, "1", "שם אושר ➔ תפריט ערים")
                return show_cities_menu(session, "REG_CITY", "reg_city")
            elif user_input == "2":
                session["step"] = "REG_NAME"
                log_step(call_id, phone, step, "2", "הקלטת שם מחדש")
                return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "", "005", skip_menu=True)
            else:
                clean_name = clean_tts(session["reg_data"].get("temp_name", ""))
                return yemot_read(f"הקשה שגויה. השם שנקלט הוא {clean_name}. לאישור הקישו 1, להקלטה מחדש הקישו 2, לחזרה הקישו כוכבית", "reg_name_confirm_choice", opts_menu())

        elif step == "REG_CITY":
            if is_back:
                session["step"] = "REG_NAME"
                log_step(call_id, phone, step, "*", "חזרה להקלטת שם")
                return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "", "005", skip_menu=True)
            cities = CACHE["cities"]
            try:
                idx = int(user_input) - 1
                if 0 <= idx < len(cities):
                    chosen_city = cities[idx]["city_name"]
                    session["reg_data"]["city"] = chosen_city
                    session["step"] = "REG_ADDRESS"
                    log_step(call_id, phone, step, user_input, f"נבחרה עיר '{chosen_city}' ➔ הקלטת רחוב ומספר בית (ללא תפריט)")
                    return yemot_read_record(f"נבחרה העיר {clean_tts(chosen_city)}. כעת אנא אמרו בקול ברור את הרחוב ומספר הבית בלבד ללא שם העיר ולאחר מכן הקישו סולמית", "reg_address", "", "010", skip_menu=True)
                return show_cities_menu(session, "REG_CITY", "reg_city", prefix="הקשה שגויה, ")
            except ValueError:
                return show_cities_menu(session, "REG_CITY", "reg_city", prefix="הקשה שגויה, ")

        elif step == "REG_ADDRESS":
            if not raw_user_input:
                return yemot_read_record("אנא אמרו בקול ברור את הרחוב ומספר הבית בלבד ללא שם העיר ולאחר מכן הקישו סולמית", "reg_address", "", "010", skip_menu=True)

            transcribed_text = transcribe_audio_file_from_yemot(raw_user_input, token)
            if not transcribed_text:
                log_step(call_id, phone, step, raw_user_input, "תמלול כתובת נכשל ➔ הקלטה חוזרת")
                return yemot_read_record("לא הצלחנו לפענח את ההקלטה, אנא אמרו שוב בקול ברור את הרחוב ומספר הבית ללא שם העיר ולאחר מכן הקישו סולמית", "reg_address", "", "011", skip_menu=True)

            session["reg_data"]["temp_address"] = transcribed_text
            session["step"] = "REG_ADDRESS_CONFIRM"
            log_step(call_id, phone, step, transcribed_text, "כתובת תומללה ➔ בקשת אישור כתובת")
            clean_addr = clean_tts(transcribed_text)
            return yemot_read(f"הכתובת שנקלטה היא {clean_addr}. לאישור הקישו 1, להקלטה מחדש הקישו 2, לחזרה הקישו כוכבית", "reg_address_confirm_choice", opts_menu())

        elif step == "REG_ADDRESS_CONFIRM":
            if is_back:
                log_step(call_id, phone, step, "*", "חזרה לבחירת עיר")
                return show_cities_menu(session, "REG_CITY", "reg_city")
            if user_input == "1":
                session["reg_data"]["address"] = session["reg_data"].get("temp_address", "")
                session["step"] = "REG_COMMUNITY_CHOICE"
                log_step(call_id, phone, step, "1", "כתובת אושרה ➔ בחירה: קוד קהילה (1) או דילוג (2)")
                return yemot_read("להקשת קוד קהילה הקישו 1, לדילוג הקישו 2, לחזרה הקישו כוכבית", "reg_community_choice", opts_menu())
            elif user_input == "2":
                session["step"] = "REG_ADDRESS"
                log_step(call_id, phone, step, "2", "הקלטת כתובת מחדש")
                return yemot_read_record("אנא אמרו בקול ברור את הרחוב ומספר הבית בלבד ללא שם העיר ולאחר מכן הקישו סולמית", "reg_address", "", "010", skip_menu=True)
            else:
                clean_addr = clean_tts(session["reg_data"].get("temp_address", ""))
                return yemot_read(f"הקשה שגויה. הכתובת שנקלטה היא {clean_addr}. לאישור הקישו 1, להקלטה מחדש הקישו 2, לחזרה הקישו כוכבית", "reg_address_confirm_choice", opts_menu())

        elif step == "REG_COMMUNITY_CHOICE":
            if is_back:
                session["step"] = "REG_ADDRESS"
                log_step(call_id, phone, step, "*", "חזרה להקלטת כתובת")
                return yemot_read_record("אנא אמרו בקול ברור את הרחוב ומספר הבית בלבד ללא שם העיר ולאחר מכן הקישו סולמית", "reg_address", "", "010", skip_menu=True)
            if user_input == "1":
                session["step"] = "REG_COMMUNITY_CODE"
                log_step(call_id, phone, step, "1", "בחירה להקיש קוד קהילה")
                return yemot_read("אנא הקישו את קוד הקהילה שלכם ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "reg_community_code", opts_digits_confirm(9, 1, 7, allow_star=True), "012")
            elif user_input == "2":
                session["reg_data"]["community_code"] = ""
                log_step(call_id, phone, step, "2", "דילוג על קוד קהילה ➔ מעבר לשלוחה /C")
                return redirect_to_tzintuk_c(session, call_id, phone, "REG", request)
            else:
                return yemot_read("הקשה שגויה. להקשת קוד קהילה הקישו 1, לדילוג הקישו 2, לחזרה הקישו כוכבית", "reg_community_choice", opts_menu())

        elif step == "REG_COMMUNITY_CODE":
            if is_back:
                session["step"] = "REG_COMMUNITY_CHOICE"
                return yemot_read("להקשת קוד קהילה הקישו 1, לדילוג הקישו 2, לחזרה הקישו כוכבית", "reg_community_choice", opts_menu())

            is_valid_code, comm_name_or_err = validate_community_code(user_input)
            if not is_valid_code:
                log_step(call_id, phone, step, user_input, f"קוד קהילה לא תקין/מושבת ({comm_name_or_err})")
                return yemot_read("קוד הקהילה שהוקש אינו מוכר או שאינו פעיל במערכת. אנא הקישו שוב ולאחר מכן סולמית, או הקישו כוכבית וסולמית לחזרה", "reg_community_code", opts_digits_confirm(9, 1, 7, allow_star=True), "012")

            session["reg_data"]["community_code"] = normalize_code(user_input)
            log_step(call_id, phone, step, user_input, f"קוד קהילה אומת בהצלחה ({comm_name_or_err}) ➔ מעבר לשלוחה /C")
            return redirect_to_tzintuk_c(session, call_id, phone, "REG", request)

        elif step == "REG_PASSWORD":
            if is_back:
                session["step"] = "REG_COMMUNITY_CHOICE"
                return yemot_read("להקשת קוד קהילה הקישו 1, לדילוג הקישו 2, לחזרה הקישו כוכבית", "reg_community_choice", opts_menu())
            if not user_input or not user_input.isdigit() or len(user_input) != 6:
                log_step(call_id, phone, step, user_input, "קוד לא תקין (נדרשות 6 ספרות)")
                return yemot_read("הקוד חייב להיות בן 6 ספרות בלבד, אנא הקישו שוב ולאחר מכן סולמית, לחזרה הקישו כוכבית וסולמית", "reg_password", opts_digits_confirm(6, 1, 7, allow_star=True))

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
            background_tasks.add_task(log_general_event, call_id, phone, "הרשמה הושלמה", f"נרשם: {new_user['first_name']} | עיר: {new_user['city']} | קהילה: {new_user['community_code']}")

            log_step(call_id, phone, step, "******", f"משתמש חדש נשמר ({new_user['id_number']}) ➔ תפריט סיום הרשמה")
            ret = session.get("reg_return_to", "MAIN_MENU")
            if ret == "PERSONAL_AREA_MENU":
                return show_personal_area_menu(session, prefix="הרישום הושלם בהצלחה, ")

            session["step"] = "REG_END_MENU"
            return yemot_read("הרישום הושלם בהצלחה. למעבר לתפריט ההזמנות הקישו 1, לחזרה לתפריט הראשי הקישו 2", "reg_end_choice", opts_menu(), "013")

        elif step == "REG_END_MENU":
            if is_back or user_input == "2":
                log_step(call_id, phone, step, user_input, "חזרה לתפריט ראשי (/)")
                return show_welcome(session, return_to_root=from_tzintuk_endpoint)
            if user_input == "1":
                log_step(call_id, phone, step, "1", "מעבר לתפריט ההזמנות")
                return show_categories(session)
            return yemot_read("הקשה שגויה. למעבר לתפריט ההזמנות הקישו 1, לחזרה לתפריט הראשי הקישו 2", "reg_end_choice", opts_menu(), "013")

        # ---------------------------------------------------------
        # שחזור סל פתוח בשלוחה 2 (אחרי זיהוי + סיסמא)
        # ---------------------------------------------------------
        elif step == "RESTORE_CART_CHOICE":
            if is_back:
                log_step(call_id, phone, step, "*", "חזרה לתפריט ראשי")
                return show_welcome(session, return_to_root=from_tzintuk_endpoint)
            user = session.get("user") or {}
            user_id = get_user_id(user) or phone
            if user_input == "1":
                saved = get_abandoned_cart(user_id=user_id, phone=phone)
                session["cart"] = list(saved["cart"]) if saved and saved.get("cart") else []
                cart_sum = sum(float(i["total"]) for i in session["cart"])
                log_step(call_id, phone, step, "1", f"המשך הזמנה פעילה (סכום {format_price(cart_sum)} ש\"ח)")
                return show_categories(session, prefix=f"סכום ההזמנה הנוכחי עומד על {format_price(cart_sum)} שקלים. ")
            elif user_input == "2":
                session["cart"] = []
                delete_abandoned_cart(user_id=user_id, phone=phone)
                log_step(call_id, phone, step, "2", "מחיקת הזמנה פעילה והתחלת תפריט הזמנות נקי")
                return show_categories(session, prefix="ההזמנה נמחקה, ")
            else:
                msg = "הקשה שגויה. המערכת מזהה כי ישנה עיסקה פעילה במערכת שעדיין לא הושלמה. למעבר להמשך ההזמנה הקישו 1, למחיקת ההזמנה הקישו 2, לחזרה הקישו כוכבית"
                return yemot_read(msg, "restore_cart_choice", opts_menu(), "026")

        elif step == "MAIN_MENU":
            if is_back:
                log_step(call_id, phone, step, "*", "חזרה לתפריט ראשי")
                return show_welcome(session, return_to_root=from_tzintuk_endpoint)

            cats = CACHE["categories"]
            ckey = get_checkout_key(len(cats))
            if user_input == ckey:
                log_step(call_id, phone, step, ckey, "מעבר לתשלום מהקטגוריות")
                return initiate_checkout(session)
            if user_input == "0":
                session["step"] = "SKU_INPUT"
                log_step(call_id, phone, step, "0", "בחירת מוצר לפי מק\"ט (4 ספרות)")
                return yemot_read("אנא הקישו את מספר המקט בן 4 ספרות ולאחר מכן הקישו סולמית, לחזרה לקטגוריות הקישו כוכבית וסולמית", "sku_input", opts_digits_confirm(4, 1, 7, allow_star=True))

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

                    log_step(call_id, phone, step, user_input, f"נבחרה קטגוריה '{selected_cat['category_name']}' ➔ תפריט כשרויות")
                    return show_kashruts_menu(session)
                return show_categories(session, prefix="הקשה שגויה, ")
            except ValueError:
                return show_categories(session, prefix="הקשה שגויה, ")

        elif step == "SKU_INPUT":
            if is_back:
                log_step(call_id, phone, step, "*", "חזרה לתפריט קטגוריות")
                return show_categories(session)

            matched = next((p for p in CACHE["products"] if p["sku"] == user_input or p["sku"].zfill(4) == user_input.zfill(4)), None)
            if not matched:
                log_step(call_id, phone, step, user_input, "מק\"ט לא נמצא")
                return yemot_read("לא נמצא מוצר עם מקט זה, אנא הקישו מקט בן 4 ספרות שוב או כוכבית וסולמית לחזרה", "sku_input", opts_digits_confirm(4, 1, 7, allow_star=True))

            cat_prods = [p for p in CACHE["products"] if str(p.get("category_name", "")).strip().lower() == str(matched.get("category_name", "")).strip().lower()]
            session["filtered_products"] = cat_prods or [matched]
            try:
                session["product_index"] = session["filtered_products"].index(matched)
            except ValueError:
                session["product_index"] = 0
            log_step(call_id, phone, step, user_input, f"נמצא מק\"ט '{matched['name']}' ➔ הצגת מוצר")
            return play_current_product(session)

        elif step == "KASHRUT_MENU":
            if is_back:
                log_step(call_id, phone, step, "*", "חזרה לתפריט קטגוריות")
                return show_categories(session)
            kashruts = session.get("available_kashruts", [])
            ckey = get_checkout_key(len(kashruts))
            if user_input == ckey:
                return initiate_checkout(session)
            try:
                choice_idx = int(user_input) - 1
                if 0 <= choice_idx < len(kashruts):
                    session["selected_kashrut"] = kashruts[choice_idx]
                    log_step(call_id, phone, step, user_input, f"נבחרה כשרות '{kashruts[choice_idx]}' ➔ רשימת מוצרים")
                    return show_category_products_menu(session)
                return show_kashruts_menu(session, prefix="הקשה שגויה, ")
            except ValueError:
                return show_kashruts_menu(session, prefix="הקשה שגויה, ")

        elif step == "PRODUCT_LIST_MENU":
            if is_back:
                if session.get("available_kashruts"):
                    log_step(call_id, phone, step, "*", "חזרה לתפריט כשרויות")
                    return show_kashruts_menu(session)
                log_step(call_id, phone, step, "*", "חזרה לתפריט קטגוריות")
                return show_categories(session)

            products = session.get("filtered_products", [])
            ckey = get_checkout_key(len(products))
            if user_input == ckey:
                return initiate_checkout(session)
            if user_input == "0":
                session["step"] = "SKU_INPUT"
                log_step(call_id, phone, step, "0", "מעבר לחיפוש מק\"ט")
                return yemot_read("אנא הקישו את מספר המקט בן 4 ספרות ולאחר מכן הקישו סולמית, לחזרה הקישו כוכבית וסולמית", "sku_input", opts_digits_confirm(4, 1, 7, allow_star=True))

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
            if is_back:
                log_step(call_id, phone, step, "*", "חזרה לרשימת המוצרים")
                return show_category_products_menu(session)
            if user_input == "9":
                log_step(call_id, phone, step, "9", "מעבר לתשלום")
                return initiate_checkout(session)

            products = session.get("filtered_products", [])
            idx = session.get("product_index", 0)

            if user_input == "1":
                session["step"] = "QTY_INPUT"
                p = products[idx]
                log_step(call_id, phone, step, "1", f"בחירת כמות למוצר '{p['name']}'")
                return yemot_read(
                    f"אנא הקישו את כמות היחידות ממוצר {clean_tts(p['name'])} ולאחר מכן הקישו סולמית, לחזרה למוצר הקישו כוכבית וסולמית",
                    "qty_input",
                    opts_digits_no_confirm(3, 1, 7, allow_star=True),
                    "020a"
                )
            elif user_input in ["2", "TIMEOUT", "ok", "None", ""]:
                session["product_index"] = (idx + 1) % len(products)
                log_step(call_id, phone, step, user_input or "TIMEOUT", "דילוג למוצר הבא")
                return play_current_product(session)
            elif user_input == "3":
                log_step(call_id, phone, step, "3", "מעבר לקטגוריות")
                return show_categories(session)
            else:
                return play_current_product(session, prefix="הקשה שגויה, ")

        elif step == "QTY_INPUT":
            if is_back:
                log_step(call_id, phone, step, "*", "חזרה לפרטי המוצר")
                return play_current_product(session)
            try:
                qty = int(user_input)
                if qty <= 0:
                    return yemot_read("כמות חייבת להיות גדולה מאפס, אנא הקש כמות תקינה ולאחר מכן סולמית, לחזרה הקישו כוכבית וסולמית", "qty_input", opts_digits_no_confirm(3, 1, 7, allow_star=True), "020b")

                p = session["filtered_products"][session["product_index"]]
                effective_price = get_product_price_for_user(p, session.get("user"))
                item_total = qty * float(effective_price)
                session["cart"].append({"sku": p["sku"], "name": p["name"], "qty": qty, "total": item_total})

                user = session.get("user") or {}
                user_id = get_user_id(user) or phone
                save_abandoned_cart(user_id, phone, session["cart"], user if user else None)

                log_step(call_id, phone, step, str(qty), f"נוסף לסל: {p['name']} x{qty} (מחיר יח': {effective_price}, סה\"כ: {format_price(item_total)})")
                background_tasks.add_task(log_general_event, call_id, phone, "הוספה לסל", f"{p['name']} x {qty} (מחיר ליח': {effective_price})")
                cart_total = sum(float(i["total"]) for i in session["cart"])

                session["step"] = "AFTER_ADD_MENU"
                msg = (
                    f"המוצר נוסף לסל, המחיר הכולל עבור מוצר זה הינו {format_price(item_total)} שקלים, "
                    f"סך הכל בסל הקניות {format_price(cart_total)} שקלים. "
                    "למוצר הבא הקישו 1, לבחירת קטגוריה אחרת הקישו 2, למעבר לתשלום הקישו 9, לחזרה למוצר הקישו כוכבית"
                )
                return yemot_read(msg, "after_add_choice", opts_menu(), "022g")
            except ValueError:
                log_step(call_id, phone, step, raw_user_input, "קלט כמות לא מספרי")
                return yemot_read("הקשה שגויה, אנא הקש כמות במספרים בלבד ולאחר מכן סולמית, לחזרה הקישו כוכבית וסולמית", "qty_input", opts_digits_no_confirm(3, 1, 7, allow_star=True), "021")

        elif step == "AFTER_ADD_MENU":
            if is_back:
                log_step(call_id, phone, step, "*", "חזרה למוצר")
                return play_current_product(session)
            if user_input == "9":
                log_step(call_id, phone, step, "9", "מעבר לתשלום")
                return initiate_checkout(session)
            elif user_input == "1":
                session["product_index"] = (session["product_index"] + 1) % len(session["filtered_products"])
                log_step(call_id, phone, step, "1", "מעבר למוצר הבא")
                return play_current_product(session)
            elif user_input == "2":
                log_step(call_id, phone, step, "2", "חזרה לקטגוריות")
                return show_categories(session)
            else:
                return yemot_read("הקשה שגויה, למוצר הבא הקישו 1, לקטגוריה אחרת הקישו 2, לתשלום הקישו 9, לחזרה הקישו כוכבית", "after_add_choice", opts_menu(), "022g")

        elif step == "CONFIRM_CHECKOUT_FEE":
            if is_back:
                log_step(call_id, phone, step, "*", "חזרה לתפריט ההזמנות")
                return show_categories(session)
            if user_input == "1":
                return finish_checkout(session, background_tasks)
            elif user_input == "2":
                session["cart"] = []
                user = session.get("user") or {}
                user_id = get_user_id(user) or phone
                delete_abandoned_cart(user_id=user_id, phone=phone)
                log_step(call_id, phone, step, "2", "הזמנה בוטלה והסל נוקה")
                return show_categories(session, prefix="ההזמנה בוטלה, ")
            else:
                return initiate_checkout(session)

        # ---------------------------------------------------------
        # אזור אישי: תפריט, עדכון פרטים סדרתי והיסטוריית עסקאות
        # ---------------------------------------------------------
        elif step == "PERSONAL_AREA_MENU":
            if is_back or user_input == "9":
                log_step(call_id, phone, step, user_input, "חזרה לתפריט ראשי")
                return show_welcome(session, return_to_root=from_tzintuk_endpoint)
            if user_input == "1":
                if not session.get("user"):
                    session["auth_target"] = "PERSONAL_UPDATE"
                    session["step"] = "LOGIN_ID"
                    log_step(call_id, phone, step, "1", "עדכון פרטים ➔ בקשת ת.ז לזיהוי")
                    return yemot_read("לעדכון פרטים אנא הקישו תעודת זהות בת 8 עד 9 ספרות ולאחר מכן סולמית, לחזרה הקישו כוכבית וסולמית", "login_id", opts_digits_confirm(9, 1, 7, allow_star=True), "003")
                log_step(call_id, phone, step, "1", "עדכון פרטים ➔ מעבר לשם")
                return show_update_field_step(session, "UPD_NAME_MENU")
            elif user_input == "2":
                if not session.get("user"):
                    session["auth_target"] = "TX_HISTORY"
                    session["step"] = "LOGIN_ID"
                    log_step(call_id, phone, step, "2", "היסטוריית עסקאות ➔ בקשת ת.ז לזיהוי")
                    return yemot_read("לצפייה בהיסטוריית עסקאות אנא הקישו תעודת זהות בת 8 עד 9 ספרות ולאחר מכן סולמית, לחזרה הקישו כוכבית וסולמית", "login_id", opts_digits_confirm(9, 1, 7, allow_star=True), "003")
                log_step(call_id, phone, step, "2", "הצגת 10 עסקאות אחרונות")
                return show_tx_history_list(session)
            elif user_input == "3":
                log_step(call_id, phone, step, "3", "מעבר לשלוחה /1/3 (הודעות מהגבאי)")
                return Response(content="go_to_folder=/1/3", media_type="text/plain; charset=utf-8")
            elif user_input == "4":
                log_step(call_id, phone, step, "4", "רישום ראשוני מתוך אזור אישי")
                return start_registration(session, return_to="PERSONAL_AREA_MENU")
            else:
                return show_personal_area_menu(session, prefix="הקשה שגויה, ")

        elif step == "UPD_NAME_MENU":
            if is_back:
                return show_personal_area_menu(session)
            if user_input == "1":
                session["step"] = "UPD_NAME_REC"
                return yemot_read_record("אנא אמרו בקול ברור את השם המעודכן ולאחר מכן הקישו סולמית", "upd_name_rec", "", "005", skip_menu=True)
            elif user_input == "2":
                return show_update_field_step(session, "UPD_CITY_MENU")
            return show_update_field_step(session, "UPD_NAME_MENU", prefix="הקשה שגויה, ")

        elif step == "UPD_NAME_REC":
            text = transcribe_audio_file_from_yemot(raw_user_input, token)
            if not text:
                return yemot_read_record("לא הצלחנו לפענח, אנא אמרו שוב את השם ולאחר מכן סולמית", "upd_name_rec", "", "006", skip_menu=True)
            session["reg_data"]["temp_upd_name"] = text
            session["step"] = "UPD_NAME_CONFIRM"
            return yemot_read(f"השם שנקלט הוא {clean_tts(text)}. לאישור הקישו 1, להקלטה מחדש הקישו 2, לחזרה הקישו כוכבית", "upd_name_confirm", opts_menu())

        elif step == "UPD_NAME_CONFIRM":
            if is_back:
                return show_update_field_step(session, "UPD_NAME_MENU")
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
            return yemot_read_record("אנא אמרו בקול ברור את השם המעודכן ולאחר מכן הקישו סולמית", "upd_name_rec", "", "005", skip_menu=True)

        elif step == "UPD_CITY_MENU":
            if is_back:
                return show_update_field_step(session, "UPD_NAME_MENU")
            if user_input == "1":
                return show_cities_menu(session, "UPD_CITY_SELECT", "upd_city_select")
            elif user_input == "2":
                return show_update_field_step(session, "UPD_ADDR_MENU")
            return show_update_field_step(session, "UPD_CITY_MENU", prefix="הקשה שגויה, ")

        elif step == "UPD_CITY_SELECT":
            if is_back:
                return show_update_field_step(session, "UPD_CITY_MENU")
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
            if is_back:
                return show_update_field_step(session, "UPD_CITY_MENU")
            if user_input == "1":
                session["step"] = "UPD_ADDR_REC"
                return yemot_read_record("אנא אמרו בקול ברור את הרחוב ומספר הבית המעודכנים ללא שם העיר ולאחר מכן הקישו סולמית", "upd_addr_rec", "", "010", skip_menu=True)
            elif user_input == "2":
                return show_update_field_step(session, "UPD_PHONE_MENU")
            return show_update_field_step(session, "UPD_ADDR_MENU", prefix="הקשה שגויה, ")

        elif step == "UPD_ADDR_REC":
            text = transcribe_audio_file_from_yemot(raw_user_input, token)
            if not text:
                return yemot_read_record("לא הצלחנו לפענח, אנא אמרו שוב את הרחוב ומספר הבית ללא שם העיר ולאחר מכן סולמית", "upd_addr_rec", "", "011", skip_menu=True)
            session["reg_data"]["temp_upd_addr"] = text
            session["step"] = "UPD_ADDR_CONFIRM"
            return yemot_read(f"הכתובת שנקלטה היא {clean_tts(text)}. לאישור הקישו 1, להקלטה מחדש הקישו 2, לחזרה הקישו כוכבית", "upd_addr_confirm", opts_menu())

        elif step == "UPD_ADDR_CONFIRM":
            if is_back:
                return show_update_field_step(session, "UPD_ADDR_MENU")
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
            return yemot_read_record("אנא אמרו בקול ברור את הרחוב ומספר הבית המעודכנים ללא שם העיר ולאחר מכן הקישו סולמית", "upd_addr_rec", "", "010", skip_menu=True)

        elif step == "UPD_PHONE_MENU":
            if is_back:
                return show_update_field_step(session, "UPD_ADDR_MENU")
            if user_input == "1":
                session["step"] = "UPD_PHONE_INPUT"
                return yemot_read("אנא הקישו מספר טלפון מעודכן בן 9 עד 10 ספרות ולאחר מכן סולמית. לבחירת המספר ממנו אתם מחייגים הקישו 1 וסולמית, לחזרה הקישו כוכבית וסולמית", "upd_phone_input", opts_digits_confirm(10, 1, 7, allow_star=True), "009")
            elif user_input == "2":
                return show_update_field_step(session, "UPD_COMMUNITY_MENU")
            return show_update_field_step(session, "UPD_PHONE_MENU", prefix="הקשה שגויה, ")

        elif step == "UPD_PHONE_INPUT":
            if is_back:
                return show_update_field_step(session, "UPD_PHONE_MENU")
            new_phone = user_input
            if user_input == "1":
                if phone and phone.isdigit() and len(phone) >= 9:
                    new_phone = phone
                else:
                    return yemot_read("המספר ממנו אתם מחייגים אינו מזוהה. אנא הקישו ידנית מספר בן 9 עד 10 ספרות ולאחר מכן סולמית, לחזרה הקישו כוכבית וסולמית", "upd_phone_input", opts_digits_confirm(10, 1, 7, allow_star=True), "009")
            elif not user_input or not user_input.isdigit() or len(user_input) < 9 or len(user_input) > 10:
                return yemot_read("מספר לא תקין, הקישו מספר טלפון בן 9 עד 10 ספרות או 1 וסולמית למספר המחייג, לחזרה הקישו כוכבית וסולמית", "upd_phone_input", opts_digits_confirm(10, 1, 7, allow_star=True), "009")

            user = session["user"]
            user["phone"] = new_phone
            user["מספר טלפון"] = new_phone
            sync_user_in_cache(user)
            background_tasks.add_task(update_user_in_sheet, dict(user))
            log_step(call_id, phone, step, new_phone, "טלפון עודכן")
            return show_update_field_step(session, "UPD_COMMUNITY_MENU", prefix="הטלפון עודכן בהצלחה, ")

        elif step == "UPD_COMMUNITY_MENU":
            if is_back:
                return show_update_field_step(session, "UPD_PHONE_MENU")
            if user_input == "1":
                session["step"] = "UPD_COMMUNITY_INPUT"
                return yemot_read("אנא הקישו קוד קהילה חדש ולאחר מכן סולמית, לחזרה הקישו כוכבית וסולמית", "upd_comm_input", opts_digits_confirm(9, 1, 7, allow_star=True), "015")
            elif user_input == "2":
                return show_update_field_step(session, "UPD_PASS_MENU")
            return show_update_field_step(session, "UPD_COMMUNITY_MENU", prefix="הקשה שגויה, ")

        elif step == "UPD_COMMUNITY_INPUT":
            if is_back:
                return show_update_field_step(session, "UPD_COMMUNITY_MENU")

            is_valid_code, comm_name_or_err = validate_community_code(user_input)
            if not is_valid_code:
                return yemot_read("קוד הקהילה שהוקש אינו מוכר או שאינו פעיל במערכת. אנא הקישו שוב ולאחר מכן סולמית, או הקישו כוכבית וסולמית לחזרה", "upd_comm_input", opts_digits_confirm(9, 1, 7, allow_star=True), "015")

            user = session["user"]
            norm_c = normalize_code(user_input)
            user["community_code"] = norm_c
            user["קוד קהילה"] = norm_c
            sync_user_in_cache(user)
            background_tasks.add_task(update_user_in_sheet, dict(user))
            log_step(call_id, phone, step, norm_c, f"קוד קהילה עודכן בהצלחה ({comm_name_or_err})")
            return show_update_field_step(session, "UPD_PASS_MENU", prefix=f"קוד הקהילה עודכן בהצלחה ושויכתם ל{clean_tts(comm_name_or_err)}, ")

        elif step == "UPD_PASS_MENU":
            if is_back:
                return show_update_field_step(session, "UPD_COMMUNITY_MENU")
            if user_input == "1":
                session["step"] = "UPD_PASS_INPUT"
                return yemot_read("אנא הקישו סיסמא חדשה בת 6 עד 10 ספרות ולאחר מכן סולמית, לחזרה הקישו כוכבית וסולמית", "upd_pass_input", opts_digits_confirm(10, 1, 7, allow_star=True))
            elif user_input == "2":
                return show_update_field_step(session, "UPD_TZINTUK_MENU")
            return show_update_field_step(session, "UPD_PASS_MENU", prefix="הקשה שגויה, ")

        elif step == "UPD_PASS_INPUT":
            if is_back:
                return show_update_field_step(session, "UPD_PASS_MENU")
            if not user_input or not user_input.isdigit() or len(user_input) < 6 or len(user_input) > 10:
                return yemot_read("סיסמא חייבת להיות בת 6 עד 10 ספרות, אנא הקישו שנית ולאחר מכן סולמית, לחזרה הקישו כוכבית וסולמית", "upd_pass_input", opts_digits_confirm(10, 1, 7, allow_star=True))
            user = session["user"]
            user["password"] = user_input
            user["סיסמא"] = user_input
            sync_user_in_cache(user)
            background_tasks.add_task(update_user_in_sheet, dict(user))
            log_step(call_id, phone, step, "******", "סיסמא עודכנה")
            return show_update_field_step(session, "UPD_TZINTUK_MENU", prefix="הסיסמא עודכנה בהצלחה, ")

        elif step == "UPD_TZINTUK_MENU":
            if is_back:
                return show_update_field_step(session, "UPD_PASS_MENU")
            if user_input == "1":
                user = session["user"]
                user["personal_tzintuk"] = "TRUE"
                sync_user_in_cache(user)
                background_tasks.add_task(update_user_in_sheet, dict(user))
                return redirect_to_tzintuk_c(session, call_id, phone, "UPD", request)
            elif user_input == "2":
                return show_personal_area_menu(session, prefix="עדכון הפרטים הסתיים, ")
            return show_update_field_step(session, "UPD_TZINTUK_MENU", prefix="הקשה שגויה, ")

        # --- היסטוריית עסקאות ---
        elif step == "TX_HISTORY_LIST":
            if is_back or user_input == "9":
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
                        "לחזרה לרשימת העסקאות הקישו 1 או כוכבית, לחזרה לאזור האישי הקישו 2"
                    )
                    return yemot_read(detail_msg, "tx_detail_choice", opts_menu())
                return show_tx_history_list(session, prefix="הקשה שגויה, ")
            except ValueError:
                return show_tx_history_list(session, prefix="הקשה שגויה, ")

        elif step == "TX_HISTORY_DETAIL":
            if is_back or user_input == "1":
                return show_tx_history_list(session)
            return show_personal_area_menu(session)

        # ---------------------------------------------------------
        # שלוחה 5: השארת הודעה לגבאי
        # ---------------------------------------------------------
        elif step == "GABAI_AUTH_ID":
            if is_back:
                return show_welcome(session, return_to_root=from_tzintuk_endpoint)
            if user_input == "0":
                session["step"] = "GABAI_RECORD_MSG"
                log_step(call_id, phone, step, "0", "דילוג על זיהוי ➔ הקלטה לגבאי (/5)")
                return yemot_read_record("אנא השאירו את הודעתכם לגבאי ולאחר מכן הקישו סולמית", "gabai_msg", "/5", skip_menu=False)

            if user_input in CACHE["users"]:
                user = CACHE["users"][user_input]
                session["user"] = user
                if is_user_personal_tzintuk(user):
                    session["step"] = "GABAI_RECORD_MSG"
                    log_step(call_id, phone, step, user_input, "משתמש רשום לצינתוק אישי ➔ הקלטה לגבאי (/5)")
                    return yemot_read_record("אנא השאירו את הודעתכם לגבאי ולאחר מכן הקישו סולמית", "gabai_msg", "/5", skip_menu=False)
                session["step"] = "GABAI_TZINTUK_PROMPT"
                log_step(call_id, phone, step, user_input, "משתמש לא רשום לצינתוק אישי ➔ הצעת רישום")
                return yemot_read("שימו לב, אינכם רשומים באזור האישי לקבלת צינתוק אישי בעת קבלת תשובה. לרישום לצינתוק אישי הקישו 1, להמשך השארת הודעה לגבאי הקישו 2, לחזרה הקישו כוכבית", "gabai_tzintuk_choice", opts_menu())
            session["step"] = "GABAI_TZINTUK_PROMPT"
            return yemot_read("אינכם מזוהים כרשומים לצינתוק אישי. לרישום לצינתוק אישי הקישו 1, להשארת הודעה לגבאי הקישו 2, לחזרה הקישו כוכבית", "gabai_tzintuk_choice", opts_menu())

        elif step == "GABAI_TZINTUK_PROMPT":
            if is_back:
                return show_welcome(session, return_to_root=from_tzintuk_endpoint)
            if user_input == "1":
                user = session.get("user")
                if user:
                    user["personal_tzintuk"] = "TRUE"
                    sync_user_in_cache(user)
                    background_tasks.add_task(update_user_in_sheet, dict(user))
                return redirect_to_tzintuk_c(session, call_id, phone, "GABAI", request)
            elif user_input == "2":
                session["step"] = "GABAI_RECORD_MSG"
                log_step(call_id, phone, step, "2", "הקלטה לגבאי ללא צינתוק (/5)")
                return yemot_read_record("אנא השאירו את הודעתכם לגבאי ולאחר מכן הקישו סולמית", "gabai_msg", "/5", skip_menu=False)
            return yemot_read("הקשה שגויה, לרישום לצינתוק אישי הקישו 1, להמשך השארת הודעה הקישו 2, לחזרה הקישו כוכבית", "gabai_tzintuk_choice", opts_menu())

        elif step == "GABAI_RECORD_MSG":
            if not raw_user_input:
                return yemot_read_record("אנא השאירו את הודעתכם לגבאי ולאחר מכן הקישו סולמית", "gabai_msg", "/5", skip_menu=False)

            log_step(call_id, phone, step, raw_user_input, "הודעה נשמרה ב-/5 ונשלחת למייל הגבאי")
            background_tasks.add_task(process_gabai_message, raw_user_input, phone, session.get("user"), token)
            background_tasks.add_task(log_general_event, call_id, phone, "הודעה לגבאי", f"נשמרה ב-/5 ונשלחה למייל: {raw_user_input}")
            return show_welcome(session, prefix="הודעתכם נשמרה במערכת ונשלחה למייל הגבאי בהצלחה, ", return_to_root=from_tzintuk_endpoint)

        return yemot_msg("אירעה שגיאה במערכת, השיחה תנותק")

    except Exception as e:
        print(f"[CRITICAL ERROR] {e}\n{traceback.format_exc()}", flush=True)
        return show_welcome(SESSIONS.get(call_id, {}), prefix="אירעה שגיאה זמנית, ")
