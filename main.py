import os
import json
import requests
from datetime import datetime
from typing import Dict, Any
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import Response

app = FastAPI(title="Yemot Sales IVR System")

APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL")

CACHE = {
    "users": {},
    "categories": [],
    "products": []
}

SESSIONS: Dict[str, Dict[str, Any]] = {}

def get_field(item: dict, *keys, default=""):
    """שליפת ערך מתוך מילון עם תמיכה בשמות עמודות בעברית ובאנגלית"""
    for k in keys:
        if k in item and item[k] is not None and str(item[k]).strip() != "":
            return item[k]
    return default

def load_data_from_sheets():
    """טעינת נתונים מ-Google Sheets"""
    if not APPS_SCRIPT_URL:
        print(" Error: APPS_SCRIPT_URL variable is missing!")
        return
        
    try:
        response = requests.get(APPS_SCRIPT_URL, timeout=10)
        data = response.json()
        
        # 1. משתמשים
        users_dict = {}
        for u in data.get("users", []):
            is_active = str(get_field(u, "פעיל", "is_active", default="TRUE")).upper()
            if is_active in ["TRUE", "1", "YES"]:
                id_num = str(get_field(u, "תעודת זהות", "id_number")).strip()
                phone = str(get_field(u, "מספר טלפון", "phone")).strip()
                if id_num: users_dict[id_num] = u
                if phone: users_dict[phone] = u
        CACHE["users"] = users_dict
        
        # 2. קטגוריות
        cats = []
        for c in data.get("categories", []):
            cats.append({
                "category_id": get_field(c, "מזהה קטגוריה", "category_id"),
                "category_name": get_field(c, "שם קטגוריה", "category_name"),
                "kashruts": get_field(c, "כשרויות זמינות", "kashruts")
            })
        CACHE["categories"] = cats
        
        # 3. מוצרים
        prods = []
        for p in data.get("products", []):
            in_stock = str(get_field(p, "במלאי", "in_stock", default="TRUE")).upper()
            if in_stock in ["TRUE", "1", "YES"]:
                prods.append({
                    "sku": str(get_field(p, "מקט", "sku")),
                    "name": get_field(p, "שם מוצר", "name"),
                    "price": get_field(p, "מחיר ליחידה", "price"),
                    "display_price": get_field(p, "מחיר תצוגה", "display_price"),
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
    """כתיבה ללוג הכללי בגיליון"""
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
        print(f" Error logging general event: {e}")

def log_transaction_to_sheet(session_data: dict):
    """כתיבה ללוג העסקאות בגיליון"""
    if not APPS_SCRIPT_URL:
        return
    try:
        user = session_data.get("user", {})
        cart = session_data.get("cart", [])
        items_summary = "; ".join([f"{item['name']} (מק\"ט {item['sku']}) x {item['qty']} = {item['total']} ש\"ח" for item in cart])
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
    except Exception as e:
        print(f" Error logging transaction: {e}")

def yemot_read(text: str, var_name: str, max_digits=10, min_digits=1, sec=7, sec_type="Numeric") -> Response:
    content = f"read=t-{text}={var_name},{min_digits},{max_digits},{sec},{sec_type},no,TAP,no"
    return Response(content=content, media_type="text/plain; charset=utf-8")

def yemot_msg(text: str) -> Response:
    content = f"id_list_message=t-{text}"
    return Response(content=content, media_type="text/plain; charset=utf-8")

#Обраפ מקבל קריאות ישירות מנתיב השורש /
@app.api_route("/", methods=["GET", "POST"])
async def ivr_handler(request: Request, background_tasks: BackgroundTasks):
    params = dict(request.query_params)
    if request.method == "POST":
        form_data = await request.form()
        params.update(dict(form_data))
        
    call_id = params.get("ApiCallId") or params.get("phone") or "default_session"
    phone = params.get("ApiPhone", "").strip()
    user_input = params.get("ApiRealAnswer", "").strip()
    
    if call_id not in SESSIONS:
        SESSIONS[call_id] = {
            "step": "AUTH", "user": None, "cart": [], "selected_cat": None,
            "selected_kashrut": None, "filtered_products": [], "product_index": 0,
            "pending_qty": 0, "call_id": call_id, "phone": phone
        }
        background_tasks.add_task(log_general_event, call_id, phone, "כניסה לשיחה", "התחלת שיחה חדשה")
        
    session = SESSIONS[call_id]
    step = session["step"]
    
    # 1. זיהוי מורשים
    if step == "AUTH":
        if not user_input:
            if phone in CACHE["users"]:
                session["user"] = CACHE["users"][phone]
                session["step"] = "MAIN_MENU"
                background_tasks.add_task(log_general_event, call_id, phone, "זיהוי אוטומטי", f"זוהה לפי טלפון {phone}")
                return await show_categories(session)
            return yemot_read("שלום. אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", 10, 7)
        
        if user_input in CACHE["users"]:
            session["user"] = CACHE["users"][user_input]
            session["step"] = "MAIN_MENU"
            background_tasks.add_task(log_general_event, call_id, phone, "זיהוי מוצלח", f"זוהה לפי {user_input}")
            return await show_categories(session)
        else:
            session["step"] = "NOT_AUTHORIZED_CHOICE"
            background_tasks.add_task(log_general_event, call_id, phone, "זיהוי נכשל", f"הוקש {user_input} - לא במורשים")
            return yemot_read("המערכת מזהה כי אינך רשום למערכת. להקשת מספר אחר הקישו 1, למעבר לרישום למערכת הקישו 2", "unauth_choice", 1, 1)

    elif step == "NOT_AUTHORIZED_CHOICE":
        if user_input == "1":
            session["step"] = "AUTH"
            return yemot_read("אנא הקישו את מספר תעודת הזהות או מספר הטלפון שלכם ולאחר מכן הקישו סולמית", "auth_id", 10, 7)
        elif user_input == "2":
            del SESSIONS[call_id]
            return yemot_msg("הועברתם לרישום. אנא פנו לשירות הלקוחות. תודה ולהתראות")
        else:
            return yemot_read("הקשה שגויה. להקשת מספר אחר הקישו 1, למעבר לרישום הקישו 2", "unauth_choice", 1, 1)

    # 2. תפריט קטגוריות
    elif step == "MAIN_MENU":
        cats = CACHE["categories"]
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
                
                k_text = f"בחרת בקטגוריית {selected_cat['category_name']}. "
                for i, k in enumerate(kashruts, 1):
                    k_text += f"לכשרות {k} הקישו {i}. "
                return yemot_read(k_text, "kashrut_choice", 1, 1)
            else:
                return await show_categories(session, prefix="הקשה שגויה. ")
        except ValueError:
            return await show_categories(session, prefix="הקשה שגויה. ")

    # 3. תפריט כשרויות
    elif step == "KASHRUT_MENU":
        kashruts = session.get("available_kashruts", [])
        try:
            choice_idx = int(user_input) - 1
            if 0 <= choice_idx < len(kashruts):
                session["selected_kashrut"] = kashruts[choice_idx]
                return start_product_loop(session)
            else:
                return yemot_read("הקשה שגויה. אנא בחר כשרות מתוך הרשימה", "kashrut_choice", 1, 1)
        except ValueError:
            return yemot_read("הקשה שגויה. אנא בחר כשרות מתוך הרשימה", "kashrut_choice", 1, 1)

    # 4. דפדוף במוצרים
    elif step == "PRODUCT_LOOP":
        products = session["filtered_products"]
        idx = session["product_index"]
        
        if user_input == "1":
            session["step"] = "QTY_INPUT"
            p = products[idx]
            return yemot_read(f"הקש את מספר הפריטים שברצונך להזמין ממוצר {p['name']}", "qty_input", 3, 1)
        elif user_input == "2":
            session["product_index"] = (idx + 1) % len(products)
            return play_current_product(session)
        elif user_input == "3":
            session["step"] = "MAIN_MENU"
            return await show_categories(session)
        elif user_input == "9":
            return finish_checkout(session, background_tasks)
        else:
            return play_current_product(session, prefix="הקשה שגויה. ")

    # 5. כמות ואישור
    elif step == "QTY_INPUT":
        try:
            qty = int(user_input)
            if qty <= 0:
                return yemot_read("כמות חייבת להיות גדולה מאפס. אנא הקש כמות תקינה", "qty_input", 3, 1)
            p = session["filtered_products"][session["product_index"]]
            total_price = qty * float(p["price"])
            session["pending_qty"] = qty
            session["pending_total"] = total_price
            session["step"] = "CONFIRM_ORDER"
            msg = f"בחרת להזמין {qty} יחידות ממוצר {p['name']}. העלות הכוללת היא {int(total_price)} שקלים. לאישור הקישו 1, לביטול הקישו 2"
            return yemot_read(msg, "confirm_choice", 1, 1)
        except ValueError:
            return yemot_read("הקשה שגויה. אנא הקש כמות במספרים בלבד", "qty_input", 3, 1)

    elif step == "CONFIRM_ORDER":
        if user_input == "1":
            p = session["filtered_products"][session["product_index"]]
            session["cart"].append({
                "sku": p["sku"], "name": p["name"], "qty": session["pending_qty"], "total": session["pending_total"]
            })
            background_tasks.add_task(log_general_event, call_id, phone, "הוספה לסל", f"נוסף {p['name']} כמות: {session['pending_qty']}")
            session["step"] = "AFTER_ADD_MENU"
            msg = "המוצר נוסף בהצלחה לסל הקניות שלך. למוצר הבא הקישו 1, למעבר לקטגוריה אחרת הקישו 2, לסיום ההזמנה הקישו 9"
            return yemot_read(msg, "after_add_choice", 1, 1)
        else:
            session["step"] = "PRODUCT_LOOP"
            return play_current_product(session, prefix="ההזמנה בוטלה. ")

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
            return yemot_read("הקשה שגויה. למוצר הבא הקישו 1, לקטגוריה אחרת הקישו 2, לסיום הקישו 9", "after_add_choice", 1, 1)

    return yemot_msg("אירעה שגיאה במערכת, השיחה תנותק")

async def show_categories(session: dict, prefix: str = "") -> str:
    cats = CACHE["categories"]
    if not cats:
        return yemot_msg("מצטערים, אין כרגע קטגוריות זמינות")
    text = prefix + "לתפריט ההזמנות: "
    for i, c in enumerate(cats, 1):
        text += f"ל{c['category_name']} הקישו {i}. "
    session["step"] = "MAIN_MENU"
    return yemot_read(text, "cat_choice", 1, 1)

def start_product_loop(session: dict) -> str:
    cat = session["selected_cat"]
    kashrut = session["selected_kashrut"]
    filtered = [
        p for p in CACHE["products"]
        if str(p.get("category_name")).strip() == cat
        and (kashrut is None or str(p.get("kashrut")).strip() == kashrut)
    ]
    if not filtered:
        session["step"] = "MAIN_MENU"
        return yemot_read("לא נמצאו מוצרים בקטגוריה זו. מעביר אותך חזרה לקטגוריות", "cat_choice", 1, 1)
    session["filtered_products"] = filtered
    session["product_index"] = 0
    session["step"] = "PRODUCT_LOOP"
    return play_current_product(session)

def play_current_product(session: dict, prefix: str = "") -> str:
    products = session["filtered_products"]
    p = products[session["product_index"]]
    notes_str = f" הערה: {p['notes']}." if p.get('notes') else ""
    display_price_str = f" המחיר המופיע על המוצר הוא {p['display_price']} שקלים." if p.get('display_price') else ""
    msg = (
        f"{prefix}מוצר: {p['name']}. מק\"ט {p['sku']}. מחיר ליחידה {p['price']} שקלים.{display_price_str}{notes_str} "
        f"להזמנת מוצר זה הקישו 1, להמשך למוצר הבא הקישו 2, למעבר לקטגוריה אחרת הקישו 3"
    )
    return yemot_read(msg, "product_choice", 1, 1)

def finish_checkout(session: dict, background_tasks: BackgroundTasks) -> str:
    cart = session.get("cart", [])
    call_id = session.get("call_id")
    phone = session.get("phone", "")
    
    if not cart:
        background_tasks.add_task(log_general_event, call_id, phone, "סיום שיחה", "יצא ללא הזמנה")
        return yemot_msg("סל הקניות שלך ריק. תודה ולהתראות!")
    
    total_sum = sum(item["total"] for item in cart)
    background_tasks.add_task(log_transaction_to_sheet, session)
    background_tasks.add_task(log_general_event, call_id, phone, "הזמנה הושלמה", f"סה\"כ {total_sum} ש\"ח")
    
    if call_id in SESSIONS:
        del SESSIONS[call_id]
        
    return yemot_msg(f"הזמנתך נקלטה בהצלחה! סך הכל לתשלום: {int(total_sum)} שקלים. תודה רבה ולהתראות!")
