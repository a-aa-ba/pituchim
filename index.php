<?php
// הגדרת קידוד מתאים לתשובת טקסט פשוט עבור ימות המשיח [10]
header('Content-Type: text/plain; charset=utf-8');

// הגדרת נתיבי הקבצים
define('ACCOUNTS_FILE', 'data/accounts.txt');
define('PREFERENCES_FILE', 'data/user_preferences.txt');
define('LOG_FILE', 'data/log.txt');

// מפתח אבטחה לאיתחול ידני דרך הדפדפן (שנה אותו למשהו סודי משלך)
define('INIT_KEY', 'my_secret_setup_key_123');

// -------------------------------------------------------------------------
// הזנת החשבונות וההגדרות ישירות בקוד המקור
// -------------------------------------------------------------------------
$initialAccounts = [
    // שם_משתמש => [סיסמה, יתרה ראשונית, שם תצוגה, האם צינתוק מופעל, טלפון לצינתוק, סכום מינימום לצינתוק, האם נדרש אימות]
    '1111' => ['password' => '1234', 'balance' => 50.0,   'name' => 'משה כהן',     'tz_enabled' => 1, 'tz_phone' => '0554000000', 'tz_min' => 10, 'verify' => 0],
    '2222' => ['password' => '5678', 'balance' => 150.0,  'name' => 'אברהם לוי',   'tz_enabled' => 1, 'tz_phone' => '0501234567', 'tz_min' => 5,  'verify' => 1],
    '2001' => ['password' => '9999', 'balance' => 1000.0, 'name' => 'מכונות הכביסה', 'tz_enabled' => 0, 'tz_phone' => '',           'tz_min' => 0,  'verify' => 0],
    '2002' => ['password' => '8888', 'balance' => 500.0,  'name' => 'קופת ת"ת',     'tz_enabled' => 0, 'tz_phone' => '',           'tz_min' => 0,  'verify' => 0],
];

// -------------------------------------------------------------------------
// פונקציית יצירת/שחזור קבצי המערכת מתוך הקוד
// -------------------------------------------------------------------------
function initializeSystemFiles($initialAccounts, $force = false) {
    if (!is_dir('data')) {
        mkdir('data', 0755, true);
    }
    
    // אם הקבצים כבר קיימים ואנחנו לא מאלצים כתיבה מחדש, לא נעשה דבר כדי לא לדרוס יתרות קיימות
    if (!$force && file_exists(ACCOUNTS_FILE) && file_exists(PREFERENCES_FILE)) {
        return;
    }
    
    $accountsLines = [];
    $prefLines = [];
    
    foreach ($initialAccounts as $user => $info) {
        // בניית שורה לקובץ היתרות בפורמט: user:password-balance
        $accountsLines[] = "{$user}:{$info['password']}-{$info['balance']}";
        
        // בניית שורה לקובץ ההגדרות
        $tzEnabled = $info['tz_enabled'] ? '1' : '0';
        $verify = $info['verify'] ? '1' : '0';
        $prefLines[] = "{$user}:{$info['name']}:{$tzEnabled}:{$info['tz_phone']}:{$info['tz_min']}:{$verify}";
    }
    
    // כתיבה מאובטחת לקבצים
    file_put_contents(ACCOUNTS_FILE, implode("\n", $accountsLines), LOCK_EX);
    file_put_contents(PREFERENCES_FILE, implode("\n", $prefLines), LOCK_EX);
    
    logAction("System database initialized/re-created from PHP source code.");
}

// -------------------------------------------------------------------------
// בדיקה האם המשתמש מבקש לאתחל ידנית דרך הדפדפן
// -------------------------------------------------------------------------
if (isset($_GET['init']) && $_GET['init'] === INIT_KEY) {
    initializeSystemFiles($initialAccounts, true);
    echo "המערכת אותחלה בהצלחה! הקבצים נוצרו מחדש לפי הנתונים שהזנת בקוד.";
    exit;
}

// איתחול אוטומטי בהרצה ראשונה (רק אם הקבצים לא קיימים כלל בשרת)
if (!file_exists(ACCOUNTS_FILE) || !file_exists(PREFERENCES_FILE)) {
    initializeSystemFiles($initialAccounts, false);
}

// המשך קוד ה-Session והלוגיקה הרגילה של ה-IVR... [2, 10]
