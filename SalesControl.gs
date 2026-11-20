/**
 * ניהול פתיחה וסגירה של המכירות
 * את מצב המכירות ואת רשימת המספרים המוחרגים מגדירים ישירות בקוד הזה.
 *
 * שינוי מצב המכירות:
 *   SALES_OPEN = true  - המכירות פתוחות לכולם.
 *   SALES_OPEN = false - המכירות סגורות, למעט המספרים שברשימת ההחרגות.
 *
 * הוספת מספר מורשה:
 *   מוסיפים מספר כמחרוזת לרשימה SALES_ALLOWED_PHONES_WHEN_CLOSED.
 *   יש לכתוב את המספר עם אפס מוביל, לדוגמה "0501234567".
 */

// ===================================================================
// הגדרות מנהל – משנים רק את הערכים כאן
// ===================================================================

// true = פתיחת המכירות; false = סגירת המכירות.
const SALES_OPEN = false;

// מספרים שמורשים להיכנס להזמנות גם כשהמכירות סגורות.
// הרשימה משפיעה על כניסה להזמנות בלבד, ולא על שלוחות אחרות.
const SALES_ALLOWED_PHONES_WHEN_CLOSED = [
  // "0501234567",
  // "0521234567",
];

// ===================================================================
// מנגנון חיבור מאובטח לשרת
// ===================================================================

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

  const exceptions = SALES_ALLOWED_PHONES_WHEN_CLOSED
    .map(normalizeSalesPhone_)
    .filter(Boolean);

  return jsonOutput_({
    sales_open: SALES_OPEN === true,
    exceptions: [...new Set(exceptions)]
  });
}

/**
 * אחידות מספרי טלפון:
 * מסיר סימנים ורווחים, וממיר קידומת 972 לפורמט ישראלי שמתחיל ב-0.
 */
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
