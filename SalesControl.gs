/**
 * ניהול פתיחה וסגירה של המכירות דרך Google Sheets
 *
 * תפקיד הסקריפט:
 * - לקרוא את מצב המכירות ואת רשימת ההחרגות מהגיליון.
 * - להחזיר לשרת את הנתונים כ-JSON רק לאחר אימות מפתח.
 * - לא לבצע קריאות חוזרות בזמן שיחות טלפון. השרת שומר את התוצאה בזיכרון.
 *
 * הפעלה ראשונה: מריצים setupSalesControl() פעם אחת.
 */

const SALES_SETTINGS_SHEET = 'הגדרות מכירות';
const SALES_EXCEPTIONS_SHEET = 'חריגי מכירות';

function getSalesSpreadsheet_() {
  const spreadsheetId = PropertiesService
    .getScriptProperties()
    .getProperty('SPREADSHEET_ID');
  if (!spreadsheetId) {
    throw new Error('חסר מאפיין סקריפט בשם SPREADSHEET_ID.');
  }
  return SpreadsheetApp.openById(spreadsheetId);
}

function setupSalesControl() {
  const ss = getSalesSpreadsheet_();
  if (!ss) {
    throw new Error('יש לפתוח את Apps Script מתוך גיליון Google Sheets של המערכת.');
  }

  // גיליון מצב המכירות
  let settings = ss.getSheetByName(SALES_SETTINGS_SHEET);
  if (!settings) settings = ss.insertSheet(SALES_SETTINGS_SHEET);

  if (settings.getLastRow() === 0) {
    settings.getRange(1, 1, 2, 2).setValues([
      ['הגדרה', 'ערך'],
      ['המכירות פתוחות', 'FALSE']
    ]);
  } else {
    settings.getRange('A1:B1').setValues([['הגדרה', 'ערך']]);
    if (!String(settings.getRange('A2').getDisplayValue()).trim()) {
      settings.getRange('A2:B2').setValues([['המכירות פתוחות', 'FALSE']]);
    }
  }

  settings.setRightToLeft(true);
  settings.setFrozenRows(1);
  settings.setColumnWidth(1, 240);
  settings.setColumnWidth(2, 180);
  settings.getRange('B2').setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(['TRUE', 'FALSE'], true)
      .setAllowInvalid(false)
      .build()
  );
  settings.getRange('B2').setNote(
    'TRUE = המכירות פתוחות לכל המתקשרים. FALSE = המכירות סגורות למעט מספרים פעילים בגיליון החריגים.'
  );
  styleSalesTable_(settings, 2);

  // גיליון מספרים מוחרגים
  let exceptions = ss.getSheetByName(SALES_EXCEPTIONS_SHEET);
  if (!exceptions) exceptions = ss.insertSheet(SALES_EXCEPTIONS_SHEET);

  if (exceptions.getLastRow() === 0) {
    exceptions.getRange(1, 1, 1, 3).setValues([
      ['מספר טלפון', 'פעיל', 'הערות']
    ]);
  } else {
    exceptions.getRange('A1:C1').setValues([
      ['מספר טלפון', 'פעיל', 'הערות']
    ]);
  }

  exceptions.setRightToLeft(true);
  exceptions.setFrozenRows(1);
  exceptions.setColumnWidth(1, 190);
  exceptions.setColumnWidth(2, 110);
  exceptions.setColumnWidth(3, 300);
  exceptions.getRange('A2:A').setNumberFormat('@');
  exceptions.getRange('B2:B').setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(['TRUE', 'FALSE'], true)
      .setAllowInvalid(false)
      .build()
  );
  exceptions.getRange('A1:C1').setNote(
    'מספר פעיל יוכל להיכנס להזמנות גם כשהמכירות סגורות. ההחרגה אינה פותחת שלוחות אחרות.'
  );
  styleSalesTable_(exceptions, 3);

  SpreadsheetApp.flush();
  return 'גיליונות ניהול המכירות הוגדרו בהצלחה.';
}

/**
 * עיצוב אחיד, כותרות כחולות, כיוון ימין-לשמאל, שורת כותרת קבועה וסינון.
 */
function styleSalesTable_(sheet, columns) {
  sheet.setRightToLeft(true);
  sheet.setFrozenRows(1);

  const header = sheet.getRange(1, 1, 1, columns);
  header
    .setBackground('#1A73E8')
    .setFontColor('#FFFFFF')
    .setFontWeight('bold')
    .setFontSize(11)
    .setHorizontalAlignment('center')
    .setVerticalAlignment('middle');

  sheet.setRowHeight(1, 34);

  const rowCount = Math.max(sheet.getLastRow(), 2);
  const dataRange = sheet.getRange(1, 1, rowCount, columns);
  dataRange
    .setFontFamily('Arial')
    .setVerticalAlignment('middle')
    .setWrap(true);

  sheet.getBandings().forEach(banding => banding.remove());
  dataRange.applyRowBanding(SpreadsheetApp.BandingTheme.LIGHT_GREY);

  if (sheet.getFilter()) sheet.getFilter().remove();
  dataRange.createFilter();
}

/**
 * נקודת הקצה שהשרת קורא לה בעת הפעלה או ברענון ידני בלבד.
 * בזמן שיחת טלפון השרת אינו פונה שוב ל-Google Sheets.
 */
function doGet(e) {
  const expectedKey = PropertiesService
    .getScriptProperties()
    .getProperty('SALES_CONTROL_KEY');

  const suppliedKey = e && e.parameter
    ? String(e.parameter.key || '')
    : '';

  if (!expectedKey || suppliedKey !== expectedKey) {
    return jsonOutput_({ error: 'unauthorized' });
  }

  const ss = getSalesSpreadsheet_();
  const settings = ss.getSheetByName(SALES_SETTINGS_SHEET);
  const exceptionsSheet = ss.getSheetByName(SALES_EXCEPTIONS_SHEET);

  if (!settings || !exceptionsSheet) {
    return jsonOutput_({ error: 'sheets_not_initialized' });
  }

  const openValue = String(settings.getRange('B2').getDisplayValue())
    .trim()
    .toUpperCase();

  const rows = exceptionsSheet.getDataRange().getDisplayValues();
  const exceptions = [];

  for (let i = 1; i < rows.length; i++) {
    const phone = normalizeSalesPhone_(rows[i][0]);
    const active = String(rows[i][1] || '').trim().toUpperCase();

    if (phone && ['TRUE', '1', 'YES', 'כן'].includes(active)) {
      exceptions.push(phone);
    }
  }

  return jsonOutput_({
    sales_open: ['TRUE', '1', 'YES', 'כן'].includes(openValue),
    exceptions: [...new Set(exceptions)],
    password_hashes: readPasswordHashes_(ss)
  });
}

function normalizeSalesPhone_(value) {
  let digits = String(value || '').replace(/\D/g, '');

  if (digits.startsWith('972') && digits.length >= 11) {
    digits = '0' + digits.slice(3);
  }

  return digits;
}

function jsonOutput_(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}


/**
 * עיצוב מחדש של כל הגיליונות והמרת שמות עמודות לאחידות בעברית.
 * הפעולה משנה רק את שורת הכותרת ואת העיצוב. ערכי הנתונים בשורות 2 ומטה
 * אינם נקראים לצורך שינוי ואינם נכתבים מחדש.
 *
 * כותרות לא מוכרות באנגלית יוחלפו בשם עברי כללי "עמודה N".
 * ניתן להוסיף מיפויים ל-HEADER_TRANSLATIONS לפני ההפעלה.
 */
const HEADER_TRANSLATIONS = {
  "id_number": "תעודת זהות",
  "id": "תעודת זהות",
  "user_id": "תעודת זהות",
  "user_identifier": "תעודת זהות",
  "phone": "מספר טלפון",
  "caller_phone": "מספר טלפון מחייג",
  "first_name": "שם פרטי",
  "last_name": "שם משפחה",
  "name": "שם לקוח",
  "user_name": "שם לקוח",
  "full_name": "שם מלא",
  "address": "כתובת מלאה",
  "community_code": "קוד קהילה",
  "code": "קוד",
  "community": "קהילה",
  "active": "פעיל",
  "is_active": "פעיל",
  "discount": "אחוז הנחה",
  "discount_percent": "אחוז הנחה",
  "category_id": "מזהה קטגוריה",
  "category_name": "שם קטגוריה",
  "category": "קטגוריה",
  "kashruts": "הכשרויות הזמינות",
  "kashrut": "כשרות",
  "sku": "מק״ט",
  "product_id": "מזהה מוצר",
  "product_name": "שם מוצר",
  "price": "מחיר ליחידה",
  "unit_price": "מחיר ליחידה",
  "category_coupon_price": "מחיר קופון קטגוריה",
  "notes": "הערות להשמעה",
  "in_stock": "במלאי",
  "stock": "מלאי",
  "transaction_id": "מספר עסקה",
  "order_id": "מספר הזמנה",
  "timestamp": "תאריך ושעה",
  "created_at": "תאריך יצירה",
  "completed_at": "תאריך סיום",
  "items_detail": "פירוט המוצרים",
  "order_details": "פירוט ההזמנה",
  "total_amount": "סכום לחיוב",
  "total": "סכום כולל",
  "quantity": "כמות יחידות",
  "qty": "כמות יחידות",
  "status": "סטטוס",
  "payment_status": "סטטוס תשלום",
  "payment_reference": "אסמכתת תשלום",
  "provider_transaction_id": "מספר עסקה אצל הספק",
  "call_id": "מזהה שיחה",
  "event_type": "סוג פעולה",
  "action": "סוג פעולה",
  "details": "פרטים נוספים",
  "metric": "מדד",
  "value": "ערך",
  "updated_at": "עודכן בתאריך",
  "password_hash": "סיסמה מוצפנת",
  "password": "סיסמה מוצפנת",
  "email": "דואר אלקטרוני",
  "notes_internal": "הערות פנימיות"
};

function normalizeHeaderKey_(value) {
  return String(value || "")
    .trim()
    .toLowerCase()
    .replace(/[\\s\\-]+/g, "_")
    .replace(/[^\u0590-\u05FFa-z0-9_״"]/g, "");
}

function formatAllTablesHebrew() {
  const ss = getSalesSpreadsheet_();
  const report = [];
  const sheets = ss.getSheets();

  sheets.forEach(sheet => {
    const lastColumn = sheet.getLastColumn();
    const lastRow = sheet.getLastRow();
    if (lastColumn < 1 || lastRow < 1) {
      report.push(sheet.getName() + ": דולג (גיליון ריק)");
      return;
    }

    // קריאת שורת הכותרת בלבד; אין קריאה/כתיבה של שורות הנתונים.
    const headerRange = sheet.getRange(1, 1, 1, lastColumn);
    const oldHeaders = headerRange.getDisplayValues()[0];
    const newHeaders = oldHeaders.map((header, index) => {
      const key = normalizeHeaderKey_(header);
      if (!key) return "עמודה " + (index + 1);
      if (HEADER_TRANSLATIONS[key]) return HEADER_TRANSLATIONS[key];
      // כותרת שכבר בעברית נשארת ללא שינוי.
      if (/[\u0590-\u05FF]/.test(String(header))) return String(header).trim();
      return "עמודה " + (index + 1);
    });

    // כתיבה לשורה 1 בלבד.
    headerRange.setValues([newHeaders]);

    sheet.setRightToLeft(true);
    sheet.setFrozenRows(1);
    sheet.setRowHeight(1, 36);

    const fullRange = sheet.getRange(1, 1, Math.max(lastRow, 1), lastColumn);
    fullRange
      .setFontFamily("Arial")
      .setFontSize(10)
      .setVerticalAlignment("middle")
      .setWrap(true);

    headerRange
      .setBackground("#1A73E8")
      .setFontColor("#FFFFFF")
      .setFontWeight("bold")
      .setFontSize(11)
      .setHorizontalAlignment("center")
      .setVerticalAlignment("middle");

    // רוחב עמודות לפי שם הכותרת, ללא שינוי בערכים.
    for (let col = 0; col < newHeaders.length; col++) {
      const h = newHeaders[col];
      let width = 150;
      if (/תעודת זהות|טלפון|מק״ט|קוד/.test(h)) width = 125;
      if (/שם|קהילה|קטגוריה|מוצר/.test(h)) width = 180;
      if (/כתובת|הערות|פירוט|פרטים/.test(h)) width = 260;
      if (/תאריך|שעה/.test(h)) width = 170;
      sheet.setColumnWidth(col + 1, width);
    }

    // עיצוב פסים מתחלפים וסינון; אינו משנה את תוכן התאים.
    sheet.getBandings().forEach(banding => banding.remove());
    if (lastRow >= 2) {
      fullRange.applyRowBanding(SpreadsheetApp.BandingTheme.LIGHT_GREY);
    }
    const existingFilter = sheet.getFilter();
    if (existingFilter) existingFilter.remove();
    if (lastRow >= 2) fullRange.createFilter();

    report.push(sheet.getName() + ": עוצב, " + lastColumn + " עמודות");
  });

  SpreadsheetApp.flush();
  return report.join("\\n");
}

/**
 * שומר hash מוצפן לסיסמת משתמש. מתקבל רק מהשרת לאחר בדיקת המפתח.
 * אם אין עמודת סיסמה מוצפנת, נוסיף אותה בקצה הגיליון ולא נזיז נתונים קיימים.
 */
function doPost(e) {
  let payload;
  try {
    payload = JSON.parse((e && e.postData && e.postData.contents) || "{}");
  } catch (error) {
    return jsonOutput_({ok: false, error: "invalid_json"});
  }

  const expectedKey = PropertiesService.getScriptProperties().getProperty("SALES_CONTROL_KEY") || "";
  if (!expectedKey || String(payload.key || "") !== expectedKey) {
    return jsonOutput_({ok: false, error: "unauthorized"});
  }

  if (payload.action !== "set_password") {
    return jsonOutput_({ok: false, error: "unsupported_action"});
  }

  const idNumber = String(payload.id_number || "").trim();
  const passwordHash = String(payload.password_hash || "").trim();
  if (!/^\\d{8,9}$/.test(idNumber) || !passwordHash.startsWith("pbkdf2_sha256$")) {
    return jsonOutput_({ok: false, error: "invalid_parameters"});
  }

  const ss = getSalesSpreadsheet_();
  const userSheet = findUsersSheet_(ss);
  if (!userSheet) return jsonOutput_({ok: false, error: "users_sheet_not_found"});

  const lastColumn = Math.max(userSheet.getLastColumn(), 1);
  const headers = userSheet.getRange(1, 1, 1, lastColumn).getDisplayValues()[0];
  let idCol = findHeaderColumn_(headers, ["תעודת זהות", "id_number", "user_id", "id"]);
  if (idCol < 0) return jsonOutput_({ok: false, error: "id_column_not_found"});

  let passwordCol = findHeaderColumn_(headers, ["סיסמה מוצפנת", "password_hash", "password"]);
  if (passwordCol < 0) {
    passwordCol = lastColumn + 1;
    userSheet.getRange(1, passwordCol).setValue("סיסמה מוצפנת");
  }

  const lastRow = userSheet.getLastRow();
  if (lastRow < 2) return jsonOutput_({ok: false, error: "user_not_found"});

  const ids = userSheet.getRange(2, idCol + 1, lastRow - 1, 1).getDisplayValues();
  let targetRow = -1;
  for (let i = 0; i < ids.length; i++) {
    if (String(ids[i][0]).trim() === idNumber) {
      targetRow = i + 2;
      break;
    }
  }
  if (targetRow < 0) return jsonOutput_({ok: false, error: "user_not_found"});

  userSheet.getRange(targetRow, passwordCol + 1).setNumberFormat("@").setValue(passwordHash);
  return jsonOutput_({ok: true, id_number: idNumber});
}

function findUsersSheet_(ss) {
  return ss.getSheetByName("משתמשים") || ss.getSheetByName("Users") || ss.getSheetByName("users");
}

function findHeaderColumn_(headers, candidates) {
  const normalized = headers.map(normalizeHeaderKey_);
  for (const candidate of candidates) {
    const index = normalized.indexOf(normalizeHeaderKey_(candidate));
    if (index >= 0) return index;
  }
  return -1;
}

function readPasswordHashes_(ss) {
  const sheet = findUsersSheet_(ss);
  if (!sheet || sheet.getLastRow() < 2 || sheet.getLastColumn() < 1) return {};
  const values = sheet.getDataRange().getDisplayValues();
  const idCol = findHeaderColumn_(values[0], ["תעודת זהות", "id_number", "user_id", "id"]);
  const passwordCol = findHeaderColumn_(values[0], ["סיסמה מוצפנת", "password_hash", "password"]);
  if (idCol < 0 || passwordCol < 0) return {};
  const hashes = {};
  for (let row = 1; row < values.length; row++) {
    const id = String(values[row][idCol] || "").trim();
    const hash = String(values[row][passwordCol] || "").trim();
    if (id && hash) hashes[id] = hash;
  }
  return hashes;
}
