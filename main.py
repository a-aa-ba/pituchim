import os
import io
import json
import requests
import subprocess
import traceback
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import Response
import imageio_ffmpeg
import speech_recognition as sr

app = FastAPI(title="Yemot Sales IVR System")

# ===================================================================
# הגדרה לפתיחה/סגירה של שלוחות 2, 3, 4, 5 (True = פתוח, False = סגור)
IS_SYSTEM_OPEN = True
# ===================================================================

# הגדרות סליקה וטוקן ימות המשיח
YEMOT_TOKEN = os.environ.get("YEMOT_TOKEN", "093136538:112131")
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")

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
    "NOT_AUTHORIZED_CHOICE": ["unauth_choice", "ApiRealAnswer"],
    "REG_NAME": ["reg_name", "my_rec", "ApiRealAnswer"],
    "REG_ID": ["reg_id", "ApiRealAnswer"],
    "REG_PHONE": ["reg_phone", "ApiRealAnswer"],
    "REG_ADDRESS": ["reg_address", "my_rec", "ApiRealAnswer"],
    "REG_COMMUNITY_CODE": ["reg_community_code", "ApiRealAnswer"],
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
    "unauth_choice": "004",
    "reg_name": "005",
    "reg_id": "007",
    "reg_phone": "009",
    "reg_address": "010",
    "reg_community_code": "012",
    "personal_choice": "014",
    "new_community_code": "015",
    "cat_choice": "017",
    "kashrut_choice": "017",
    "catalog_choice": "018",
    "qty_input": "020",
    "product_choice": "022",
    "after_add_choice": "022",
    "checkout_confirm_choice": "023",
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
    if not my_rec_path or not isinstance(my_rec_path, str):
        return ""

    active_token = token or YEMOT_TOKEN
    clean_path = my_rec_path.strip()
    if not clean_path.startswith('/'):
        clean_path = '/' + clean_path

    audio_url = f"https://www.call2all.co.il/ym/api/DownloadFile?token={active_token}&path=ivr2:{clean_path}"

    temp_audio = f"downloaded_{os.getpid()}.file"
    converted_wav = f"converted_{os.getpid()}.wav"

    try:
        res = requests.get(audio_url, timeout=30)
        if res.status_code != 200 or res.content.startswith(b'<') or res.content.startswith(b'{'):
            return ""

        with open(temp_audio, "wb") as f:
            f.write(res.content)

        if not convert_audio_to_pcm_wav(temp_audio, converted_wav):
            target_wav = temp_audio
        else:
            target_wav = converted_wav

        recognizer = sr.Recognizer()
        with sr.AudioFile(target_wav) as source:
            audio_data = recognizer.record(source)
            text = recognizer.recognize_google(audio_data, language='he-IL')

        return text.strip() if text else ""

    except Exception as e:
        print(f"LOG ERROR בתמלול: {e}", flush=True)
        return ""
    finally:
        if os.path.exists(temp_audio):
            try:
                os.remove(temp_audio)
            except Exception:
                pass
        if os.path.exists(converted_wav):
            try:
                os.remove(converted_wav)
            except Exception:
                pass

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

@app.get("/refresh-cache")
async def refresh_cache():
    load_data_from_sheets()
    return {"status": "success", "message": "Cache refreshed"}

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

def save_new_user_to_sheet(user_data: dict):
    if not APPS_SCRIPT_URL:
        return
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
        res = requests.post(APPS_SCRIPT_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=10)
        print(f" LOG: User register sheet response [Code {res.status_code}]: {res.text}", flush=True)
    except Exception as e:
        print(f" LOG ERROR registering user: {e}", flush=True)

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

# זיהוי מספר הקובץ לפי הטקסט או המשתנה
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
        return "018"
    if "סל הקניות שלך ריק" in text:
        return "019"
    if "כמות חייבת להיות גדולה מאפס" in text:
        return "020"
    if "מספרים בלבד" in text:
        return "021"
    if "ההזמנה בוטלה" in text:
        return "024"
    if "סך הכל לתשלום" in text and "מועברים" in text:
        return "025"
    if "יש לך הזמנה פתוחה" in text:
        return "026"
    return PROMPT_FILE_MAP.get(var_name, "001")

# -------------------------------------------------------------------
# פונקציות מענה לימות המשיח - בדיקה אוטומטית: קובץ קודם, ואם אין - TTS
# -------------------------------------------------------------------
def yemot_read(text: str, var_name: str, options: str = "no,1,1,7,Digits,no,no,*/") -> Response:
    clean_text = clean_tts(text)
    file_num = get_prompt_file_num(clean_text, var_name)
    content = f"read=f-הודעות מערכת/{file_num}:t-{clean_text}={var_name},{options}"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def yemot_read_record(text: str, var_name: str, options: str = "no,record", record_folder: str = "/הקלטות") -> Response:
    clean_text = clean_tts(text)
    file_num = get_prompt_file_num(clean_text, var_name)
    content = f"read=f-הודעות מערכת/{file_num}:t-{clean_text}={var_name},{options}&record_folder={record_folder}"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def yemot_msg(text: str) -> Response:
    clean_text = clean_tts(text)
    file_num = get_prompt_file_num(clean_text, "")
    content = f"id_list_message=f-הודעות מערכת/{file_num}:t-{clean_text}"
    return Response(content=content, media_type="text/plain; charset=utf-8")

# בדיקה האם קיימת ללקוח הזמנה פתוחה שלא שולמה
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
        
        # בדיקת סגירת המערכת לשלוחות 2, 3, 4, 5
        if not IS_SYSTEM_OPEN and user_input in ["2", "3", "4", "5"]:
            clean_closed = clean_tts("מערכת ההזמנות סגורה כעת")
            clean_welcome = clean_tts(welcome_text)
            content = f"id_list_message=f-הודעות מערכת/002:t-{clean_closed}&read=f-הודעות מערכת/001:t-{clean_welcome}=welcome_choice,no,1,1,7,Digits,no,no,*/"
            return Response(content=content, media_type="text/plain; charset=utf-8")

        # מעבר מידי לשלוחה 1 ללא הודעה מקדימה
        if user_input == "1":
            return Response(content="go_to_folder=/1", media_type="text/plain; charset=utf-8")
            
        elif user_input == "2":
            user = session.get("user") or CACHE["users"].get(phone)
            if user:
                session["user"] = user
                background_tasks.add_task(log_general_event, call_id, phone, "זיהוי אוטומטי", f"זוהה לפי טלפון {phone}")
                return await check_abandoned_cart_or_proceed(session, background_tasks)
            else:
                session["auth_target"] = "MAIN_MENU"
                session["step"] = "AUTH"
                return yemot_read("אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", "no,10,9,7,Digits,yes,no,*/")
                
        elif user_input == "3":
            session["step"] = "REG_NAME"
            return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "no,record")
            
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
            
        # מעבר מידי לשלוחה 6 ללא הודעה מקדימה
        elif user_input == "6":
            return Response(content="go_to_folder=/6", media_type="text/plain; charset=utf-8")

        # מעבר מידי לשלוחה 7 ללא הודעה מקדימה
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
    # שלבבחירה: שחזור הזמנה קודמת שלא שולמה
    # ---------------------------------------------------------
    elif step == "RESTORE_CART_CHOICE":
        user = session.get("user") or {}
        user_id = get_field(user, "תעודת זהות", "id_number") or get_field(user, "מספר טלפון", "phone") or phone
        
        if user_input == "1":
            # להמשך קנייה זו - שחזור סל קודם
            session["cart"] = SAVED_CARTS.get(user_id, [])
            session["step"] = "MAIN_MENU"
            return await show_categories(session, prefix="ממשיכים את ההזמנה הקודמת, ")
        elif user_input == "2":
            # להתחלת קנייה חדשה - איפוס סל
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
        if not user_input:
            return yemot_read("אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", "no,10,9,7,Digits,no,no,*/")
        
        if user_input in CACHE["users"]:
            session["user"] = CACHE["users"][user_input]
            background_tasks.add_task(log_general_event, call_id, phone, "זיהוי מוצלח", f"זוהה לפי {user_input}")
            
            target = session.get("auth_target", "MAIN_MENU")
            if target == "PERSONAL_AREA":
                return show_personal_area(session)
            else:
                return await check_abandoned_cart_or_proceed(session, background_tasks)
        else:
            session["step"] = "NOT_AUTHORIZED_CHOICE"
            background_tasks.add_task(log_general_event, call_id, phone, "זיהוי נכשל", f"הוקש {user_input} - לא במורשים")
            return yemot_read("המערכת מזהה כי אינך רשום למערכת, להקשת מספר אחר הקישו 1, למעבר לרישום למערכת הקישו 2", "unauth_choice", "no,1,1,7,no,no,no,*/,,,,,,no")

    elif step == "NOT_AUTHORIZED_CHOICE":
        if user_input == "1":
            session["step"] = "AUTH"
            return yemot_read("אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", "no,10,1,7,Digits,no,no,*/")
        elif user_input == "2":
            session["step"] = "REG_NAME"
            return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "no,record")
        else:
            return yemot_read("הקשה שגויה, להקשת מספר אחר הקישו 1, למעבר לרישום הקישו 2", "unauth_choice", "no,1,1,7,no,no,no,*/,,,,,,no")

    # ---------------------------------------------------------
    # תהליך הרשמה (שם -> ת.ז -> טלפון -> כתובת -> קוד קהילה)
    # ---------------------------------------------------------
    elif step == "REG_NAME":
        if not raw_user_input:
            return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "no,record")
        
        transcribed_text = transcribe_audio_file_from_yemot(raw_user_input, token)
        if not transcribed_text:
            return yemot_read_record("לא הצלחנו לפענח את ההקלטה, אנא אמרו שוב בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name", "no,record")
            
        session["reg_data"]["first_name"] = transcribed_text
        session["step"] = "REG_ID"
        return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם ולאחר מכן הקישו סולמית", "reg_id", "no,9,8,7,Digits,no,no,*/")

    elif step == "REG_ID":
        if not user_input:
            return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם ולאחר מכן הקישו סולמית", "reg_id", "no,9,8,7,Digits,no,no,*/")
        
        if user_input in CACHE["users"]:
            return yemot_read("מספר תעודת זהות זה כבר רשום במערכת, אנא הקישו מספר תעודת זהות אחר", "reg_id", "no,9,8,7,Digits,no,no,*/")
            
        session["reg_data"]["id_number"] = user_input
        session["step"] = "REG_PHONE"
        return yemot_read("אנא הקישו את מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "reg_phone", "no,10,9,7,Digits,no,no,*/")

    elif step == "REG_PHONE":
        if not user_input:
            return yemot_read("אנא הקישו את מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "reg_phone", "no,10,9,7,Digits,no,no,*/")
        session["reg_data"]["phone"] = user_input
        session["step"] = "REG_ADDRESS"
        return yemot_read_record("אנא אמרו בקול ברור את כתובת המגורים המלאה עיר רחוב ומספר בית ולאחר מכן הקישו סולמית", "reg_address", "no,record")

    elif step == "REG_ADDRESS":
        if not raw_user_input:
            return yemot_read_record("אנא אמרו בקול ברור את כתובת המגורים ולאחר מכן הקישו סולמית", "reg_address", "no,record")
            
        transcribed_text = transcribe_audio_file_from_yemot(raw_user_input, token)
        if not transcribed_text:
            return yemot_read_record("לא הצלחנו לפענח את ההקלטה, אנא אמרו שוב בקול ברור את כתובת המגורים ולאחר מכן הקישו סולמית", "reg_address", "no,record")

        session["reg_data"]["address"] = transcribed_text
        session["step"] = "REG_COMMUNITY_CODE"
        return yemot_read("אנא הקישו את קוד הקהילה שלכם ולאחר מכן הקישו סולמית, לדילוג הקישו סולמית", "reg_community_code", "no,6,0,7,Digits,no,no,*/")

    elif step == "REG_COMMUNITY_CODE":
        community_code = user_input if user_input not in ["0", "*", "#", ""] else ""
        session["reg_data"]["community_code"] = community_code
        
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
        CACHE["users"][user_info["id_number"]] = new_user
        CACHE["users"][user_info["phone"]] = new_user
        session["user"] = new_user
        
        background_tasks.add_task(save_new_user_to_sheet, user_info)
        background_tasks.add_task(log_general_event, call_id, phone, "הרשמה הושלמה", f"נרשם: {user_info.get('first_name')}")
        
        return await show_categories(session, prefix="הרשמתכם הושלמה בהצלחה, מועברים לתפריט ההזמנות, ")

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
            return yemot_read(f"הקש את מספר הפריטים שברצונך להזמין ממוצר {p['name']}", "qty_input", "no,3,1,7,Digits,no,no,*/")
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
    # שלב 5: הזנת כמות (שמירת הסל בזמן אמת עבור המשתמש)
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
            
            # עדכון סל פתוח בזיכרון בזמן אמת
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
            
            # שזירת ההודעות 023a + n-סכום + 023b
            sound_chain = f"f-הודעות מערכת/023a:t-{clean_tts(part1_text)}.n-{total_with_fee}.f-הודעות מערכת/023b:t-{clean_tts(part2_text)}"
            content = f"read={sound_chain}=checkout_confirm_choice,no,1,1,7,no,no,no,*/,,,,,,no"
            return Response(content=content, media_type="text/plain; charset=utf-8")

    return yemot_msg("אירעה שגיאה במערכת, השיחה תנותק")

def show_personal_area(session: dict, prefix: str = "") -> Response:
    user = session.get("user")
    if not user:
        session["auth_target"] = "PERSONAL_AREA"
        session["step"] = "AUTH"
        return yemot_read("לאזור האישי אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", "no,10,1,7,Digits,no,no,*/")
        
    session["step"] = "PERSONAL_AREA"
    name = get_field(user, "שם פרטי ומשפחה", "שם פרטי", "first_name")
    addr = get_field(user, "כתובת", "address")
    code = get_field(user, "קוד קהילה", "community_code", default="לא עודכן")
    
    msg = f"{prefix}שלום {name}, הכתובת הרשומה במערכת היא {addr}, קוד הקהילה הרשום במערכת הוא {code}. לחזרה לתפריט הראשי הקישו 1, לעדכון קוד הקהילה הקישו 2"
    return yemot_read(msg, "personal_choice", "no,1,1,7,no,no,no,*/,,,,,,no")

async def show_categories(session: dict, prefix: str = "") -> Response:
    if not session.get("user"):
        session["auth_target"] = "MAIN_MENU"
        session["step"] = "AUTH"
        return yemot_read("לכניסה למערכת ההזמנות אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", "no,10,1,7,Digits,no,no,*/")

    cats = CACHE["categories"]
    if not cats:
        return yemot_msg("מצטערים, אין כרגע קטגוריות זמינות")
    text = prefix + "לתפריט ההזמנות: "
    for i, c in enumerate(cats, 1):
        text += f"ל{c['category_name']} הקישו {i}, "
    text += "לסיום הקנייה ומעבר לתשלום הקישו 9"
    session["step"] = "MAIN_MENU"
    return yemot_read(text, "cat_choice", "no,1,1,7,no,no,no,*/,,,,,,no")

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
    
    notes_str = f" הערה: {p['notes']}," if p.get('notes') else ""
    msg = (
        f"{prefix}מוצר: {p['name']}, מקט {p['sku']}, מחיר ליחידה {p['price']} שקלים,{notes_str} "
        f"להזמנת מוצר זה הקישו 1, להמשך למוצר הבא הקישו 2, למעבר לקטגוריה אחרת הקישו 3, לסיום הקנייה ומעבר לתשלום הקישו 9"
    )
    return yemot_read(msg, "product_choice", "no,1,1,7,no,no,no,*/,,,,,,no")

def play_catalog_product(session: dict, prefix: str = "") -> Response:
    products = session.get("filtered_products", [])
    if not products:
        return yemot_msg("מצטערים, אין כרגע מוצרים בקטלוג")
    idx = session.get("product_index", 0)
    p = products[idx]
    
    notes_str = f" הערה: {p['notes']}," if p.get('notes') else ""
    msg = (
        f"{prefix}מוצר: {p['name']}, מקט {p['sku']}, מחיר ליחידה {p['price']} שקלים.{notes_str} "
        f"למוצר הבא הקישו 1, לחזרה לתפריט הראשי הקישו 2"
    )
    return yemot_read(msg, "catalog_choice", "no,1,1,7,no,no,no,*/,,,,,,no")

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
    
    # שזירת ההודעות 023a + n-סכום + 023b
    sound_chain = f"f-הודעות מערכת/023a:t-{clean_tts(part1_text)}.n-{total_with_fee}.f-הודעות מערכת/023b:t-{clean_tts(part2_text)}"
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
    
    # ניקוי הסל הפתוח של המשתמש מזיכרון המערכת לאחר השלמת הזמנה
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
    
    # שזירת ההודעות 025a + n-סכום + 025b
    msg_chain = f"f-הודעות מערכת/025a:t-{clean_tts(part1_text)}.n-{total_sum}.f-הודעות מערכת/025b:t-{clean_tts(part2_text)}"
    
    # שליחת CREDIT_CARD_MAX_PAYMENTS (1) ו-CREDIT_CARD_CURRENCY מפורשות לסליקת תשלום אחד בלבד
    credit_card_cmd = f"credit_card={CREDIT_CARD_PROVIDER},{total_sum},{CREDIT_CARD_MAX_PAYMENTS},{CREDIT_CARD_CURRENCY},,,,{CREDIT_CARD_REGISTER_NO}"
    
    content = f"id_list_message={msg_chain}&{credit_card_cmd}"
    return Response(content=content, media_type="text/plain; charset=utf-8")
