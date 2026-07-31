import io
import os
import json
import requests
import speech_recognition as sr
from pydub import AudioSegment
import imageio_ffmpeg
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import Response

# הגדרת pydub להשתמש בממיר ffmpeg המובנה
AudioSegment.converter = imageio_ffmpeg.get_ffmpeg_exe()

app = FastAPI(title="Yemot Sales IVR System")

APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")

CACHE = {
    "users": {},
    "categories": [],
    "products": []
}

SESSIONS: Dict[str, Dict[str, Any]] = {}

STEP_PARAM_MAP = {
    "WELCOME": ["welcome_choice", "ApiRealAnswer"],
    "AUTH": ["auth_id", "ApiRealAnswer"],
    "NOT_AUTHORIZED_CHOICE": ["unauth_choice", "ApiRealAnswer"],
    "REG_NAME": ["reg_name", "ApiRealAnswer"],
    "CONFIRM_REG_NAME": ["confirm_reg_name", "ApiRealAnswer"],
    "REG_ID": ["reg_id", "ApiRealAnswer"],
    "CONFIRM_REG_ID": ["confirm_reg_id", "ApiRealAnswer"],
    "REG_PHONE": ["reg_phone", "ApiRealAnswer"],
    "CONFIRM_REG_PHONE": ["confirm_reg_phone", "ApiRealAnswer"],
    "REG_ADDRESS": ["reg_address", "ApiRealAnswer"],
    "CONFIRM_REG_ADDRESS": ["confirm_reg_address", "ApiRealAnswer"],
    "MAIN_MENU": ["cat_choice", "ApiRealAnswer"],
    "KASHRUT_MENU": ["kashrut_choice", "ApiRealAnswer"],
    "PRODUCT_LOOP": ["product_choice", "ApiRealAnswer"],
    "QTY_INPUT": ["qty_input", "ApiRealAnswer"],
    "CONFIRM_ORDER": ["confirm_choice", "ApiRealAnswer"],
    "AFTER_ADD_MENU": ["after_add_choice", "ApiRealAnswer"]
}

def transcribe_hebrew_audio(audio_path_or_url: str) -> str:
    """הורדת קובץ השמע, המרתו ל-PCM WAV בזיכרון ותמלול חינמי בעברית"""
    if not audio_path_or_url:
        return ""
        
    if not audio_path_or_url.startswith("http"):
        audio_url = "https://f2.freeivr.co.il/files/" + audio_path_or_url.lstrip("/")
    else:
        audio_url = audio_path_or_url

    try:
        # 1. הורדת הקובץ מימות המשיח
        response = requests.get(audio_url, timeout=10)
        
        # 2. המרה של הקובץ הדחוס (GSM/u-law) ל-PCM WAV לא-דחוס בזיכרון
        audio = AudioSegment.from_file(io.BytesIO(response.content))
        pcm_wav_bytes = io.BytesIO()
        audio.export(pcm_wav_bytes, format="wav")
        pcm_wav_bytes.seek(0)
        
        # 3. תמלול הקובץ בעברית בחינם
        r = sr.Recognizer()
        with sr.AudioFile(pcm_wav_bytes) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data, language="he-IL")
            print(f" Transcribed text: {text}")
            return text.strip()
    except Exception as e:
        print(f" Error transcribing audio: {e}")
        return ""

def clean_input(val: str) -> str:
    """ניקוי תווי לוואי מהקשת המשתמש"""
    if not val:
        return ""
    val = str(val).strip()
    val = val.replace("#", "").replace("*", "")
    if val.startswith("Digits-"):
        val = val.replace("Digits-", "")
    return val.strip()

def clean_tts(text: str) -> str:
    """מנקה תווי הפרדה שעלולים לשבור את ה-Parser של ימות המשיח"""
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
    for k in keys:
        if k in item and item[k] is not None and str(item[k]).strip() != "":
            return item[k]
    return default

def load_data_from_sheets():
    if not APPS_SCRIPT_URL:
        print(" Error: APPS_SCRIPT_URL variable is missing!")
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
                if id_num: users_dict[id_num] = u
                if phone: users_dict[phone] = u
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
        print(" Data successfully reloaded from Sheets!")
    except Exception as e:
        print(f" Error loading data: {e}")

@app.on_event("startup")
async def startup_event():
    load_data_from_sheets()

@app.get("/refresh-cache")
async def refresh_cache():
    load_data_from_sheets()
    return {"status": "success", "message": "Cache refreshed"}

def log_general_event(call_id: str, phone: str, event_type: str, details: str):
    if not APPS_SCRIPT_URL: return
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
    except Exception as e: print(f" Error logging general event: {e}")

def save_new_user_to_sheet(user_data: dict):
    if not APPS_SCRIPT_URL: return
    try:
        payload = {
            "type": "register_user",
            "id_number": str(user_data.get("id_number", "")),
            "phone": str(user_data.get("phone", "")),
            "first_name": str(user_data.get("first_name", "")),
            "last_name": "",
            "address": str(user_data.get("address", ""))
        }
        requests.post(APPS_SCRIPT_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=10)
        print(" New user registered to Sheet!")
    except Exception as e: print(f" Error registering user: {e}")

def log_transaction_to_sheet(session_data: dict):
    if not APPS_SCRIPT_URL: return
    try:
        user = session_data.get("user", {})
        cart = session_data.get("cart", [])
        items_summary = "; ".join([f"{item['name']} מקט {item['sku']} כמות {item['qty']} סך הכל {item['total']} שח" for item in cart])
        total_sum = sum(item['total'] for item in cart)
        
        first_name = get_field(user, "שם פרטי", "first_name")
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
            "status": "אושר"
        }
        requests.post(APPS_SCRIPT_URL, data=json.dumps(payload), headers={"Content-Type": "application/json"}, timeout=10)
    except Exception as e: print(f" Error logging transaction: {e}")

def yemot_read(text: str, var_name: str, max_digits=10, min_digits=1, sec=7, sec_type="Number") -> Response:
    clean_text = clean_tts(text)
    content = f"read=t-{clean_text}={var_name},no,{max_digits},{min_digits},{sec},{sec_type},no,no,*/"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def yemot_read_record(text: str, var_name: str, sec=10) -> Response:
    """הוראת הקלטה חינמית מימות המשיח לקובץ שמע"""
    clean_text = clean_tts(text)
    content = f"read=t-{clean_text}={var_name},no,record,/ApiRecord,file_name,no,yes,yes,2,{sec}"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def yemot_msg(text: str) -> Response:
    clean_text = clean_tts(text)
    content = f"id_list_message=t-{clean_text}"
    return Response(content=content, media_type="text/plain; charset=utf-8")

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
    
    if call_id not in SESSIONS:
        SESSIONS[call_id] = {
            "step": "WELCOME", "user": None, "cart": [], "selected_cat": None,
            "selected_kashrut": None, "filtered_products": [], "product_index": 0,
            "pending_qty": 0, "call_id": call_id, "phone": phone, "reg_data": {}
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
    
    # ---------------------------------------------------------
    # שלב פתיחה: בחירת כניסה או רישום
    # ---------------------------------------------------------
    if step == "WELCOME":
        if not user_input:
            if phone in CACHE["users"]:
                session["user"] = CACHE["users"][phone]
                session["step"] = "MAIN_MENU"
                background_tasks.add_task(log_general_event, call_id, phone, "זיהוי אוטומטי", f"זוהה לפי טלפון {phone}")
                return await show_categories(session, prefix="שלום, ברוכים הבאים, ")
            return yemot_read("שלום וברוכים הבאים למערכת ההזמנות, לכניסה למערכת הקישו 1, לרישום למערכת הקישו 2", "welcome_choice", max_digits=1, min_digits=1)
        
        if user_input == "1":
            session["step"] = "AUTH"
            return yemot_read("אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", max_digits=10, min_digits=1)
        elif user_input == "2":
            session["step"] = "REG_NAME"
            return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name")
        else:
            return yemot_read("הקשה שגויה, לכניסה למערכת הקישו 1, לרישום למערכת הקישו 2", "welcome_choice", max_digits=1, min_digits=1)

    # ---------------------------------------------------------
    # שלב 1: זיהוי מורשים
    # ---------------------------------------------------------
    elif step == "AUTH":
        if not user_input:
            return yemot_read("אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", max_digits=10, min_digits=1)
        
        if user_input in CACHE["users"]:
            session["user"] = CACHE["users"][user_input]
            session["step"] = "MAIN_MENU"
            background_tasks.add_task(log_general_event, call_id, phone, "זיהוי מוצלח", f"זוהה לפי {user_input}")
            return await show_categories(session)
        else:
            session["step"] = "NOT_AUTHORIZED_CHOICE"
            background_tasks.add_task(log_general_event, call_id, phone, "זיהוי נכשל", f"הוקש {user_input} - לא במורשים")
            return yemot_read("המערכת מזהה כי אינך רשום למערכת, להקשת מספר אחר הקישו 1, למעבר לרישום למערכת הקישו 2", "unauth_choice", max_digits=1, min_digits=1)

    elif step == "NOT_AUTHORIZED_CHOICE":
        if user_input == "1":
            session["step"] = "AUTH"
            return yemot_read("אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", max_digits=10, min_digits=1)
        elif user_input == "2":
            session["step"] = "REG_NAME"
            return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name")
        else:
            return yemot_read("הקשה שגויה, להקשת מספר אחר הקישו 1, למעבר לרישום הקישו 2", "unauth_choice", max_digits=1, min_digits=1)

    # ---------------------------------------------------------
    # תהליך הרשמה (הקלטה חינמית + תמלול בשרת)
    # ---------------------------------------------------------
    elif step == "REG_NAME":
        if not raw_user_input:
            return yemot_read_record("אנא אמרו בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name")
        
        transcribed_text = transcribe_hebrew_audio(raw_user_input)
        if not transcribed_text:
            return yemot_read_record("לא הצלחנו לפענח את הדיבור, אנא אמרו שוב בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name")
            
        session["reg_data"]["first_name"] = transcribed_text
        session["step"] = "CONFIRM_REG_NAME"
        return yemot_read(f"שמכם נקלט כ {transcribed_text}, לאישור הקישו 1, להקלטה מחדש הקישו 2", "confirm_reg_name", max_digits=1, min_digits=1)

    elif step == "CONFIRM_REG_NAME":
        if user_input == "1":
            session["step"] = "REG_ID"
            return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם ולאחר מכן הקישו סולמית", "reg_id", max_digits=9, min_digits=8)
        else:
            session["step"] = "REG_NAME"
            return yemot_read_record("אנא אמרו שוב בקול ברור את שמכם הפרטי והמשפחתי ולאחר מכן הקישו סולמית", "reg_name")

    elif step == "REG_ID":
        if not user_input:
            return yemot_read("אנא הקישו את מספר תעודת הזהות שלכם ולאחר מכן הקישו סולמית", "reg_id", max_digits=9, min_digits=8)
        
        if user_input in CACHE["users"]:
            return yemot_read("מספר תעודת זהות זה כבר רשום במערכת, אנא הקישו מספר תעודת זהות אחר", "reg_id", max_digits=9, min_digits=8)
            
        session["reg_data"]["id_number"] = user_input
        session["step"] = "CONFIRM_REG_ID"
        return yemot_read(f"מספר תעודת הזהות שהקשתם הוא {user_input}, לאישור הקישו 1, להקשה מחדש הקישו 2", "confirm_reg_id", max_digits=1, min_digits=1)

    elif step == "CONFIRM_REG_ID":
        if user_input == "1":
            session["step"] = "REG_PHONE"
            return yemot_read("אנא הקישו את מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "reg_phone", max_digits=10, min_digits=9)
        else:
            session["step"] = "REG_ID"
            return yemot_read("אנא הקישו מחדש את מספר תעודת הזהות ולאחר מכן הקישו סולמית", "reg_id", max_digits=9, min_digits=8)

    elif step == "REG_PHONE":
        if not user_input:
            return yemot_read("אנא הקישו את מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "reg_phone", max_digits=10, min_digits=9)
        session["reg_data"]["phone"] = user_input
        session["step"] = "CONFIRM_REG_PHONE"
        return yemot_read(f"מספר הטלפון שהקשתם הוא {user_input}, לאישור הקישו 1, להקשה מחדש הקישו 2", "confirm_reg_phone", max_digits=1, min_digits=1)

    elif step == "CONFIRM_REG_PHONE":
        if user_input == "1":
            session["step"] = "REG_ADDRESS"
            return yemot_read_record("אנא אמרו בקול ברור את כתובת המגורים המלאה עיר רחוב ומספר בית ולאחר מכן הקישו סולמית", "reg_address")
        else:
            session["step"] = "REG_PHONE"
            return yemot_read("אנא הקישו מחדש את מספר הטלפון ולאחר מכן הקישו סולמית", "reg_phone", max_digits=10, min_digits=9)

    elif step == "REG_ADDRESS":
        if not raw_user_input:
            return yemot_read_record("אנא אמרו בקול ברור את כתובת המגורים ולאחר מכן הקישו סולמית", "reg_address")
            
        transcribed_text = transcribe_hebrew_audio(raw_user_input)
        if not transcribed_text:
            return yemot_read_record("לא הצלחנו לפענח את הדיבור, אנא אמרו שוב בקול ברור את כתובת המגורים ולאחר מכן הקישו סולמית", "reg_address")

        session["reg_data"]["address"] = transcribed_text
        session["step"] = "CONFIRM_REG_ADDRESS"
        return yemot_read(f"הכתובת נקלטה כ {transcribed_text}, לאישור הקישו 1, להקלטה מחדש הקישו 2", "confirm_reg_address", max_digits=1, min_digits=1)

    elif step == "CONFIRM_REG_ADDRESS":
        if user_input == "1":
            user_info = session["reg_data"]
            new_user = {
                "id_number": user_info.get("id_number"),
                "phone": user_info.get("phone"),
                "first_name": user_info.get("first_name"),
                "last_name": "",
                "address": user_info.get("address"),
                "is_active": "TRUE"
            }
            CACHE["users"][user_info["id_number"]] = new_user
            CACHE["users"][user_info["phone"]] = new_user
            session["user"] = new_user
            
            background_tasks.add_task(save_new_user_to_sheet, user_info)
            background_tasks.add_task(log_general_event, call_id, phone, "הרשמה הושלמה", f"נרשם: {user_info.get('first_name')}")
            
            session["step"] = "MAIN_MENU"
            return await show_categories(session, prefix="הרשמתכם הושלמה בהצלחה, מועברים לתפריט ההזמנות, ")
        else:
            session["step"] = "REG_ADDRESS"
            return yemot_read_record("אנא אמרו שוב בקול ברור את כתובת המגורים ולאחר מכן הקישו סולמית", "reg_address")

    # ---------------------------------------------------------
    # שלב 2: תפריט קטגוריות
    # ---------------------------------------------------------
    elif step == "MAIN_MENU":
        cats = CACHE["categories"]
        if user_input == "9":
            return finish_checkout(session, background_tasks)
            
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
                
                k_text = f"בחרת בקטגוריית {selected_cat['category_name']}, "
                for i, k in enumerate(kashruts, 1):
                    k_text += f"לכשרות {k} הקישו {i}, "
                return yemot_read(k_text, "kashrut_choice", max_digits=1, min_digits=1)
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
            return finish_checkout(session, background_tasks)
            
        try:
            choice_idx = int(user_input) - 1
            if 0 <= choice_idx < len(kashruts):
                session["selected_kashrut"] = kashruts[choice_idx]
                return start_product_loop(session)
            else:
                return yemot_read("הקשה שגויה, אנא בחר כשרות מתוך הרשימה", "kashrut_choice", max_digits=1, min_digits=1)
        except ValueError:
            return yemot_read("הקשה שגויה, אנא בחר כשרות מתוך הרשימה", "kashrut_choice", max_digits=1, min_digits=1)

    # ---------------------------------------------------------
    # שלב 4: דפדוף במוצרים
    # ---------------------------------------------------------
    elif step == "PRODUCT_LOOP":
        products = session["filtered_products"]
        idx = session["product_index"]
        
        if user_input == "1":
            session["step"] = "QTY_INPUT"
            p = products[idx]
            return yemot_read(f"הקש את מספר הפריטים שברצונך להזמין ממוצר {p['name']}", "qty_input", max_digits=3, min_digits=1)
        elif user_input == "2":
            next_idx = (idx + 1) % len(products)
            session["product_index"] = next_idx
            return play_current_product(session)
        elif user_input == "3":
            session["step"] = "MAIN_MENU"
            return await show_categories(session)
        elif user_input == "9":
            return finish_checkout(session, background_tasks)
        else:
            return play_current_product(session, prefix="הקשה שגויה, ")

    # ---------------------------------------------------------
    # שלב 5: הזנת כמות
    # ---------------------------------------------------------
    elif step == "QTY_INPUT":
        try:
            qty = int(user_input)
            if qty <= 0:
                return yemot_read("כמות חייבת להיות גדולה מאפס, אנא הקש כמות תקינה", "qty_input", max_digits=3, min_digits=1)
            p = session["filtered_products"][session["product_index"]]
            total_price = qty * float(p["price"])
            session["pending_qty"] = qty
            session["pending_total"] = total_price
            session["step"] = "CONFIRM_ORDER"
            msg = f"בחרת להזמין {qty} יחידות ממוצר {p['name']}, העלות הכוללת היא {int(total_price)} שקלים, לאישור הקישו 1, לביטול הקישו 2"
            return yemot_read(msg, "confirm_choice", max_digits=1, min_digits=1)
        except ValueError:
            return yemot_read("הקשה שגויה, אנא הקש כמות במספרים בלבד", "qty_input", max_digits=3, min_digits=1)

    elif step == "CONFIRM_ORDER":
        if user_input == "1":
            p = session["filtered_products"][session["product_index"]]
            session["cart"].append({
                "sku": p["sku"], "name": p["name"], "qty": session["pending_qty"], "total": session["pending_total"]
            })
            background_tasks.add_task(log_general_event, call_id, phone, "הוספה לסל", f"נוסף {p['name']} כמות {session['pending_qty']}")
            session["step"] = "AFTER_ADD_MENU"
            msg = "המוצר נוסף בהצלחה לסל הקניות שלך, למוצר הבא הקישו 1, למעבר לקטגוריה אחרת הקישו 2, לסיום הקנייה ומעבר לתשלום הקישו 9"
            return yemot_read(msg, "after_add_choice", max_digits=1, min_digits=1)
        else:
            session["step"] = "PRODUCT_LOOP"
            return play_current_product(session, prefix="ההזמנה בוטלה, ")

    elif step == "AFTER_ADD_MENU":
        if user_input == "1":
            session["product_index"] = (session["product_index"] + 1) % len(session["filtered_products"])
            session["step"] = "PRODUCT_LOOP"
            return play_current_product(session)
        elif user_input == "2":
            session["step"] = "MAIN_MENU"
            return await show_categories(session)
        elif user_input == "9":
            return finish_checkout(session, background_tasks)
        else:
            return yemot_read("הקשה שגויה, למוצר הבא הקישו 1, לקטגוריה אחרת הקישו 2, לסיום הקנייה ומעבר לתשלום הקישו 9", "after_add_choice", max_digits=1, min_digits=1)

    return yemot_msg("אירעה שגיאה במערכת, השיחה תנותק")

async def show_categories(session: dict, prefix: str = "") -> Response:
    cats = CACHE["categories"]
    if not cats:
        return yemot_msg("מצטערים, אין כרגע קטגוריות זמינות")
    text = prefix + "לתפריט ההזמנות: "
    for i, c in enumerate(cats, 1):
        text += f"ל{c['category_name']} הקישו {i}, "
    text += "לסיום הקנייה ומעבר לתשלום הקישו 9"
    session["step"] = "MAIN_MENU"
    return yemot_read(text, "cat_choice", max_digits=1, min_digits=1)

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
        return yemot_read("לא נמצאו מוצרים בקטגוריה זו, מעביר אותך חזרה לקטגוריות", "cat_choice", max_digits=1, min_digits=1)
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
    return yemot_read(msg, "product_choice", max_digits=1, min_digits=1)

def finish_checkout(session: dict, background_tasks: BackgroundTasks) -> Response:
    cart = session.get("cart", [])
    call_id = session.get("call_id")
    phone = session.get("phone", "")
    
    if not cart:
        background_tasks.add_task(log_general_event, call_id, phone, "סיום שיחה", "יצא ללא הזמנה")
        return yemot_msg("סל הקניות שלך ריק, תודה ולהתראות")
    
    total_sum = sum(item["total"] for item in cart)
    background_tasks.add_task(log_transaction_to_sheet, session)
    background_tasks.add_task(log_general_event, call_id, phone, "הזמנה הושלמה", f"סה\"כ {total_sum} ש\"ח")
    
    if call_id in SESSIONS:
        del SESSIONS[call_id]
        
    return yemot_msg(f"הזמנתך נקלטה בהצלחה, סך הכל לתשלום: {int(total_sum)} שקלים, תודה רבה ולהתראות")
