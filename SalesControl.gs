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
    exceptions: [...new Set(exceptions)]
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
