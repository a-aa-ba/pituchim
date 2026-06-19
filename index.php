<?php
/**
 * Yemot Hamashiah IVR PHP Render Server - High Performance Version
 * Current context year: 2026
 */

header('Content-Type: text/plain; charset=utf-8');

// הגדרת קישור ה-Apps Script שלך
define('APPS_SCRIPT_URL', 'https://script.google.com/macros/s/YOUR_APPS_SCRIPT_DEPLOYMENT_ID/exec');

// הגדרת טוקן פיתוח של ימות המשיח לצורך ביצוע צינתוקים / אימותים
define('YEMOT_API_TOKEN', 'YOUR_YEMOT_DEVELOPER_API_TOKEN');

// שימוש בתיקיית /tmp הזמנית של שרת הרנדר
define('SESSIONS_DIR', '/tmp/sessions');
define('ACCOUNTS_CACHE_FILE', '/tmp/accounts_cache.json');
define('PREFS_CACHE_DIR', '/tmp/prefs');

// יצירת תיקיות בסיס אם אינן קיימות
foreach ([SESSIONS_DIR, PREFS_CACHE_DIR] as $dir) {
    if (!is_dir($dir)) {
        mkdir($dir, 0755, true);
    }
}

// קבלת פרמטרים מימות המשיח
$callId    = $_REQUEST['ApiCallId'] ?? null;
$phone     = $_REQUEST['ApiPhone'] ?? '';
$extension = $_REQUEST['ApiExtension'] ?? '/';
$userInput = $_REQUEST['ApiValName'] ?? '';

if (!$callId) {
    exit("id_list_message=t-שגיאה במערכת, מזהה שיחה חסר.");
}

// ניהול סשן השיחה
$sessionFile = SESSIONS_DIR . '/' . $callId . '.json';
$session = [];
if (file_exists($sessionFile)) {
    $session = json_decode(file_get_contents($sessionFile), true);
}

if (isset($session['last_extension']) && $session['last_extension'] !== $extension) {
    $session['state'] = 'idle';
}
$session['last_extension'] = $extension;

// אבטחה קשיחה: וידוא התחברות
$isAuthenticated = !empty($session['user']) && ($session['logged_in'] ?? false);
$isAuthFlow = in_array($session['state'] ?? '', ['wait_username', 'wait_password']);

if (!$isAuthenticated && !$isAuthFlow) {
    $session['state'] = 'wait_username';
    saveSession($sessionFile, $session);
    echo formatRead("אנא הקש את שם המשתמש שלך, ולאחריו סולמית", "username", 4, 4);
    exit;
}

// --- תהליך התחברות מבוסס מטמון מקומי מהיר (מיידי) ---
if (!$isAuthenticated && $isAuthFlow) {
    if ($session['state'] === 'wait_username') {
        $enteredUser = trim($userInput);
        $userData = getUserFromCache($enteredUser);
        
        if (!$userData) {
            echo "id_list_message=t-שם משתמש זה אינו מופיע ברשימת המשתמשים הרשומים למערכת. לרישום למערכת יש לפנות לחדר התת בישיבה&api_end_goto=hangup";
            unlink($sessionFile);
            exit;
        }
        
        $session['temp_user'] = $enteredUser;
        $session['state'] = 'wait_password';
        saveSession($sessionFile, $session);
        echo formatRead("אנא הקש את הסיסמה שלך, ולאחריה סולמית", "password", 10, 4);
        exit;
    } 
    
    if ($session['state'] === 'wait_password') {
        $enteredPassword = trim($userInput);
        $tempUser = $session['temp_user'];
        $userData = getUserFromCache($tempUser);
        
        if ($userData && $userData['password'] === $enteredPassword) {
            $session['user'] = $tempUser;
            $session['logged_in'] = true;
            $session['state'] = 'idle';
            saveSession($sessionFile, $session);
            
            // שליחת לוג אסינכרונית ברקע (המשתמש ממשיך מיידית בטלפון)
            respondAndRunBackground("id_list_message=t-שלום " . $tempUser . " נכנסת בהצלחה.&", function() use ($tempUser) {
                callDb(['action' => 'log_auth', 'user' => $tempUser, 'type' => 'התחברות', 'detail' => 'התחברות מאובטחת בהצלחה']);
            });
            exit;
        } else {
            $session['state'] = 'wait_username';
            saveSession($sessionFile, $session);
            echo "id_list_message=t-הסיסמה שגויה, נסו שנית.&";
            echo formatRead("אנא הקש שוב את שם המשתמש שלך, ולאחריו סולמית", "username", 4, 4);
            exit;
        }
    }
}

$currentUser = $session['user'];
$cleanExt = rtrim($extension, '/');

// שלוחה 4 - פיתוח
if (strpos($cleanExt, '/4') === 0) {
    echo "id_list_message=t-שלוחה זו עדיין בפיתוח.&api_end_goto=/";
    exit;
}

// שלוחה 0 - אזור אישי
if (strpos($cleanExt, '/0') === 0) {
    handlePersonalArea($cleanExt, $currentUser, $session, $sessionFile, $userInput, $phone);
    exit;
}

// שלוחה 1 - ביצוע תשלומים
if (strpos($cleanExt, '/1/') === 0) {
    $parts = explode('/', $cleanExt);
    $businessAccount = end($parts);
    handlePaymentFlow($currentUser, $businessAccount, $session, $sessionFile, $userInput, $phone);
    exit;
}

// שלוחה 2 - העברה חופשית
if ($cleanExt === '/2') {
    handleTransferFlow($currentUser, $session, $sessionFile, $userInput, $phone);
    exit;
}

// שלוחה 3 - היסטוריית פעולות
if ($cleanExt === '/3') {
    handleHistoryFlow($currentUser, $session, $sessionFile, $userInput);
    exit;
}

// שלוחה * - יתרת חשבון
if (strpos($cleanExt, '/star') === 0 || $cleanExt === '/*') {
    $userData = getUserFromCache($currentUser);
    echo "id_list_message=t-היתרה בחשבונך עומדת על סך של " . $userData['balance'] . " שקלים.&api_end_goto=/";
    exit;
}

// תפריט ברירת מחדל
echo "id_list_message=t-ברוכים הבאים למערכת.&";
echo formatRead("לתשלום הקישו 1, להעברה הקישו 2, להיסטוריה הקישו 3, לאזור האישי הקישו 0", "menu_select", 1, 1);
exit;

// ==========================================
// --- פונקציות העסקאות והשלוחות (מיידיות) ---
// ==========================================

function handlePaymentFlow($user, $business, &$session, $sessionFile, $userInput, $phone) {
    $businessNames = ['101' => 'תת', '102' => 'מכונות כביסה', '103' => 'אוצר הספרים'];
    $businessName = $businessNames[$business] ?? "עסק מספר " . $business;
    $state = $session['sub_state'] ?? 'start';
    
    if ($state === 'start') {
        $session['sub_state'] = 'wait_amount';
        saveSession($sessionFile, $session);
        echo formatRead("אנא הקש את הסכום לחיוב, ולאחריו סולמית", "amount", 5, 1);
        return;
    }
    
    if ($state === 'wait_amount') {
        $amount = (float)$userInput;
        if ($amount <= 0) {
            echo "id_list_message=t-סכום לא תקין.&";
            $session['sub_state'] = 'start';
            saveSession($sessionFile, $session);
            return;
        }
        
        $userData = getUserFromCache($user);
        if ($userData['balance'] < $amount) {
            echo "id_list_message=t-היתרה בחשבונך עומדת על " . $userData['balance'] . " שקלים בלבד. לא ניתן לבצע העברה בסכום זה.&";
            $session['sub_state'] = 'start';
            saveSession($sessionFile, $session);
            return;
        }
        
        $session['temp_amount'] = $amount;
        $session['sub_state'] = 'wait_confirmation';
        saveSession($sessionFile, $session);
        echo formatRead("הנך מבקש להעביר סכום של " . $amount . " שקלים ל " . $businessName . " . לאישור הקש 1, לביטול הקש 2", "confirm", 1, 1);
        return;
    }
    
    if ($state === 'wait_confirmation') {
        if ($userInput == '1') {
            $amount = $session['temp_amount'];
            $prefs = getUserPreferences($user);
            
            // עדכון היתרה באופן מקומי במטמון מיידית
            updateLocalBalanceInCache($user, -$amount);
            updateLocalBalanceInCache($business, $amount);
            
            // שליחה לגוגל שיטס ברקע + מענה טלפוני מיידי
            respondAndRunBackground("id_list_message=t-העסקה בוצעה בהצלחה.&api_end_goto=/", function() use ($user, $business, $amount, $businessName, $prefs, $phone) {
                if ($prefs['verification'] && $amount >= $prefs['verification_threshold']) {
                    callDb(['action' => 'log_auth', 'user' => $user, 'type' => 'אימות תשלום', 'detail' => 'נשלחה שיחת אימות על סך ' . $amount]);
                    sendYemotCall($phone); 
                }
                
                $res = callDb(['action' => 'transfer', 'from' => $user, 'to' => $business, 'amount' => $amount]);
                if (trim($res) === 'success') {
                    callDb(['action' => 'log_transaction', 'user' => $user, 'type' => 'תשלום', 'target' => $businessName, 'amount' => -$amount]);
                    callDb(['action' => 'log_transaction', 'user' => $business, 'type' => 'קבלת תשלום', 'target' => $user, 'amount' => $amount]);
                    
                    if ($prefs['tzintuk'] && $amount >= $prefs['tzintuk_threshold'] && !empty($prefs['tzintuk_phone'])) {
                        sendYemotTzintuk($prefs['tzintuk_phone']);
                    }
                }
            });
        } else {
            echo "id_list_message=t-העסקה בבוטלה.&api_end_goto=/";
        }
        unset($session['sub_state'], $session['temp_amount']);
        saveSession($sessionFile, $session);
    }
}

function handleTransferFlow($user, &$session, $sessionFile, $userInput, $phone) {
    $state = $session['sub_state'] ?? 'start';
    
    if ($state === 'start') {
        $session['sub_state'] = 'wait_target';
        saveSession($sessionFile, $session);
        echo formatRead("הקש את שם המשתמש אליו הינך רוצה להעביר", "target_user", 4, 4);
        return;
    }
    
    if ($state === 'wait_target') {
        $targetUser = trim($userInput);
        $targetData = getUserFromCache($targetUser);
        if (!$targetData) {
            echo "id_list_message=t-משתמש היעד לא נמצא במערכת.&";
            $session['sub_state'] = 'start';
            saveSession($sessionFile, $session);
            return;
        }
        
        $session['temp_target'] = $targetUser;
        $session['sub_state'] = 'wait_amount';
        saveSession($sessionFile, $session);
        echo formatRead("אנא הקש את הסכום להעברה, ולאחריו סולמית", "amount", 5, 1);
        return;
    }
    
    if ($state === 'wait_amount') {
        $amount = (float)$userInput;
        if ($amount <= 0) {
            echo "id_list_message=t-סכום לא תקין.&";
            $session['sub_state'] = 'start';
            saveSession($sessionFile, $session);
            return;
        }
        
        $userData = getUserFromCache($user);
        if ($userData['balance'] < $amount) {
            echo "id_list_message=t-יתרתך הנוכחית היא " . $userData['balance'] . " שקלים. הפעולה נדחתה.&";
            $session['sub_state'] = 'start';
            saveSession($sessionFile, $session);
            return;
        }
        
        $session['temp_amount'] = $amount;
        $session['sub_state'] = 'wait_confirmation';
        saveSession($sessionFile, $session);
        echo formatRead("הנך מבקש להעביר " . $amount . " שקלים למשתמש " . $session['temp_target'] . " . לאישור הקש 1, לביטול הקש 2", "confirm", 1, 1);
        return;
    }
    
    if ($state === 'wait_confirmation') {
        if ($userInput == '1') {
            $amount = $session['temp_amount'];
            $target = $session['temp_target'];
            $prefs = getUserPreferences($user);
            
            // עדכון המטמון המקומי מיידית למאזין
            updateLocalBalanceInCache($user, -$amount);
            updateLocalBalanceInCache($target, $amount);
            
            respondAndRunBackground("id_list_message=t-ההעברה בוצעה בהצלחה.&api_end_goto=/", function() use ($user, $target, $amount, $prefs, $phone) {
                if ($prefs['verification'] && $amount >= $prefs['verification_threshold']) {
                    sendYemotVerificationCall($phone);
                }
                
                $res = callDb(['action' => 'transfer', 'from' => $user, 'to' => $target, 'amount' => $amount]);
                if (trim($res) === 'success') {
                    callDb(['action' => 'log_transaction', 'user' => $user, 'type' => 'העברה', 'target' => $target, 'amount' => -$amount]);
                    callDb(['action' => 'log_transaction', 'user' => $target, 'type' => 'קבלת העברה', 'target' => $user, 'amount' => $amount]);
                    
                    if ($prefs['tzintuk'] && $amount >= $prefs['tzintuk_threshold'] && !empty($prefs['tzintuk_phone'])) {
                        sendYemotTzintuk($prefs['tzintuk_phone']);
                    }
                }
            });
        } else {
            echo "id_list_message=t-הפעולה בוטלה.&api_end_goto=/";
        }
        unset($session['sub_state'], $session['temp_target'], $session['temp_amount']);
        saveSession($sessionFile, $session);
    }
}

// שאר השלוחות...
function handleHistoryFlow($user, &$session, $sessionFile, $userInput) {
    // השמעת היסטוריה דורשת קריאה מגוגל שיטס. היא מתבצעת פעם אחת בכניסה לשלוחה
    $response = callDb(['action' => 'get_transactions', 'user' => $user]);
    $transactions = json_decode($response, true);
    
    if (empty($transactions)) {
        echo "id_list_message=t-לא נמצאו פעולות קודמות בחשבונך.&api_end_goto=/";
        return;
    }
    
    $index = $session['history_index'] ?? 0;
    if ($userInput == '8') { $index++; } 
    elseif ($userInput == '2') { $index--; }
    
    if ($index < 0) {
        $index = 0;
        echo "id_list_message=t-זוהי הפעולה האחרונה.&";
    }
    if ($index >= count($transactions)) {
        echo "id_list_message=t-סיימתם להאזין לפעולות.&api_end_goto=/";
        unset($session['history_index']);
        saveSession($sessionFile, $session);
        return;
    }
    
    $session['history_index'] = $index;
    saveSession($sessionFile, $session);
    
    $parts = explode('|', $transactions[$index]);
    if (count($parts) < 5) {
        $index++;
        $session['history_index'] = $index;
        saveSession($sessionFile, $session);
        return;
    }
    
    list($date, $time, $type, $target, $amount) = $parts;
    $dir = ((float)$amount < 0) ? "ל" : "מ";
    $absAmount = abs((float)$amount);
    
    $msg = "t-בתאריך " . $date . " בשעה " . $time . " בוצעה פעולה של " . $type . " " . $dir . " חשבונך עם " . $target . " על סך " . $absAmount . " שקלים.";
    echo "read=" . $msg . "=history_nav,,1,1,2,Digits,no,no,,,3,Ok,None,yes,no";
}

function handlePersonalArea($cleanExt, $user, &$session, $sessionFile, $userInput, $phone) {
    if ($cleanExt === '/0') {
        echo "id_list_message=t-אזור אישי.&";
        echo formatRead("לשינוי סיסמה הקישו 1, להגדרות צינתוקים הקישו 2, להגדרות שיחות אימות הקישו 3", "sub_menu", 1, 1);
        return;
    }
    
    // שינוי סיסמה
    if ($cleanExt === '/0/1') {
        $state = $session['sub_state'] ?? 'start';
        if ($state === 'start') {
            $session['sub_state'] = 'wait_curr_pass';
            saveSession($sessionFile, $session);
            echo formatRead("אנא הקש את הסיסמה העכשווית שלך, ולאחריה סולמית", "curr_pass", 10, 4);
            return;
        }
        if ($state === 'wait_curr_pass') {
            $userData = getUserFromCache($user);
            if ($userData['password'] === trim($userInput)) {
                $session['sub_state'] = 'wait_new_pass1';
                saveSession($sessionFile, $session);
                echo formatRead("אנא הקש את הסיסמה החדשה שלך, ולאחריה סולמית", "new_pass1", 10, 4);
            } else {
                echo "id_list_message=t-סיסמה שגויה. הפעולה בוטלה.&api_end_goto=/";
                unset($session['sub_state']);
                saveSession($sessionFile, $session);
            }
            return;
        }
        if ($state === 'wait_new_pass1') {
            $session['temp_new_pass'] = trim($userInput);
            $session['sub_state'] = 'wait_new_pass2';
            saveSession($sessionFile, $session);
            echo formatRead("אנא הקש שוב את הסיסמה החדשה לאימות", "new_pass2", 10, 4);
            return;
        }
        if ($state === 'wait_new_pass2') {
            if ($session['temp_new_pass'] === trim($userInput)) {
                $newPass = $session['temp_new_pass'];
                updateLocalPasswordInCache($user, $newPass);
                
                respondAndRunBackground("id_list_message=t-הסיסמה שונתה בהצלחה.&api_end_goto=/", function() use ($user, $newPass) {
                    callDb(['action' => 'update_password', 'username' => $user, 'password' => $newPass]);
                    callDb(['action' => 'log_auth', 'user' => $user, 'type' => 'שינוי סיסמה', 'detail' => 'סיסמה שונתה בהצלחה']);
                });
            } else {
                echo "id_list_message=t-הסיסמאות אינן תואמות. הפעולה בוטלה.&api_end_goto=/";
            }
            unset($session['sub_state'], $session['temp_new_pass']);
            saveSession($sessionFile, $session);
        }
        return;
    }
    
    // הגדרות צינתוקים
    if (strpos($cleanExt, '/0/2') === 0) {
        $prefs = getUserPreferences($user);
        if ($cleanExt === '/0/2') {
            echo formatRead("להפעלת או ביטול צינתוקים הקישו 1, להגדרת סכום הצינתוק הקישו 2, להגדרת מספר הטלפון הקישו 3", "tz_choice", 1, 1);
            return;
        }
        if ($cleanExt === '/0/2/1') {
            $prefs['tzintuk'] = !$prefs['tzintuk'];
            saveUserPreferences($user, $prefs);
            $statusStr = $prefs['tzintuk'] ? "מופעל" : "מבוטל";
            echo "id_list_message=t-שירות הצינתוקים עודכן ל " . $statusStr . " .&api_end_goto=/0/2";
            return;
        }
        if ($cleanExt === '/0/2/2') {
            $state = $session['sub_state'] ?? 'start';
            if ($state === 'start') {
                $session['sub_state'] = 'wait_amount_choice';
                saveSession($sessionFile, $session);
                echo formatRead("הסכום המוגדר כעת הוא " . $prefs['tzintuk_threshold'] . " שקלים. לשינוי הקישו 1, ליציאה הקישו 2", "choice", 1, 1);
            } elseif ($state === 'wait_amount_choice') {
                if ($userInput == '1') {
                    $session['sub_state'] = 'wait_new_amount';
                    saveSession($sessionFile, $session);
                    echo formatRead("אנא הקש את הסכום שממנו תתחיל לקבל צינתוק, ולאחריו סולמית", "new_val", 5, 1);
                } else {
                    echo "id_list_message=t-הפעולה בוטלה.&api_end_goto=/0/2";
                    unset($session['sub_state']);
                    saveSession($sessionFile, $session);
                }
            } elseif ($state === 'wait_new_amount') {
                $prefs['tzintuk_threshold'] = (float)$userInput;
                saveUserPreferences($user, $prefs);
                echo "id_list_message=t-ההגדרה עודכנה בהצלחה.&api_end_goto=/0/2";
                unset($session['sub_state']);
                saveSession($sessionFile, $session);
            }
            return;
        }
        if ($cleanExt === '/0/2/3') {
            $state = $session['sub_state'] ?? 'start';
            if ($state === 'start') {
                $currentPhone = !empty($prefs['tzintuk_phone']) ? $prefs['tzintuk_phone'] : 'לא מוגדר מספר';
                $session['sub_state'] = 'wait_phone_choice';
                saveSession($sessionFile, $session);
                echo formatRead("המספר המוגדר כעת הוא " . $currentPhone . " . לשינוי הקש 1, ליציאה הקש 2", "choice", 1, 1);
            } elseif ($state === 'wait_phone_choice') {
                if ($userInput == '1') {
                    $session['sub_state'] = 'wait_new_phone';
                    saveSession($sessionFile, $session);
                    echo formatRead("הקש את המספר אליו יישלח הצינתוק, ולאחריו סולמית", "new_phone", 9, 8);
                } else {
                    echo "id_list_message=t-הפעולה בוטלה.&api_end_goto=/0/2";
                    unset($session['sub_state']);
                    saveSession($sessionFile, $session);
                }
            } elseif ($state === 'wait_new_phone') {
                $prefs['tzintuk_phone'] = trim($userInput);
                saveUserPreferences($user, $prefs);
                echo "id_list_message=t-המספר הוגדר בהצלחה.&api_end_goto=/0/2";
                unset($session['sub_state']);
                saveSession($sessionFile, $session);
            }
            return;
        }
    }
}

// ==========================================
// --- מנגנוני מטמון ושיגור אסינכרוני (מאיצי מהירות) ---
// ==========================================

// סגירה מיידית של החיבור עם ימות המשיח והמשך ריצה של הקוד ברקע
function respondAndRunBackground($responseText, $backgroundFunction) {
    // מנקים באפרים קודמים
    while (ob_get_level() > 0) {
        ob_end_clean();
    }
    
    ob_start();
    echo $responseText;
    $size = ob_get_length();
    
    header("Content-Type: text/plain; charset=utf-8");
    header("Connection: close");
    header("Content-Length: " . $size);
    
    ob_end_flush();
    flush();
    
    // מנתק את החיבור עם שרת ימות המשיח (המאזין ממשיך לשמוע את הודעת ההצלחה ללא שום דיליי)
    if (function_exists('fastcgi_finish_request')) {
        fastcgi_finish_request();
    }
    
    // השרת מבצע כעת את הפעולות האיטיות מול גוגל שיטס ברקע
    $backgroundFunction();
}

// משיכת כל החשבונות פעם אחת ב-5 דקות (מבטל את הדיליי לחלוטין)
function getUserFromCache($username) {
    $cacheLifetime = 300; // 5 דקות
    $accounts = [];
    
    if (file_exists(ACCOUNTS_CACHE_FILE) && (time() - filemtime(ACCOUNTS_CACHE_FILE) < $cacheLifetime)) {
        $accounts = json_decode(file_get_contents(ACCOUNTS_CACHE_FILE), true);
    } else {
        // משיכה מרוכזת אחת של כל הטבלה
        $res = callDb(['action' => 'get_accounts']);
        $fetched = json_decode($res, true);
        if (is_array($fetched)) {
            $accounts = $fetched;
            file_put_contents(ACCOUNTS_CACHE_FILE, json_encode($accounts), LOCK_EX);
        } elseif (file_exists(ACCOUNTS_CACHE_FILE)) {
            // גיבוי למקרה של כשל רשת זמני מול גוגל
            $accounts = json_decode(file_get_contents(ACCOUNTS_CACHE_FILE), true);
        }
    }
    
    return $accounts[$username] ?? null;
}

function updateLocalBalanceInCache($username, $delta) {
    if (!file_exists(ACCOUNTS_CACHE_FILE)) return;
    $accounts = json_decode(file_get_contents(ACCOUNTS_CACHE_FILE), true);
    if (isset($accounts[$username])) {
        $accounts[$username]['balance'] = (float)$accounts[$username]['balance'] + $delta;
        file_put_contents(ACCOUNTS_CACHE_FILE, json_encode($accounts), LOCK_EX);
    }
}

function updateLocalPasswordInCache($username, $newPass) {
    if (!file_exists(ACCOUNTS_CACHE_FILE)) return;
    $accounts = json_decode(file_get_contents(ACCOUNTS_CACHE_FILE), true);
    if (isset($accounts[$username])) {
        $accounts[$username]['password'] = $newPass;
        file_put_contents(ACCOUNTS_CACHE_FILE, json_encode($accounts), LOCK_EX);
    }
}

function getUserPreferences($username) {
    $cacheFile = PREFS_CACHE_DIR . "/{$username}.json";
    if (file_exists($cacheFile) && (time() - filemtime($cacheFile) < 300)) {
        return json_decode(file_get_contents($cacheFile), true);
    }
    
    $res = callDb(['action' => 'get_preferences', 'user' => $username]);
    $data = json_decode($res, true);
    if (is_array($data)) {
        file_put_contents($cacheFile, json_encode($data), LOCK_EX);
        return $data;
    }
    return ['tzintuk' => false, 'tzintuk_threshold' => 10, 'tzintuk_phone' => '', 'verification' => false, 'verification_threshold' => 100];
}

function saveUserPreferences($username, $prefs) {
    $cacheFile = PREFS_CACHE_DIR . "/{$username}.json";
    file_put_contents($cacheFile, json_encode($prefs), LOCK_EX);
    
    callDb([
        'action' => 'set_preferences',
        'user' => $username,
        'tzintuk' => $prefs['tzintuk'] ? 'true' : 'false',
        'tzintuk_threshold' => $prefs['tzintuk_threshold'],
        'tzintuk_phone' => $prefs['tzintuk_phone'],
        'verification' => $prefs['verification'] ? 'true' : 'false',
        'verification_threshold' => $prefs['verification_threshold']
    ]);
}

function callDb($params) {
    $url = APPS_SCRIPT_URL . '?' . http_build_query($params);
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    curl_setopt($ch, CURLOPT_TIMEOUT, 10);
    $response = curl_exec($ch);
    curl_close($ch);
    return $response;
}

function saveSession($file, $data) {
    file_put_contents($file, json_encode($data, JSON_PRETTY_PRINT), LOCK_EX);
}

function formatRead($messageText, $paramName, $maxDigits, $minDigits) {
    return "read=t-" . $messageText . "=" . $paramName . ",,{$maxDigits},{$minDigits},7,Digits,no,no,,,3,no,None,no,no";
}
