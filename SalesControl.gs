/**
 * ניהול פתיחה וסגירה של המכירות – Google Apps Script
 * יש לקשר את הפרויקט לגיליון Google Sheets של המערכת.
 *
 * אבטחה:
 * 1. הגדירו ב'הגדרות פרויקט' > 'מאפייני סקריפט' מפתח בשם SALES_CONTROL_KEY.
 * 2. פרסמו כיישום אינטרנט: הפעלה בתור בעלים, גישה לכל מי שמחזיק בקישור.
 * 3. המפתח נשלח מהשרת בלבד בפרמטר key. אין לשתף אותו עם משתמשי הקצה.
 */

const SALES_SETTINGS_SHEET = 'הגדרות מכירות';
const SALES_EXCEPTIONS_SHEET = 'חריגי מכירות';

function setupSalesControl() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss) throw new Error('יש לפתוח את Apps Script מתוך גיליון Google Sheets.');

  let settings = ss.getSheetByName(SALES_SETTINGS_SHEET);
  if (!settings) settings = ss.insertSheet(SALES_SETTINGS_SHEET);
  settings.clear();
  settings.getRange(1, 1, 2, 2).setValues([
    ['הגדרה', 'ערך'],
    ['המכירות פתוחות', 'FALSE']
  ]);
  styleSalesSheet_(settings, 2);
  settings.setColumnWidth(1, 240);
  settings.setColumnWidth(2, 180);
  settings.getRange('B2').setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(['TRUE', 'FALSE'], true)
      .setAllowInvalid(false)
      .build()
  );
  settings.getRange('B2').setNote('TRUE = המכירות פתוחות. FALSE = המכירות סגורות.');

  let exceptions = ss.getSheetByName(SALES_EXCEPTIONS_SHEET);
  if (!exceptions) exceptions = ss.insertSheet(SALES_EXCEPTIONS_SHEET);
  exceptions.clear();
  exceptions.getRange(1, 1, 2, 3).setValues([
    ['מספר טלפון', 'פעיל', 'הערות'],
    ['', 'TRUE', '']
  ]);
  styleSalesSheet_(exceptions, 3);
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
  exceptions.getRange('A1:C1').setNote('החרגה מאפשרת למספר זה להיכנס להזמנות גם כשהמכירות סגורות. היא אינה פותחת שלוחות אחרות.');
  exceptions.setFrozenRows(1);
  if (!exceptions.getFilter()) {
    exceptions.getRange(1, 1, Math.max(2, exceptions.getMaxRows()), 3).createFilter();
  }
  SpreadsheetApp.flush();
  return 'גיליונות ניהול המכירות נוצרו ועוצבו בהצלחה.';
}

function styleSalesSheet_(sheet, columns) {
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
  sheet.getDataRange()
    .setVerticalAlignment('middle')
    .setFontFamily('Arial')
    .setWrap(true);
  const bandedRange = sheet.getRange(1, 1, Math.max(2, sheet.getMaxRows()), columns);
  bandedRange.applyRowBanding(SpreadsheetApp.BandingTheme.LIGHT_GREY);
}

function doGet(e) {
  const expectedKey = PropertiesService.getScriptProperties().getProperty('SALES_CONTROL_KEY');
  const suppliedKey = e && e.parameter ? String(e.parameter.key || '') : '';
  if (!expectedKey || suppliedKey !== expectedKey) {
    return jsonOutput_({ error: 'unauthorized' });
  }

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const settings = ss.getSheetByName(SALES_SETTINGS_SHEET);
  const exceptionsSheet = ss.getSheetByName(SALES_EXCEPTIONS_SHEET);
  if (!settings || !exceptionsSheet) {
    return jsonOutput_({ error: 'sheets_not_initialized' });
  }

  const salesOpenValue = String(settings.getRange('B2').getDisplayValue()).trim().toUpperCase();
  const rows = exceptionsSheet.getDataRange().getDisplayValues();
  const exceptions = [];
  for (let i = 1; i < rows.length; i++) {
    const phone = normalizeSalesPhone_(rows[i][0]);
    const active = String(rows[i][1] || '').trim().toUpperCase();
    if (phone && ['TRUE', '1', 'YES', 'כן'].includes(active)) exceptions.push(phone);
  }

  return jsonOutput_({
    sales_open: ['TRUE', '1', 'YES', 'כן'].includes(salesOpenValue),
    exceptions: [...new Set(exceptions)]
  });
}

function normalizeSalesPhone_(value) {
  let digits = String(value || '').replace(/\\D/g, '');
  if (digits.startsWith('972') && digits.length >= 11) digits = '0' + digits.slice(3);
  return digits;
}

function jsonOutput_(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
