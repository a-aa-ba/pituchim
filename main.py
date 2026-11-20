import os
import io
import json
import hashlib
import hmac
import secrets
import requests
import subprocess
import traceback
import urllib.parse
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import Response
import imageio_ffmpeg
import speech_recognition as sr

app = FastAPI(title="Yemot Sales IVR System")

# ===================================================================
# 1. ניהול פתיחה וסגירה של המכירות
# ההגדרות נשמרות בגיליון Google Sheets נפרד ומנוהלות דרך ממשק הגיליון.
SALES_CONTROL_URL = os.environ.get("SALES_CONTROL_URL", "").strip()
SALES_CONTROL_KEY = os.environ.get("SALES_CONTROL_KEY", "").strip()
REFRESH_CACHE_KEY = os.environ.get("REFRESH_CACHE_KEY", "").strip()
SALES_CONTROL_CACHE = {
    "sales_open": False,
    "exceptions": set(),
    "password_hashes": {},
    "loaded": False
}

def normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if digits.startswith("972") and len(digits) >= 11:
        digits = "0" + digits[3:]
    return digits

def load_sales_control() -> bool:
    """טעינת מצב המכירות והחריגים מגיליון הניהול."""
    if not SALES_CONTROL_URL or not SALES_CONTROL_KEY:
        print("LOG: הגדרות ניהול המכירות חסרות; המכירות נשארות סגורות כברירת מחדל", flush=True)
        return False
    try:
        response = requests.get(
            SALES_CONTROL_URL,
            params={"key": SALES_CONTROL_KEY},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        if (
            not isinstance(data.get("sales_open"), bool)
            or not isinstance(data.get("exceptions"), list)
            or not isinstance(data.get("password_hashes", {}), dict)
        ):
            raise ValueError("מבנה נתוני ניהול המכירות אינו תקין")
        SALES_CONTROL_CACHE["sales_open"] = data["sales_open"]
        SALES_CONTROL_CACHE["exceptions"] = {
            normalize_phone(phone) for phone in data["exceptions"] if normalize_phone(phone)
        }
        SALES_CONTROL_CACHE["password_hashes"] = {
            str(user_id).strip(): str(password_hash).strip()
            for user_id, password_hash in data.get("password_hashes", {}).items()
            if str(user_id).strip() and str(password_hash).startswith("pbkdf2_sha256$")
        }
        SALES_CONTROL_CACHE["loaded"] = True
        print(
            f"LOG: הגדרות מכירות נטענו בהצלחה; פתוח={data['sales_open']}, "
            f"מספר חריגים={len(SALES_CONTROL_CACHE['exceptions'])}",
            flush=True
        )
        return True
    except Exception as error:
        print(f"LOG ERROR בטעינת הגדרות המכירות: {error}", flush=True)
        return False


def is_sales_entry_allowed(session: dict) -> bool:
    """בדיקה מקומית בזיכרון בלבד; אין כאן פנייה ל-Google Sheets."""
    if SALES_CONTROL_CACHE.get("sales_open", False):
        return True
    caller = normalize_phone(session.get("phone", ""))
    return bool(caller and caller in SALES_CONTROL_CACHE.get("exceptions", set()))

def sales_closed_response() -> Response:
    return yemot_msg("מערכת ההזמנות סגורה כעת. נא לנסות מאוחר יותר.")

def password_is_valid(password: str) -> bool:
    return password.isdigit() and 6 <= len(password) <= 10

def hash_user_password(password: str) -> str:
    salt = secrets.token_hex(16)
    iterations = 310000
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    ).hex()
    return "pbkdf2_sha256$" + str(iterations) + "$" + salt + "$" + digest

def verify_user_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, iterations_text, salt_hex, expected_digest = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        if iterations < 100000 or iterations > 1000000:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), iterations
        ).hex()
        return hmac.compare_digest(actual, expected_digest)
    except (ValueError, TypeError):
        return False

def save_password_hash_to_sales_control(id_number: str, password_hash: str):
    if not SALES_CONTROL_URL or not SALES_CONTROL_KEY:
        print("LOG ERROR: חסרים פרטי חיבור לשמירת סיסמה בגיליון", flush=True)
        return False
    try:
        response = requests.post(
            SALES_CONTROL_URL,
            json={
                "key": SALES_CONTROL_KEY,
                "action": "set_password",
                "id_number": str(id_number),
                "password_hash": str(password_hash)
            },
            timeout=15
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("ok"):
            raise ValueError("Google Sheets rejected password update")
        return True
    except Exception as error:
        print(f"LOG ERROR בשמירת hash סיסמה: {error}", flush=True)
        return False

# 2. שימוש בקובצי שמע מוקלטים (אם קובץ שמע חסר בתיקייה, ישתמש ב-TTS אוטומטית)
USE_AUDIO_FILES = True
AUDIO_FOLDER = "הודעות מערכת"
AUDIO_FILE_EXISTS_CACHE = {}
# ===================================================================

# הגדרות סליקה וטוקן ימות המשיח
YEMOT_TOKEN = "0795322222:123456"
APPS_SCRIPT_URL = "https://script.google.com/macros/s/AKfycbx7Uk7ltg9ZmaLKbh_SBrt1y_dQIMBmPbkhOSA0zEn4Ls77HXgghwGaiLMiln7chcQmfA/exec"

# הגדרות סליקת אשראי (ברירת מחדל: נדרים פלוס, תשלום 1 בלבד)
CREDIT_CARD_PROVIDER = "nedarim_plus"
CREDIT_CARD_REGISTER_NO = "4001388"
CREDIT_CARD_MAX_PAYMENTS = "1"  # תשלום 1 בלבד
CREDIT_CARD_CURRENCY = os.environ.get("CREDIT_CARD_CURRENCY", "1")  # 1 = שקל

CACHE = {
    "users": {},
    "categories": [],
    "products": []
}

SESSIONS: Dict[str, Dict[str, Any]] = {}
SAVED_CARTS: Dict[str, list] = {}  # שמירת סלי קניות פתוחים של משתמשים

STEP_PARAM_MAP = {
    "WELCOME": ["welcome_choice", "ApiRealAnswer"],
    "AUTH": ["auth_id", "ApiRealAnswer"],
    "AUTH_PASSWORD": ["auth_password", "ApiRealAnswer"],
    "SET_PASSWORD": ["set_password", "ApiRealAnswer"],
    "SET_PASSWORD_CONFIRM": ["set_password_confirm", "ApiRealAnswer"],
    "NOT_AUTHORIZED_CHOICE": ["unauth_choice", "ApiRealAnswer"],
    "REG_ID": ["reg_id", "ApiRealAnswer"],
    "REG_ID_CONFIRM": ["reg_id_confirm_choice", "ApiRealAnswer"],
    "REG_PHONE": ["reg_phone", "ApiRealAnswer"],
    "REG_PHONE_CONFIRM": ["reg_phone_confirm_choice", "ApiRealAnswer"],
    "REG_NAME": ["reg_name", "my_rec", "ApiRealAnswer"],
    "REG_NAME_CONFIRM": ["reg_name_confirm_choice", "ApiRealAnswer"],
    "REG_ADDRESS": ["reg_address", "my_rec", "ApiRealAnswer"],
    "REG_ADDRESS_CONFIRM": ["reg_address_confirm_choice", "ApiRealAnswer"],
    "REG_COMMUNITY_CODE": ["reg_community_code", "ApiRealAnswer"],
    "REG_COMMUNITY_CODE_CONFIRM": ["reg_community_code_confirm_choice", "ApiRealAnswer"],
    "REG_ALERTS_CHOICE": ["reg_alerts_choice", "ApiRealAnswer"],
    "REG_FINISH": ["reg_finish_choice", "ApiRealAnswer"],
    "PERSONAL_AREA": ["personal_choice", "ApiRealAnswer"],
    "UPDATE_COMMUNITY_CODE": ["new_community_code", "ApiRealAnswer"],
    "RESTORE_CART_CHOICE": ["restore_cart_choice", "ApiRealAnswer"],
    "MAIN_MENU": ["cat_choice", "ApiRealAnswer"],
    "KASHRUT_MENU": ["kashrut_choice", "ApiRealAnswer"],
    "PRODUCT_LOOP": ["product_choice", "ApiRealAnswer"],
    "CATALOG_LOOP": ["catalog_choice", "ApiRealAnswer"],
    "QTY_INPUT": ["qty_input", "ApiRealAnswer"],
    "AFTER_ADD_MENU": ["after_add_choice", "ApiRealAnswer"],
    "CONFIRM_CHECKOUT_FEE": ["checkout_confirm_choice", "ApiRealAnswer"]
}

PROMPT_FILE_MAP = {
    "welcome_choice": "001",
    "auth_id": "003",
    "auth_password": "029",
    "set_password": "030",
    "set_password_confirm": "031",
    "unauth_choice": "004",
    "reg_name": "005",
    "reg_id": "007",
    "reg_id_confirm_choice": "032",
    "reg_phone": "009",
    "reg_phone_confirm_choice": "033",
    "reg_address": "010",
    "reg_community_code": "012",
    "reg_community_code_confirm_choice": "034",
    "reg_alerts_choice": "035",
    "reg_finish_choice": "036",
    "personal_choice": "014d",
    "new_community_code": "015",
    "cat_choice": "017b",
    "kashrut_choice": "017b",
    "catalog_choice": "018f",
    "qty_input": "020a",
    "product_choice": "022f",
    "after_add_choice": "022g",
    "checkout_confirm_choice": "023b",
    "restore_cart_choice": "026"
}

# -------------------------------------------------------------------
# 1. המרת שמע + פילטרים לניקוי רעשים ואיזון עוצמה (FFmpeg)
# -------------------------------------------------------------------
def convert_audio_to_pcm_wav(input_path, output_path):
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
        print(f"LOG ERROR בהמרת FFmpeg: {e}", flush=True)
        return False

# -------------------------------------------------------------------
# 2. הורדת הקובץ מימות המשיח + תמלול בעברית
# -------------------------------------------------------------------
def transcribe_audio_file_from_yemot(my_rec_path: str, token: str = None) -> str:
    print(f"\n=======================================================", flush=True)
    print(f"LOG [תמלול שמע]: התקבל נתיב להקלטה מימות המשיח: '{my_rec_path}'", flush=True)
    print(f"=======================================================", flush=True)

    if not my_rec_path or not isinstance(my_rec_path, str):
        print("LOG ERROR: נתיב הקלטה ריק או לא תקין", flush=True)
        return ""

    active_token = (token or YEMOT_TOKEN or "").strip()
    print(f"LOG [תמלול שמע]: עושה שימוש בטוקן: '{active_token}'", flush=True)

    raw_path = str(my_rec_path).strip()
    clean_path = raw_path.replace("Digits-", "").replace("val_name-", "").strip()
    if clean_path.startswith("ivr2:"):
        clean_path = clean_path[5:]
    clean_path = "/" + clean_path.lstrip('/')

    possible_paths = [
        f"ivr2:{clean_path}",
        f"ivr2:{raw_path}",
        clean_path,
        clean_path.lstrip('/')
    ]

    unique_paths = []
    for p in possible_paths:
        if p not in unique_paths:
            unique_paths.append(p)

    res = None
    for try_path in unique_paths:
        encoded_path = urllib.parse.quote(try_path, safe=':/')
        audio_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={active_token}&path={encoded_path}"
        
        try:
            r = requests.get(audio_url, timeout=10)
            if r.status_code == 200 and len(r.content) >= 100 and not r.content.startswith(b'<') and not r.content.startswith(b'{'):
                res = r
                print(f"LOG [תמלול שמע]: הורדת קובץ שמע הצליחה בנתיב: {try_path}", flush=True)
                break
        except Exception as err:
            print(f"LOG ERROR [תמלול שמע]: שגיאה בחיבור בנתיב {try_path}: {err}", flush=True)

    if not res:
        print(f"LOG ERROR [תמלול שמע]: כל ניסיונות ההורדה נכשלו עבור הקובץ '{my_rec_path}'. וודא שהטוקן תקין והקובץ קיים במערכת.", flush=True)
        return ""

    temp_audio = f"downloaded_{os.getpid()}.file"
    converted_wav = f"converted_{os.getpid()}.wav"

    try:
        with open(temp_audio, "wb") as f:
            f.write(res.content)

        if not convert_audio_to_pcm_wav(temp_audio, converted_wav):
            target_wav = temp_audio
        else:
            target_wav = converted_wav

        recognizer = sr.Recognizer()
        with sr.AudioFile(target_wav) as source:
            audio_data = recognizer.record(source)
            
            try:
                text = recognizer.recognize_google(audio_data, language='he-IL')
                print(f"=====> תוצאת התמלול שהתקבלה מ-Google: '{text}' <=====", flush=True)
                return text.strip() if text else ""
            except sr.UnknownValueError:
                print("=====> תוצאת התמלול: [לא הצליח לזהות מילים / הקלטה שקטה/לא ברורה] <=====", flush=True)
                return ""
            except sr.RequestError as e:
                print(f"LOG ERROR [תמלול שמע]: SpeechRecognition שגיאת תקשורת: {e}", flush=True)
                return ""

    except Exception as e:
        print(f"LOG ERROR בתהליך תמלול השמע: {e}\n{traceback.format_exc()}", flush=True)
        return ""
    finally:
        if os.path.exists(temp_audio):
            try: os.remove(temp_audio)
            except: pass
        if os.path.exists(converted_wav):
            try: os.remove(converted_wav)
            except: pass

# -------------------------------------------------------------------
# 3. פונקציות עזר לניקוי וטעינת נתונים
# -------------------------------------------------------------------
def clean_input(val: str) -> str:
    if not val:
        return ""
    val = str(val).strip()
    val = val.replace("#", "").replace("*", "")
    if val.startswith("Digits-"):
        val = val.replace("Digits-", "")
    return val.strip()

def clean_tts(text: str) -> str:
    if not text:
        return ""
    text = str(text)
    text = text.replace(".", " ")
    text = text.replace("-", " ")
    text = text.replace('"', "")
    text = text.replace("'", "")
    text = text.replace("=", " ")
    return text.strip()

def get_field(item: dict, *keys, default=""):
    if not item or not isinstance(item, dict):
        return default
    for k in keys:
        if k in item and item[k] is not None and str(item[k]).strip() != "":
            return item[k]
    return default

def load_data_from_sheets():
    if not APPS_SCRIPT_URL:
        return
        
    try:
        response = requests.get(APPS_SCRIPT_URL, timeout=10)
        data = response.json()
        
        users_dict = {}
        for u in data.get("users", []):
            is_active = str(get_field(u, "פעיל", "is_active", default="TRUE")).upper()
            if is_active in ["TRUE", "1", "YES"]:
                id_num = str(get_field(u, "תעודת זהות", "id_number")).strip()
                phone = str(get_field(u, "מספר טלפון", "phone")).strip()
                if id_num:
                    users_dict[id_num] = u
                if phone:
                    users_dict[phone] = u
        CACHE["users"] = users_dict
        
        cats = []
        for c in data.get("categories", []):
            cats.append({
                "category_id": get_field(c, "מזהה קטגוריה", "category_id"),
                "category_name": get_field(c, "שם קטגוריה", "category_name"),
                "kashruts": get_field(c, "כשרויות זמינות", "kashruts")
            })
        CACHE["categories"] = cats
        
        prods = []
        for p in data.get("products", []):
            in_stock = str(get_field(p, "במלאי", "in_stock", default="TRUE")).upper()
            if in_stock in ["TRUE", "1", "YES"]:
                prods.append({
                    "sku": str(get_field(p, "מקט", "sku")),
                    "name": get_field(p, "שם מוצר", "name"),
                    "price": get_field(p, "מחיר ליחידה", "price"),
                    "notes": get_field(p, "הערות", "notes"),
                    "category_name": get_field(p, "קטגוריה", "category_name"),
                    "kashrut": get_field(p, "כשרות", "kashrut")
                })
        CACHE["products"] = prods
    except Exception as e:
        print(f" Error loading data: {e}", flush=True)

@app.on_event("startup")
async def startup_event():
    load_data_from_sheets()
    load_sales_control()

@app.get("/refresh-cache")
async def refresh_cache(request: Request):
    supplied_key = request.headers.get("x-refresh-key", "")
    if not REFRESH_CACHE_KEY or supplied_key != REFRESH_CACHE_KEY:
        return Response(content="Forbidden", status_code=403, media_type="text/plain")

    load_data_from_sheets()
    sales_control_loaded = load_sales_control()
    return Response(
        content=json.dumps({
            "status": "success",
            "message": "Cache refreshed",
            "ניהול_מכירות_נטען": sales_control_loaded,
            "המכירות_פתוחות": SALES_CONTROL_CACHE["sales_open"]
        }, ensure_ascii=False),
        media_type="application/json"
    )

def log_general_event(call_id: str, phone: str, event_type: str, details: str):
    if not APPS_SCRIPT_URL:
        return
    try:
        payload = {
            "type": "general_log",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "call_id": str(call_id),
            "phone": str(phone),
            "event_type": event_type,
            "details": details
        }
        requests.post(APPS_SCRIPT_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=10)
    except Exception as e:
        pass

def save_new_user_to_sheet(user_data: dict, password_hash: str = ""):
    """שומר את פרטי הנרשם. סיסמה נשמרת רק אם נמסר hash."""
    if not APPS_SCRIPT_URL:
        print("LOG ERROR: חסרה כתובת Apps Script לשמירת משתמש", flush=True)
        return False
    try:
        payload = {
            "type": "register_user",
            "id_number": str(user_data.get("id_number", "")),
            "phone": str(user_data.get("phone", "")),
            "first_name": str(user_data.get("first_name", "")),
            "last_name": "",
            "address": str(user_data.get("address", "")),
            "community_code": str(user_data.get("community_code", ""))
        }
        res = requests.post(
            APPS_SCRIPT_URL, data=json.dumps(payload),
            headers={"Content-Type": "application/json"}, timeout=15
        )
        res.raise_for_status()
        print(f"LOG: User register sheet response [Code {res.status_code}]", flush=True)
        if password_hash and not save_password_hash_to_sales_control(str(user_data.get("id_number", "")), password_hash):
            print("LOG ERROR: המשתמש נשמר אך שמירת הסיסמה נכשלה", flush=True)
            return False
        return True
    except Exception as e:
        print(f"LOG ERROR registering user: {e}", flush=True)
        return False

def persist_registration(session: dict, background_tasks: BackgroundTasks) -> dict:
    """שומר נרשם פעם אחת בזיכרון וב-Sheets, לפני כל ניתוב לשלוחה חיצונית."""
    data = session.setdefault("reg_data", {})
    id_number = str(data.get("id_number", "")).strip()
    phone = str(data.get("phone", "")).strip()
    user = {
        "id_number": id_number,
        "phone": phone,
        "first_name": str(data.get("first_name", "")).strip(),
        "last_name": "",
        "address": str(data.get("address", "")).strip(),
        "community_code": str(data.get("community_code", "")).strip(),
        "is_active": "TRUE"
    }
    if not session.get("registration_saved"):
        CACHE["users"][id_number] = user
        CACHE["users"][phone] = user
        session["user"] = user
        session["authenticated_id"] = id_number
        session["registration_saved"] = True
        background_tasks.add_task(save_new_user_to_sheet, data, "")
        background_tasks.add_task(
            log_general_event,
            session.get("call_id", ""),
            session.get("phone", ""),
            "הרשמה הושלמה",
            "משתמש חדש נרשם; פרטי רישום נשמרו ללא הגדרת סיסמה"
        )
    else:
        session["user"] = user
    return user

def log_transaction_to_sheet(session_data: dict):
    if not APPS_SCRIPT_URL:
        return
    try:
        user = session_data.get("user", {})
        cart = session_data.get("cart", [])
        items_summary = "; ".join([f"{item['name']} מקט {item['sku']} כמות {item['qty']} סך הכל {item['total']} שח" for item in cart])
        total_sum = session_data.get("total_sum_with_fee", sum(item['total'] for item in cart) + 10)
        
        first_name = get_field(user, "שם פרטי ומשפחה", "שם פרטי", "first_name")
        last_name = get_field(user, "שם משפחה", "last_name")
        user_id = get_field(user, "תעודת זהות", "id_number") or get_field(user, "מספר טלפון", "phone")
        
        payload = {
            "type": "transaction",
            "transaction_id": str(session_data.get("call_id")),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "user_identifier": str(user_id),
            "user_name": f"{first_name} {last_name}".strip(),
            "items_detail": items_summary,
            "total_amount": total_sum,
            "status": "אומת לפני סליקה"
        }
        requests.post(APPS_SCRIPT_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=10)
    except Exception as e:
        pass

def get_prompt_file_num(text: str, var_name: str) -> str:
    if "סגורה כעת" in text:
        return "002"
    if "לא הצלחנו לפענח" in text and "שמכם" in text:
        return "006"
    if "כבר רשום" in text:
        return "008"
    if "לא הצלחנו לפענח" in text and "כתובת" in text:
        return "011"
    if "הרשמתכם הושלמה" in text:
        return "013"
    if "קוד הקהילה עודכן" in text:
        return "016"
    if "אין כרגע מוצרים בקטלוג" in text:
        return "018f"
    if "סל הקניות שלך ריק" in text:
        return "019"
    if "כמות חייבת להיות גדולה מאפס" in text:
        return "020b"
    if "מספרים בלבד" in text:
        return "021"
    if "ההזמנה בוטלה" in text:
        return "024"
    if "סך הכל לתשלום" in text and "מועברים" in text:
        return "025b"
    if "יש לך הזמנה פתוחה" in text:
        return "026"
    return PROMPT_FILE_MAP.get(var_name, "001")

# -------------------------------------------------------------------
# פונקציות מענה לימות המשיח
# -------------------------------------------------------------------
def get_audio_file_extension(file_num: str) -> str:
    """בודק פעם אחת לכל קובץ אם קיימת הקלטת WAV או OGG בשלוחה המוגדרת."""
    key = str(file_num or "").strip()
    if not USE_AUDIO_FILES or not key or not YEMOT_TOKEN:
        return ""
    if key in AUDIO_FILE_EXISTS_CACHE:
        return AUDIO_FILE_EXISTS_CACHE[key]

    api_url = "https://www.call2all.co.il/ym/api/CheckIfFileExists"
    for extension in ("wav", "ogg"):
        path = f"ivr2:/{AUDIO_FOLDER}/{key}.{extension}"
        try:
            response = requests.get(
                api_url,
                params={"token": YEMOT_TOKEN, "path": path},
                timeout=3
            )
            response.raise_for_status()
            data = response.json()
            if data.get("fileExists") is True:
                AUDIO_FILE_EXISTS_CACHE[key] = extension
                return extension
        except Exception as error:
            print(f"LOG: בדיקת קובץ שמע {key}.{extension} נכשלה: {error}", flush=True)

    AUDIO_FILE_EXISTS_CACHE[key] = ""
    return ""

def audio_prompt(file_num: str, fallback_text: str) -> str:
    """אם יש הקלטה משמיע אותה בלבד; אחרת משתמש ב-TTS כגיבוי."""
    extension = get_audio_file_extension(file_num)
    if extension:
        return f"f-/{AUDIO_FOLDER}/{file_num}.{extension}"
    return f"t-{clean_tts(fallback_text)}"

def yemot_read(text: str, var_name: str, options: str = "no,1,1,7,Digits,no,no,*/") -> Response:
    clean_text = clean_tts(text)
    file_num = get_prompt_file_num(clean_text, var_name)
    sound_str = audio_prompt(file_num, clean_text)
    content = f"read={sound_str}={var_name},{options}"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def yemot_read_record(text: str, var_name: str, options: str = "no,record,,,no", record_folder: str = "") -> Response:
    clean_text = clean_tts(text)
    file_num = get_prompt_file_num(clean_text, var_name)
    sound_str = audio_prompt(file_num, clean_text)
    if record_folder and record_folder != "/":
        content = f"read={sound_str}={var_name},{options},{record_folder}"
    else:
        content = f"read={sound_str}={var_name},{options}"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def yemot_msg(text: str) -> Response:
    clean_text = clean_tts(text)
    file_num = get_prompt_file_num(clean_text, "")
    sound_str = audio_prompt(file_num, clean_text)
    content = f"id_list_message={sound_str}"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def yemot_read_digit_confirmation(
    field_title: str, digits: str, confirm_text: str, var_name: str,
    intro_file: str, confirm_file: str, options: str
) -> Response:
    """משמיע ספרות אחת-אחת בין שני קובצי הנחיה מוקלטים."""
    sound_chain = (
        f"{audio_prompt(intro_file, field_title)}."
        f"d-{digits}."
        f"{audio_prompt(confirm_file, confirm_text)}"
    )
    return Response(
        content=f"read={sound_chain}={var_name},{options}",
        media_type="text/plain; charset=utf-8"
    )

def yemot_read_transcript_confirmation(
    label: str, transcript: str, var_name: str, intro_file: str, confirm_file: str,
    retry_text: str
) -> Response:
    clean_transcript = clean_tts(transcript)
    sound_chain = (
        f"{audio_prompt(intro_file, label)}."
        f"t-{clean_transcript}."
        f"{audio_prompt(confirm_file, retry_text)}"
    )
    return Response(
        content=f"read={sound_chain}={var_name},no,1,1,7,Digits,no,no,*/",
        media_type="text/plain; charset=utf-8"
    )

async def check_abandoned_cart_or_proceed(session: dict, background_tasks: BackgroundTasks) -> Response:
    user = session.get("user", {})
    user_id = get_field(user, "תעודת זהות", "id_number") or get_field(user, "מספר טלפון", "phone") or session.get("phone")
    
    if user_id and SAVED_CARTS.get(user_id):
        session["step"] = "RESTORE_CART_CHOICE"
        msg = "המערכת מזהה כי יש לך הזמנה פתוחה במערכת, להמשך קנייה זו הקישו 1, להתחלת קנייה חדשה הקישו 2"
        return yemot_read(msg, "restore_cart_choice", "no,1,1,7,Digits,no,no,*/")
    else:
        session["step"] = "MAIN_MENU"
        return await show_categories(session)

# -------------------------------------------------------------------
# 4. Webhook ראשי
# -------------------------------------------------------------------
@app.api_route("/", methods=["GET", "POST", "HEAD"])
async def ivr_handler(request: Request, background_tasks: BackgroundTasks):
    if request.method == "HEAD":
        return Response(content="OK", media_type="text/plain")

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
                "cart": [],
                "selected_cat": None,
                "selected_kashrut": None,
                "filtered_products": [],
                "product_index": 0,
                "pending_qty": 0,
                "call_id": call_id,
                "phone": phone,
                "reg_data": {},
                "auth_target": "MAIN_MENU"
            }
            background_tasks.add_task(log_general_event, call_id, phone, "כניסה לשיחה", "התחלת שיחה חדשה")
            
        session = SESSIONS[call_id]
        step = session["step"]
        
        raw_user_input = ""
        expected_keys = STEP_PARAM_MAP.get(step, [])
        for key in expected_keys:
            if params.get(key):
                raw_user_input = str(params.get(key)).strip()
                break
                
        if not raw_user_input:
            for k, v in params.items():
                if not k.startswith("Api") and v:
                    raw_user_input = str(v).strip()
                    break
                    
        user_input = clean_input(raw_user_input)
        welcome_text = "שלום וברוכים הבאים, להודעות ועידכונים הקישו 1, לכניסה למערכת ההזמנות הקישו 2, לרישום למערכת ההזמנות הקישו 3, לאיזור האישי הקישו 4, לשמיעת הקטלוג המלא הקישו 5, לרישום לקבלת צינתוק כשעולה הודעה חדשה הקישו 6"
        
        # ---------------------------------------------------------
        # שלב פתיחה (תפריט ראשי)
        # ---------------------------------------------------------
        if step == "WELCOME":
            if not user_input:
                return yemot_read(welcome_text, "welcome_choice", "no,1,1,7,no,no,no,*/,,,,,,no")
            
            if user_input == "1":
                return Response(content="go_to_folder=/1", media_type="text/plain; charset=utf-8")
                
            elif user_input == "2":
                # קודם מזהים לפי תעודת זהות; רק לאחר מכן תתבקש סיסמה.
                session["auth_target"] = "MAIN_MENU"
                session["step"] = "AUTH"
                session["password_attempts"] = 0
                return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם ולאחר מכן הקישו סולמית", "auth_id", "no,9,8,7,Digits,no,no,*/")
                    
            elif user_input == "3":
                session["reg_data"] = {}
                session.pop("password_setup_target", None)
                session.pop("pending_password", None)
                session["registration_saved"] = False
                session["step"] = "REG_ID"
                return yemot_read("להתחלת רישום, אנא הקישו את מספר תעודת הזהות שלכם ולאחר מכן הקישו סולמית", "reg_id", "no,9,8,7,Digits,no,no,*/")
                
            elif user_input == "4":
                user = session.get("user") or CACHE["users"].get(phone)
                if user:
                    session["user"] = user
                    return show_personal_area(session)
                else:
                    session["auth_target"] = "PERSONAL_AREA"
                    session["step"] = "AUTH"
                    return yemot_read("לאזור האישי אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", "no,10,9,7,Digits,no,no,*/")
                    
            elif user_input == "5":
                session["filtered_products"] = CACHE["products"]
                session["product_index"] = 0
                session["step"] = "CATALOG_LOOP"
                return play_catalog_product(session)
                
            elif user_input == "6":
                return Response(content="go_to_folder=/6", media_type="text/plain; charset=utf-8")

            elif user_input == "7":
                return Response(content="go_to_folder=/7", media_type="text/plain; charset=utf-8")
                
            else:
                return yemot_read(f"הקשה שגויה, {welcome_text}", "welcome_choice", "no,1,1,7,Digits,no,no,*/")

        # ---------------------------------------------------------
        # שלב אזור אישי
        # ---------------------------------------------------------
        elif step == "PERSONAL_AREA":
            if user_input == "1":
                session["step"] = "WELCOME"
                return yemot_read(welcome_text, "welcome_choice", "no,1,1,7,no,no,no,*/,,,,,,no")
            elif user_input == "2":
                session["step"] = "UPDATE_COMMUNITY_CODE"
                return yemot_read("אנא הקישו את קוד הקהילה החדש שלכם ולאחר מכן הקישו סולמית", "new_community_code", "no,6,1,7,Digits,no,no,*/")
            else:
                return show_personal_area(session)

        elif step == "UPDATE_COMMUNITY_CODE":
            if not user_input:
                return yemot_read("אנא הקישו את קוד הקהילה החדש שלכם ולאחר מכן הקישו סולמית", "new_community_code", "no,6,1,7,Digits,no,no,*/")
                
            new_code = user_input
            user = session.get("user") or {}
            user_id = get_field(user, "תעודת זהות", "id_number") or get_field(user, "מספר טלפון", "phone") or session.get("phone")
            
            if APPS_SCRIPT_URL:
                try:
                    payload = {
                        "type": "update_community_code",
                        "id_number": str(user_id),
                        "phone": str(session.get("phone", "")),
                        "community_code": str(new_code)
                    }
                    background_tasks.add_task(requests.post, APPS_SCRIPT_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=10)
                except Exception:
                    pass

            user["community_code"] = new_code
            if user_id in CACHE["users"]:
                CACHE["users"][user_id]["community_code"] = new_code
            if session.get("phone") in CACHE["users"]:
                CACHE["users"][session["phone"]]["community_code"] = new_code
                
            return show_personal_area(session, prefix="קוד הקהילה עודכן בהצלחה, ")

        # ---------------------------------------------------------
        # שלב בחירה: שחזור הזמנה קודמת שלא שולמה
        # ---------------------------------------------------------
        elif step == "RESTORE_CART_CHOICE":
            user = session.get("user") or {}
            user_id = get_field(user, "תעודת זהות", "id_number") or get_field(user, "מספר טלפון", "phone") or phone
            
            if user_input == "1":
                session["cart"] = SAVED_CARTS.get(user_id, [])
                session["step"] = "MAIN_MENU"
                return await show_categories(session, prefix="ממשיכים את ההזמנה הקודמת, ")
            elif user_input == "2":
                session["cart"] = []
                if user_id in SAVED_CARTS:
                    del SAVED_CARTS[user_id]
                session["step"] = "MAIN_MENU"
                return await show_categories(session, prefix="מתחילים הזמנה חדשה, ")
            else:
                msg = "הקשה שגויה, המערכת מזהה כי יש לך הזמנה פתוחה במערכת, להמשך קנייה זו הקישו 1, להתחלת קנייה חדשה הקישו 2"
                return yemot_read(msg, "restore_cart_choice", "no,1,1,7,Digits,no,no,*/")

        # ---------------------------------------------------------
        # שלב 1: זיהוי מורשים
        # ---------------------------------------------------------
        elif step == "AUTH":
            target = session.get("auth_target", "MAIN_MENU")
            if not user_input:
                return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם ולאחר מכן הקישו סולמית", "auth_id", "no,9,8,7,Digits,no,no,*/")

            if target == "MAIN_MENU" and (not user_input.isdigit() or not 8 <= len(user_input) <= 9):
                return yemot_read("מספר תעודת הזהות חייב להכיל שמונה או תשע ספרות. אנא הקישו שוב", "auth_id", "no,9,8,7,Digits,no,no,*/")

            if user_input in CACHE["users"]:
                session["user"] = CACHE["users"][user_input]
                session["authenticated_id"] = str(get_field(session["user"], "תעודת זהות", "id_number") or user_input)
                background_tasks.add_task(log_general_event, call_id, phone, "זיהוי מוצלח", "נמצא משתמש רשום")

                if target == "PERSONAL_AREA":
                    return show_personal_area(session)

                stored_hash = SALES_CONTROL_CACHE["password_hashes"].get(session["authenticated_id"])
                if not stored_hash:
                    registered_phone = normalize_phone(get_field(session["user"], "מספר טלפון", "phone"))
                    caller_phone = normalize_phone(phone)
                    if registered_phone and caller_phone and registered_phone == caller_phone:
                        session["password_setup_target"] = "legacy_user"
                        session["step"] = "SET_PASSWORD"
                        return yemot_read("החשבון נמצא. להגדרת סיסמה ראשונה הקישו סיסמה חדשה בת שש עד עשר ספרות", "set_password", "no,10,6,7,Digits,no,no,*/")
                    return yemot_msg("החשבון נמצא אך טרם הוגדרה לו סיסמה. נא לפנות למנהל המערכת")

                session["step"] = "AUTH_PASSWORD"
                session["password_attempts"] = 0
                return yemot_read("אנא הקישו את הסיסמה שלכם בת שש עד עשר ספרות", "auth_password", "no,10,6,7,Digits,no,no,*/")

            session["step"] = "NOT_AUTHORIZED_CHOICE"
            background_tasks.add_task(log_general_event, call_id, phone, "זיהוי נכשל", "תעודת הזהות אינה רשומה")
            return yemot_read("המערכת מזהה כי אינך רשום למערכת, להקשת מספר אחר הקישו 1, למעבר לרישום למערכת הקישו 2", "unauth_choice", "no,1,1,7,no,no,no,*/,,,,,,no")

        elif step == "AUTH_PASSWORD":
            if not user_input:
                return yemot_read("אנא הקישו את הסיסמה שלכם בת שש עד עשר ספרות", "auth_password", "no,10,6,7,Digits,no,no,*/")
            if not password_is_valid(user_input):
                return yemot_read("הסיסמה חייבת להכיל שש עד עשר ספרות. אנא הקישו שוב", "auth_password", "no,10,6,7,Digits,no,no,*/")

            id_number = session.get("authenticated_id", "")
            stored_hash = SALES_CONTROL_CACHE["password_hashes"].get(id_number, "")
            if not verify_user_password(user_input, stored_hash):
                session["password_attempts"] = session.get("password_attempts", 0) + 1
                if session["password_attempts"] >= 3:
                    session["step"] = "WELCOME"
                    session["user"] = None
                    return yemot_msg("הסיסמה שגויה שלוש פעמים. נא להתקשר מחדש")
                return yemot_read("הסיסמה שגויה. אנא נסו שוב", "auth_password", "no,10,6,7,Digits,no,no,*/")

            background_tasks.add_task(log_general_event, call_id, phone, "התחברות מוצלחת", "אימות סיסמה הצליח")
            if not is_sales_entry_allowed(session):
                session["step"] = "WELCOME"
                return sales_closed_response()
            return await check_abandoned_cart_or_proceed(session, background_tasks)

        elif step == "SET_PASSWORD":
            if not password_is_valid(user_input):
                return yemot_read("יש להקיש סיסמה בת שש עד עשר ספרות", "set_password", "no,10,6,7,Digits,no,no,*/")
            session["pending_password"] = user_input
            session["step"] = "SET_PASSWORD_CONFIRM"
            return yemot_read("להקשה חוזרת של הסיסמה לאישור, הקישו שוב את אותן שש עד עשר ספרות", "set_password_confirm", "no,10,6,7,Digits,no,no,*/")

        elif step == "SET_PASSWORD_CONFIRM":
            if not password_is_valid(user_input):
                return yemot_read("יש להקיש סיסמה בת שש עד עשר ספרות", "set_password_confirm", "no,10,6,7,Digits,no,no,*/")
            if user_input != session.get("pending_password"):
                session.pop("pending_password", None)
                session["step"] = "SET_PASSWORD"
                return yemot_read("הסיסמאות אינן זהות. אנא הקישו סיסמה חדשה", "set_password", "no,10,6,7,Digits,no,no,*/")

            password_hash = hash_user_password(user_input)
            target = session.get("password_setup_target", "new_user")
            id_number = str(
                session.get("reg_data", {}).get("id_number")
                if target == "new_user"
                else session.get("authenticated_id", "")
            ).strip()

            if target == "new_user":
                user_info = session["reg_data"]
                new_user = {
                    "id_number": user_info.get("id_number"),
                    "phone": user_info.get("phone"),
                    "first_name": user_info.get("first_name"),
                    "last_name": "",
                    "address": user_info.get("address"),
                    "community_code": user_info.get("community_code"),
                    "is_active": "TRUE"
                }
                CACHE["users"][id_number] = new_user
                CACHE["users"][str(user_info.get("phone", ""))] = new_user
                session["user"] = new_user
                background_tasks.add_task(save_new_user_to_sheet, user_info, password_hash)
                background_tasks.add_task(log_general_event, call_id, phone, "הרשמה הושלמה", "משתמש חדש נרשם ונקבעה סיסמה")
            else:
                background_tasks.add_task(save_password_hash_to_sales_control, id_number, password_hash)
                background_tasks.add_task(log_general_event, call_id, phone, "הוגדרה סיסמה", "סיסמה ראשונה הוגדרה לחשבון קיים")

            SALES_CONTROL_CACHE["password_hashes"][id_number] = password_hash
            session.pop("pending_password", None)
            session.pop("password_setup_target", None)

            if not is_sales_entry_allowed(session):
                session["step"] = "WELCOME"
                return yemot_msg("הרשמתכם הושלמה בהצלחה. מערכת ההזמנות סגורה כעת. נא לנסות מאוחר יותר.")
            if target == "new_user":
                return await show_categories(session, prefix="הרשמתכם הושלמה בהצלחה, ")
            return await check_abandoned_cart_or_proceed(session, background_tasks)

        elif step == "NOT_AUTHORIZED_CHOICE":
            if user_input == "1":
                session["step"] = "AUTH"
                session["auth_target"] = "MAIN_MENU"
                return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם ולאחר מכן הקישו סולמית", "auth_id", "no,9,8,7,Digits,no,no,*/")
            elif user_input == "2":
                session["reg_data"] = {}
                session.pop("password_setup_target", None)
                session.pop("pending_password", None)
                session["registration_saved"] = False
                session["step"] = "REG_ID"
                return yemot_read("להתחלת רישום, אנא הקישו את מספר תעודת הזהות שלכם ולאחר מכן הקישו סולמית", "reg_id", "no,9,8,7,Digits,no,no,*/")
            else:
                return yemot_read("הקשה שגויה. להקשת מספר אחר הקישו 1, למעבר לרישום הקישו 2", "unauth_choice", "no,1,1,7,Digits,no,no,*/")

        # ---------------------------------------------------------
        # הרשמה חדשה - לפי סדר שבעת השלבים שהוגדר
        # ---------------------------------------------------------
        elif step == "REG_ID":
            if not user_input or not user_input.isdigit() or not 8 <= len(user_input) <= 9:
                return yemot_read("מספר תעודת הזהות חייב להכיל שמונה או תשע ספרות. אנא הקישו שוב", "reg_id", "no,9,8,7,Digits,no,no,*/")
            if user_input in CACHE["users"]:
                session["step"] = "AUTH"
                session["auth_target"] = "MAIN_MENU"
                return yemot_read("מספר תעודת הזהות כבר רשום במערכת. לכניסה לחשבון הקישו שוב את מספר תעודת הזהות ולאחר מכן סולמית", "auth_id", "no,9,8,7,Digits,no,no,*/")
            session["reg_data"]["id_number_temp"] = user_input
            session["reg_data"]["temp_id_number"] = user_input
            session["step"] = "REG_ID_CONFIRM"
            return yemot_read_digit_confirmation(
                "מספר תעודת הזהות שנקלט הוא", user_input,
                "לאישור הקישו 1, להקשה מחדש הקישו 2",
                "reg_id_confirm_choice", "032", "027b",
                "no,1,1,7,Digits,no,no,*/"
            )

        elif step == "REG_ID_CONFIRM":
            if user_input == "1":
                session["reg_data"]["id_number"] = session["reg_data"].get("temp_id_number", "")
                session["step"] = "REG_PHONE"
                return yemot_read("אנא הקישו את מספר הטלפון שלכם, בן תשע או עשר ספרות, ולאחר מכן הקישו סולמית", "reg_phone", "no,10,9,7,Digits,no,no,*/")
            if user_input == "2":
                session["step"] = "REG_ID"
                return yemot_read("אנא הקישו מחדש את מספר תעודת הזהות שלכם ולאחר מכן הקישו סולמית", "reg_id", "no,9,8,7,Digits,no,no,*/")
            return yemot_read_digit_confirmation(
                "מספר תעודת הזהות שנקלט הוא",
                session["reg_data"].get("temp_id_number", ""),
                "לאישור הקישו 1, להקשה מחדש הקישו 2",
                "reg_id_confirm_choice", "032", "027b",
                "no,1,1,7,Digits,no,no,*/"
            )

        elif step == "REG_PHONE":
            if not user_input or not user_input.isdigit() or not 9 <= len(user_input) <= 10:
                return yemot_read("מספר הטלפון חייב להכיל תשע או עשר ספרות. אנא הקישו שוב", "reg_phone", "no,10,9,7,Digits,no,no,*/")
            session["reg_data"]["temp_phone"] = user_input
            session["step"] = "REG_PHONE_CONFIRM"
            return yemot_read_digit_confirmation(
                "מספר הטלפון שנקלט הוא", user_input,
                "לאישור הקישו 1, להקשה מחדש הקישו 2",
                "reg_phone_confirm_choice", "033", "027b",
                "no,1,1,7,Digits,no,no,*/"
            )

        elif step == "REG_PHONE_CONFIRM":
            if user_input == "1":
                session["reg_data"]["phone"] = session["reg_data"].get("temp_phone", "")
                session["step"] = "REG_NAME"
                return yemot_read_record(
                    "כעת הקליטו את שמכם המלא לאחר הצליל. לסיום ההקלטה הקישו סולמית",
                    "reg_name", "no,record,,,no"
                )
            if user_input == "2":
                session["step"] = "REG_PHONE"
                return yemot_read("אנא הקישו מחדש את מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "reg_phone", "no,10,9,7,Digits,no,no,*/")
            return yemot_read_digit_confirmation(
                "מספר הטלפון שנקלט הוא", session["reg_data"].get("temp_phone", ""),
                "לאישור הקישו 1, להקשה מחדש הקישו 2",
                "reg_phone_confirm_choice", "033", "027b",
                "no,1,1,7,Digits,no,no,*/"
            )

        elif step == "REG_NAME":
            print(f"LOG [REG_NAME]: התקבל נתיב הקלטת שם: '{raw_user_input}'", flush=True)
            if not raw_user_input:
                return yemot_read_record(
                    "כעת הקליטו את שמכם המלא לאחר הצליל. לסיום ההקלטה הקישו סולמית",
                    "reg_name", "no,record,,,no"
                )
            transcribed_text = transcribe_audio_file_from_yemot(raw_user_input, token)
            print(f"LOG [REG_NAME]: תמלול השם: '{transcribed_text}'", flush=True)
            if not transcribed_text:
                return yemot_read_record(
                    "לא הצלחנו לתמלל את השם. אנא הקליטו שוב את שמכם המלא לאחר הצליל ולסיום הקישו סולמית",
                    "reg_name", "no,record,,,no"
                )
            session["reg_data"]["temp_name"] = transcribed_text.strip()
            session["step"] = "REG_NAME_CONFIRM"
            return yemot_read_transcript_confirmation(
                "השם שנקלט הוא", session["reg_data"]["temp_name"],
                "reg_name_confirm_choice", "027a", "027b",
                "לאישור הקישו 1, להקלטה מחדש הקישו 2"
            )

        elif step == "REG_NAME_CONFIRM":
            if user_input == "1":
                session["reg_data"]["first_name"] = session["reg_data"].get("temp_name", "")
                session["step"] = "REG_ADDRESS"
                return yemot_read_record(
                    "כעת הקליטו את הכתובת המלאה, כולל עיר, רחוב ומספר בית, לאחר הצליל. לסיום הקישו סולמית",
                    "reg_address", "no,record,,,no"
                )
            if user_input == "2":
                session["step"] = "REG_NAME"
                return yemot_read_record(
                    "אנא הקליטו שוב את שמכם המלא לאחר הצליל. לסיום הקישו סולמית",
                    "reg_name", "no,record,,,no"
                )
            return yemot_read_transcript_confirmation(
                "השם שנקלט הוא", session["reg_data"].get("temp_name", ""),
                "reg_name_confirm_choice", "027a", "027b",
                "לאישור הקישו 1, להקלטה מחדש הקישו 2"
            )

        elif step == "REG_ADDRESS":
            print(f"LOG [REG_ADDRESS]: התקבל נתיב הקלטת כתובת: '{raw_user_input}'", flush=True)
            if not raw_user_input:
                return yemot_read_record(
                    "כעת הקליטו את הכתובת המלאה, כולל עיר, רחוב ומספר בית, לאחר הצליל. לסיום הקישו סולמית",
                    "reg_address", "no,record,,,no"
                )
            transcribed_text = transcribe_audio_file_from_yemot(raw_user_input, token)
            print(f"LOG [REG_ADDRESS]: תמלול הכתובת: '{transcribed_text}'", flush=True)
            if not transcribed_text:
                return yemot_read_record(
                    "לא הצלחנו לתמלל את הכתובת. אנא הקליטו שוב את הכתובת המלאה לאחר הצליל ולסיום הקישו סולמית",
                    "reg_address", "no,record,,,no"
                )
            session["reg_data"]["temp_address"] = transcribed_text.strip()
            session["step"] = "REG_ADDRESS_CONFIRM"
            return yemot_read_transcript_confirmation(
                "הכתובת שנקלטה היא", session["reg_data"]["temp_address"],
                "reg_address_confirm_choice", "028a", "028b",
                "לאישור הקישו 1, להקלטה מחדש הקישו 2"
            )

        elif step == "REG_ADDRESS_CONFIRM":
            if user_input == "1":
                session["reg_data"]["address"] = session["reg_data"].get("temp_address", "")
                session["step"] = "REG_COMMUNITY_CODE"
                return yemot_read(
                    "אנא הקישו את קוד הקהילה בן שש הספרות שלכם. לדילוג על שלב זה הקישו סולמית",
                    "reg_community_code", "no,6,0,7,Digits,no,no,*/"
                )
            if user_input == "2":
                session["step"] = "REG_ADDRESS"
                return yemot_read_record(
                    "אנא הקליטו שוב את הכתובת המלאה, כולל עיר, רחוב ומספר בית, לאחר הצליל. לסיום הקישו סולמית",
                    "reg_address", "no,record,,,no"
                )
            return yemot_read_transcript_confirmation(
                "הכתובת שנקלטה היא", session["reg_data"].get("temp_address", ""),
                "reg_address_confirm_choice", "028a", "028b",
                "לאישור הקישו 1, להקלטה מחדש הקישו 2"
            )

        elif step == "REG_COMMUNITY_CODE":
            code = user_input.strip() if user_input and user_input not in ["0", "*", "#"] else ""
            if not code:
                session["reg_data"]["community_code"] = ""
                session["step"] = "REG_ALERTS_CHOICE"
                return yemot_read(
                    "לרישום לקבלת צינתוקים אישיים הקישו 1. לדילוג על שלב זה הקישו 2",
                    "reg_alerts_choice", "no,1,1,7,Digits,no,no,*/"
                )
            if not code.isdigit() or len(code) != 6:
                return yemot_read(
                    "קוד הקהילה חייב להכיל שש ספרות. אנא הקישו שוב, או הקישו סולמית לדילוג",
                    "reg_community_code", "no,6,0,7,Digits,no,no,*/"
                )
            session["reg_data"]["temp_community_code"] = code
            session["step"] = "REG_COMMUNITY_CODE_CONFIRM"
            return yemot_read_digit_confirmation(
                "קוד הקהילה שנקלט הוא", code,
                "לאישור הקישו 1, להקשה מחדש הקישו 2",
                "reg_community_code_confirm_choice", "034", "027b",
                "no,1,1,7,Digits,no,no,*/"
            )

        elif step == "REG_COMMUNITY_CODE_CONFIRM":
            if user_input == "1":
                session["reg_data"]["community_code"] = session["reg_data"].get("temp_community_code", "")
                session["step"] = "REG_ALERTS_CHOICE"
                return yemot_read(
                    "לרישום לקבלת צינתוקים אישיים הקישו 1. לדילוג על שלב זה הקישו 2",
                    "reg_alerts_choice", "no,1,1,7,Digits,no,no,*/"
                )
            if user_input == "2":
                session["step"] = "REG_COMMUNITY_CODE"
                return yemot_read(
                    "אנא הקישו מחדש את קוד הקהילה בן שש הספרות, או הקישו סולמית לדילוג",
                    "reg_community_code", "no,6,0,7,Digits,no,no,*/"
                )
            return yemot_read_digit_confirmation(
                "קוד הקהילה שנקלט הוא", session["reg_data"].get("temp_community_code", ""),
                "לאישור הקישו 1, להקשה מחדש הקישו 2",
                "reg_community_code_confirm_choice", "034", "027b",
                "no,1,1,7,Digits,no,no,*/"
            )

        elif step == "REG_ALERTS_CHOICE":
            persist_registration(session, background_tasks)
            session["step"] = "REG_FINISH"
            if user_input == "1":
                # שלוחה C במערכת הראשית מטפלת בצירוף לרשימת הצינתוקים האישיים.
                # שלוחת C מוגדרת להשתמש במספר המתקשר כמספר הרשימה.
                session["registration_alerts_requested"] = True
                return Response(content="go_to_folder=/C", media_type="text/plain; charset=utf-8")
            if user_input == "2":
                session["registration_alerts_requested"] = False
                return yemot_read(
                    "הרישום נשמר. לסיום ומעבר לתפריט ההזמנות הקישו 1, למעבר לתפריט הראשי הקישו 2",
                    "reg_finish_choice", "no,1,1,7,Digits,no,no,*/"
                )
            return yemot_read(
                "הקשה שגויה. לרישום לקבלת צינתוקים אישיים הקישו 1, לדילוג הקישו 2",
                "reg_alerts_choice", "no,1,1,7,Digits,no,no,*/"
            )

        elif step == "REG_FINISH":
            if user_input == "2":
                session["step"] = "WELCOME"
                session["auth_target"] = "MAIN_MENU"
                session["registration_alerts_requested"] = False
                return yemot_read(welcome_text, "welcome_choice", "no,1,1,7,Digits,no,no,*/")
            if user_input == "1":
                if not is_sales_entry_allowed(session):
                    return yemot_read(
                        "הרישום הושלם, אך המכירות סגורות כעת. למעבר לתפריט הראשי הקישו 2",
                        "reg_finish_choice", "no,1,1,7,Digits,no,no,*/"
                    )
                session["step"] = "MAIN_MENU"
                session["user"] = session.get("user") or CACHE["users"].get(session["reg_data"].get("id_number", ""))
                return await show_categories(session, prefix="הרישום הושלם בהצלחה, ")
            if not is_sales_entry_allowed(session):
                return yemot_read(
                    "הרישום הושלם, אך המכירות סגורות כעת. למעבר לתפריט הראשי הקישו 2",
                    "reg_finish_choice", "no,1,1,7,Digits,no,no,*/"
                )
            return yemot_read(
                "הרישום נשמר. לסיום ומעבר לתפריט ההזמנות הקישו 1, למעבר לתפריט הראשי הקישו 2",
                "reg_finish_choice", "no,1,1,7,Digits,no,no,*/"
            )

        # ---------------------------------------------------------
        # שלב 2: תפריט קטגוריות
        # ---------------------------------------------------------
        elif step == "MAIN_MENU":
            cats = CACHE["categories"]
            if user_input == "9":
                return initiate_checkout(session)
                
            try:
                choice_idx = int(user_input) - 1
                if 0 <= choice_idx < len(cats):
                    selected_cat = cats[choice_idx]
                    session["selected_cat"] = selected_cat["category_name"]
                    session["step"] = "KASHRUT_MENU"
                    kashruts = [k.strip() for k in str(selected_cat.get("kashruts", "")).split(",") if k.strip()]
                    session["available_kashruts"] = kashruts
                    
                    if not kashruts:
                        session["selected_kashrut"] = None
                        return start_product_loop(session)
                    
                    k_text = ""
                    for i, k in enumerate(kashruts, 1):
                        k_text += f"לכשרות {k} הקישו {i}, "
                    return yemot_read(k_text, "kashrut_choice", "no,1,1,7,no,no,no,*/,,,,,,no")
                else:
                    return await show_categories(session, prefix="הקשה שגויה, ")
            except ValueError:
                return await show_categories(session, prefix="הקשה שגויה, ")

        # ---------------------------------------------------------
        # שלב 3: תפריט כשרויות
        # ---------------------------------------------------------
        elif step == "KASHRUT_MENU":
            kashruts = session.get("available_kashruts", [])
            if user_input == "9":
                return initiate_checkout(session)
                
            try:
                choice_idx = int(user_input) - 1
                if 0 <= choice_idx < len(kashruts):
                    session["selected_kashrut"] = kashruts[choice_idx]
                    return start_product_loop(session)
                else:
                    return yemot_read("הקשה שגויה, אנא בחר כשרות מתוך הרשימה", "kashrut_choice", "no,1,1,7,no,no,no,*/,,,,,,no")
            except ValueError:
                return yemot_read("הקשה שגויה, אנא בחר כשרות מתוך הרשימה", "kashrut_choice", "no,1,1,7,no,no,no,*/,,,,,,no")

        # ---------------------------------------------------------
        # שלב 4: דפדוף במוצרים במכירות
        # ---------------------------------------------------------
        elif step == "PRODUCT_LOOP":
            products = session["filtered_products"]
            idx = session["product_index"]
            
            if user_input == "1":
                session["step"] = "QTY_INPUT"
                p = products[idx]
                return yemot_read_qty(p['name'])
            elif user_input == "2":
                next_idx = (idx + 1) % len(products)
                session["product_index"] = next_idx
                return play_current_product(session)
            elif user_input == "3":
                session["step"] = "MAIN_MENU"
                return await show_categories(session)
            elif user_input == "9":
                return initiate_checkout(session)
            else:
                return play_current_product(session, prefix="הקשה שגויה, ")

        # ---------------------------------------------------------
        # שלב 4ב: דפדוף בקטלוג (שמיעה בלבד)
        # ---------------------------------------------------------
        elif step == "CATALOG_LOOP":
            products = session.get("filtered_products", [])
            idx = session.get("product_index", 0)
            
            if user_input == "1":
                next_idx = (idx + 1) % len(products)
                session["product_index"] = next_idx
                return play_catalog_product(session)
            elif user_input == "2":
                session["step"] = "WELCOME"
                return yemot_read(welcome_text, "welcome_choice", "no,1,1,7,no,no,no,*/,,,,,,no")
            else:
                return play_catalog_product(session, prefix="הקשה שגויה, ")

        # ---------------------------------------------------------
        # שלב 5: הזנת כמות
        # ---------------------------------------------------------
        elif step == "QTY_INPUT":
            try:
                qty = int(user_input)
                if qty <= 0:
                    return yemot_read("כמות חייבת להיות גדולה מאפס, אנא הקש כמות תקינה", "qty_input", "no,3,1,7,Digits,no,no,*/")
                
                p = session["filtered_products"][session["product_index"]]
                total_price = qty * float(p["price"])
                
                session["cart"].append({
                    "sku": p["sku"],
                    "name": p["name"],
                    "qty": qty,
                    "total": total_price
                })
                
                user = session.get("user") or {}
                user_id = get_field(user, "תעודת זהות", "id_number") or get_field(user, "מספר טלפון", "phone") or phone
                if user_id:
                    SAVED_CARTS[user_id] = session["cart"]

                background_tasks.add_task(log_general_event, call_id, phone, "הוספה לסל", f"נוסף {p['name']} כמות {qty}")
                
                session["step"] = "AFTER_ADD_MENU"
                msg = "המוצר נוסף בהצלחה לסל הקניות שלך, למוצר הבא הקישו 1, למעבר לקטגוריה אחרת הקישו 2, לסיום הקנייה ומעבר לתשלום הקישו 9"
                return yemot_read(msg, "after_add_choice", "no,1,1,7,no,no,no,*/,,,,,,no")
            except ValueError:
                return yemot_read("הקשה שגויה, אנא הקש כמות במספרים בלבד", "qty_input", "no,3,1,7,Digits,no,no,*/")

        elif step == "AFTER_ADD_MENU":
            if user_input == "1":
                session["product_index"] = (session["product_index"] + 1) % len(session["filtered_products"])
                session["step"] = "PRODUCT_LOOP"
                return play_current_product(session)
            elif user_input == "2":
                session["step"] = "MAIN_MENU"
                return await show_categories(session)
            elif user_input == "9":
                return initiate_checkout(session)
            else:
                return yemot_read("הקשה שגויה, למוצר הבא הקישו 1, לקטגוריה אחרת הקישו 2, לסיום הקנייה ומעבר לתשלום הקישו 9", "after_add_choice", "no,1,1,7,no,no,no,*/,,,,,,no")

        # ---------------------------------------------------------
        # שלב 6: אישור דמי החזקת תחנת חלוקה (10 ש"ח)
        # ---------------------------------------------------------
        elif step == "CONFIRM_CHECKOUT_FEE":
            if user_input == "1":
                return finish_checkout(session, background_tasks)
            elif user_input == "2":
                session["cart"] = []
                user = session.get("user") or {}
                user_id = get_field(user, "תעודת זהות", "id_number") or get_field(user, "מספר טלפון", "phone") or phone
                if user_id and user_id in SAVED_CARTS:
                    del SAVED_CARTS[user_id]
                    
                session["step"] = "MAIN_MENU"
                return await show_categories(session, prefix="ההזמנה בוטלה, מעביר אותך חזרה לתפריט, ")
            else:
                total_with_fee = session.get("total_sum_with_fee", 10)
                part1_text = "שימו לב בכל הזמנה יתווספו לתשלום דמי החזקת תחנת החלוקה בסך של 10 שקלים סך הכל לתשלום כולל דמי החזקה הוא"
                part2_text = "שקלים לאישור ומעבר לתשלום הקישו 1 לביטול ההזמנה הקישו 2"
                
                if USE_AUDIO_FILES:
                    sound_chain = f"f-/{AUDIO_FOLDER}/023a.t-{clean_tts(part1_text)}.n-{total_with_fee}.f-/{AUDIO_FOLDER}/023b.t-{clean_tts(part2_text)}"
                else:
                    sound_chain = f"t-{clean_tts(part1_text)}.n-{total_with_fee}.t-{clean_tts(part2_text)}"

                content = f"read={sound_chain}=checkout_confirm_choice,no,1,1,7,no,no,no,*/,,,,,,no"
                return Response(content=content, media_type="text/plain; charset=utf-8")

        return yemot_msg("אירעה שגיאה במערכת, השיחה תנותק")

    except Exception as e:
        print(f"CRITICAL IVR HANDLER ERROR: {e}\n{traceback.format_exc()}", flush=True)
        return yemot_read("אירעה שגיאה זמנית בעבודת השרת, אנא נסו שנית", "welcome_choice", "no,1,1,7,Digits,no,no,*/")

def show_personal_area(session: dict, prefix: str = "") -> Response:
    user = session.get("user")
    if not user:
        session["auth_target"] = "PERSONAL_AREA"
        session["step"] = "AUTH"
        return yemot_read("לאזור האישי אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", "no,10,1,7,Digits,no,no,*/")
        
    session["step"] = "PERSONAL_AREA"
    name = clean_tts(get_field(user, "שם פרטי ומשפחה", "שם פרטי", "first_name"))
    addr = clean_tts(get_field(user, "כתובת", "address"))
    code = clean_tts(get_field(user, "קוד קהילה", "community_code", default="לא עודכן"))
    
    if USE_AUDIO_FILES:
        sound_chain = (
            f"f-/{AUDIO_FOLDER}/014a.t-שלום.t-{name}."
            f"f-/{AUDIO_FOLDER}/014b.t-הכתובת הרשומה במערכת היא.t-{addr}."
            f"f-/{AUDIO_FOLDER}/014c.t-קוד הקהילה הרשום במערכת הוא.t-{code}."
            f"f-/{AUDIO_FOLDER}/014d.t-לחזרה לתפריט הראשי הקישו 1, לעדכון קוד הקהילה הקישו 2"
        )
    else:
        sound_chain = f"t-שלום {name}, הכתובת הרשומה במערכת היא {addr}, קוד הקהילה הרשום במערכת הוא {code}. לחזרה לתפריט הראשי הקישו 1, לעדכון קוד הקהילה הקישו 2"

    content = f"read={sound_chain}=personal_choice,no,1,1,7,no,no,no,*/,,,,,,no"
    return Response(content=content, media_type="text/plain; charset=utf-8")

async def show_categories(session: dict, prefix: str = "") -> Response:
    if not session.get("user"):
        session["auth_target"] = "MAIN_MENU"
        session["step"] = "AUTH"
        return yemot_read("לכניסה למערכת ההזמנות אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", "no,10,1,7,Digits,no,no,*/")

    cats = CACHE["categories"]
    if not cats:
        return yemot_msg("מצטערים, אין כרגע קטגוריות זמינות")
        
    cats_text = ""
    for i, c in enumerate(cats, 1):
        cats_text += f"ל{c['category_name']} הקישו {i}, "

    if USE_AUDIO_FILES:
        sound_chain = f"f-/{AUDIO_FOLDER}/017a.t-לתפריט ההזמנות.t-{clean_tts(prefix + cats_text)}.f-/{AUDIO_FOLDER}/017b.t-לסיום הקנייה ומעבר לתשלום הקישו 9"
    else:
        sound_chain = f"t-{clean_tts(prefix)} לתפריט ההזמנות: {clean_tts(cats_text)} לסיום הקנייה ומעבר לתשלום הקישו 9"

    session["step"] = "MAIN_MENU"
    content = f"read={sound_chain}=cat_choice,no,1,1,7,no,no,no,*/,,,,,,no"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def start_product_loop(session: dict) -> Response:
    cat = str(session.get("selected_cat", "")).strip()
    kashrut = session.get("selected_kashrut")
    if kashrut:
        kashrut = str(kashrut).strip()
        
    filtered = [
        p for p in CACHE["products"]
        if str(p.get("category_name", "")).strip().lower() == cat.lower()
        and (not kashrut or str(p.get("kashrut", "")).strip().lower() == kashrut.lower())
    ]
    if not filtered:
        session["step"] = "MAIN_MENU"
        return yemot_read("לא נמצאו מוצרים בקטגוריה זו, מעביר אותך חזרה לקטגוריות", "cat_choice", "no,1,1,7,no,no,no,*/,,,,,,no")
    session["filtered_products"] = filtered
    session["product_index"] = 0
    session["step"] = "PRODUCT_LOOP"
    return play_current_product(session)

def play_current_product(session: dict, prefix: str = "") -> Response:
    products = session["filtered_products"]
    idx = session["product_index"]
    p = products[idx]
    
    p_name = clean_tts(p['name'])
    p_sku = clean_tts(p['sku'])
    p_price = clean_tts(p['price'])
    p_notes = clean_tts(p['notes']) if p.get('notes') else ""

    if USE_AUDIO_FILES:
        sound_chain = (
            f"f-/{AUDIO_FOLDER}/022a.t-מוצר.t-{p_name}."
            f"f-/{AUDIO_FOLDER}/022b.t-מקט.t-{p_sku}."
            f"f-/{AUDIO_FOLDER}/022c.t-מחיר ליחידה.t-{p_price}."
            f"f-/{AUDIO_FOLDER}/022d.t-שקלים."
        )
        if p_notes:
            sound_chain += f"f-/{AUDIO_FOLDER}/022e.t-הערה.t-{p_notes}."
        sound_chain += f"f-/{AUDIO_FOLDER}/022f.t-להזמנת מוצר זה הקישו 1, להמשך למוצר הבא הקישו 2, למעבר לקטגוריה אחרת הקישו 3, לסיום הקנייה ומעבר לתשלום הקישו 9"
    else:
        notes_str = f" הערה: {p_notes}," if p_notes else ""
        sound_chain = f"t-{clean_tts(prefix)}מוצר: {p_name}, מקט {p_sku}, מחיר ליחידה {p_price} שקלים,{notes_str} להזמנת מוצר זה הקישו 1, להמשך למוצר הבא הקישו 2, למעבר לקטגוריה אחרת הקישו 3, לסיום הקנייה ומעבר לתשלום הקישו 9"

    content = f"read={sound_chain}=product_choice,no,1,1,7,no,no,no,*/,,,,,,no"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def play_catalog_product(session: dict, prefix: str = "") -> Response:
    products = session.get("filtered_products", [])
    if not products:
        return yemot_msg("מצטערים, אין כרגע מוצרים בקטלוג")
    idx = session.get("product_index", 0)
    p = products[idx]
    
    p_name = clean_tts(p['name'])
    p_sku = clean_tts(p['sku'])
    p_price = clean_tts(p['price'])
    p_notes = clean_tts(p['notes']) if p.get('notes') else ""

    if USE_AUDIO_FILES:
        sound_chain = (
            f"f-/{AUDIO_FOLDER}/018a.t-מוצר.t-{p_name}."
            f"f-/{AUDIO_FOLDER}/018b.t-מקט.t-{p_sku}."
            f"f-/{AUDIO_FOLDER}/018c.t-מחיר ליחידה.t-{p_price}."
            f"f-/{AUDIO_FOLDER}/018d.t-שקלים."
        )
        if p_notes:
            sound_chain += f"f-/{AUDIO_FOLDER}/018e.t-הערה.t-{p_notes}."
        sound_chain += f"f-/{AUDIO_FOLDER}/018f.t-למוצר הבא הקישו 1, לחזרה לתפריט הראשי הקישו 2"
    else:
        notes_str = f" הערה: {p_notes}," if p_notes else ""
        sound_chain = f"t-{clean_tts(prefix)}מוצר: {p_name}, מקט {p_sku}, מחיר ליחידה {p_price} שקלים.{notes_str} למוצר הבא הקישו 1, לחזרה לתפריט הראשי הקישו 2"

    content = f"read={sound_chain}=catalog_choice,no,1,1,7,no,no,no,*/,,,,,,no"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def yemot_read_qty(product_name: str) -> Response:
    p_name = clean_tts(product_name)
    if USE_AUDIO_FILES:
        sound_chain = f"f-/{AUDIO_FOLDER}/020a.t-הקש את מספר הפריטים שברצונך להזמין ממוצר.t-{p_name}"
    else:
        sound_chain = f"t-הקש את מספר הפריטים שברצונך להזמין ממוצר {p_name}"
        
    content = f"read={sound_chain}=qty_input,no,3,1,7,Digits,no,no,*/"
    return Response(content=content, media_type="text/plain; charset=utf-8")

# -------------------------------------------------------------------
# 5. תחילת יציאה לתשלום: הודעה על 10 ש"ח + אישור (1 לאישור, 2 לביטול)
# -------------------------------------------------------------------
def initiate_checkout(session: dict) -> Response:
    cart = session.get("cart", [])
    if not cart:
        return yemot_msg("סל הקניות שלך ריק, תודה ולהתראות")
    
    cart_sum = int(sum(item["total"] for item in cart))
    total_with_fee = cart_sum + 10
    session["total_sum_with_fee"] = total_with_fee
    session["step"] = "CONFIRM_CHECKOUT_FEE"
    
    part1_text = "שימו לב בכל הזמנה יתווספו לתשלום דמי החזקת תחנת החלוקה בסך של 10 שקלים סך הכל לתשלום כולל דמי החזקה הוא"
    part2_text = "שקלים לאישור ומעבר לתשלום הקישו 1 לביטול ההזמנה הקישו 2"
    
    if USE_AUDIO_FILES:
        sound_chain = f"f-/{AUDIO_FOLDER}/023a.t-{clean_tts(part1_text)}.n-{total_with_fee}.f-/{AUDIO_FOLDER}/023b.t-{clean_tts(part2_text)}"
    else:
        sound_chain = f"t-{clean_tts(part1_text)}.n-{total_with_fee}.t-{clean_tts(part2_text)}"

    content = f"read={sound_chain}=checkout_confirm_choice,no,1,1,7,no,no,no,*/,,,,,,no"
    return Response(content=content, media_type="text/plain; charset=utf-8")

# -------------------------------------------------------------------
# 6. מעבר סופי לסליקת אשראי - תשלום 1 בלבד
# -------------------------------------------------------------------
def finish_checkout(session: dict, background_tasks: BackgroundTasks) -> Response:
    cart = session.get("cart", [])
    call_id = session.get("call_id")
    phone = session.get("phone", "")
    
    if not cart:
        background_tasks.add_task(log_general_event, call_id, phone, "סיום שיחה", "יצא ללא הזמנה")
        return yemot_msg("סל הקניות שלך ריק, תודה ולהתראות")
    
    cart_sum = int(sum(item["total"] for item in cart))
    total_sum = session.get("total_sum_with_fee") or (cart_sum + 10)
    
    user = session.get("user") or {}
    user_id = get_field(user, "תעודת זהות", "id_number") or get_field(user, "מספר טלפון", "phone") or phone
    if user_id and user_id in SAVED_CARTS:
        del SAVED_CARTS[user_id]
        
    background_tasks.add_task(log_transaction_to_sheet, session)
    background_tasks.add_task(log_general_event, call_id, phone, "הזמנה הושלמה - מעבר לסליקה", f"סה\"כ כולל דמי החזקה {total_sum} ש\"ח")
    
    if call_id in SESSIONS:
        del SESSIONS[call_id]
        
    part1_text = "סך הכל לתשלום"
    part2_text = "שקלים מועברים כעת לסליקת אשראי"
    
    if USE_AUDIO_FILES:
        msg_chain = f"f-/{AUDIO_FOLDER}/025a.t-{clean_tts(part1_text)}.n-{total_sum}.f-/{AUDIO_FOLDER}/025b.t-{clean_tts(part2_text)}"
    else:
        msg_chain = f"t-{clean_tts(part1_text)}.n-{total_sum}.t-{clean_tts(part2_text)}"
    
    credit_card_cmd = f"credit_card={CREDIT_CARD_PROVIDER},{total_sum},{CREDIT_CARD_MAX_PAYMENTS},{CREDIT_CARD_CURRENCY},,,,{CREDIT_CARD_REGISTER_NO}"
    
    content = f"id_list_message={msg_chain}&{credit_card_cmd}"
    return Response(content=content, media_type="text/plain; charset=utf-8")
