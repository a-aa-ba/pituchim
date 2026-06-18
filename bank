<?php
// הגדרת סוג התוכן כטקסט פשוט בעברית עבור ימות המשיח
header('Content-Type: text/plain; charset=utf-8');

// הפעלת סשן מבוסס מזהה שיחה טלפונית (ApiCallId) של ימות המשיח לשמירה על שלבי הניווט בשיחה
$call_id = isset($_GET['ApiCallId']) ? $_GET['ApiCallId'] : 'test_session';
session_id($call_id);
session_start();

// הגדרת נתיבי תיקיות האחסון בשרת
define('STORAGE_DIR', __DIR__ . '/storage');
define('GENERAL_DIR', STORAGE_DIR . '/general');
define('USERS_DIR', STORAGE_DIR . '/users');

// יצירת תיקיות הבסיס במידה והן לא קיימות
if (!file_exists(GENERAL_DIR)) mkdir(GENERAL_DIR, 0777, true);
if (!file_exists(USERS_DIR)) mkdir(USERS_DIR, 0777, true);

// אתחול קבצים כלליים במידה ואינם קיימים
$accounts_file = GENERAL_DIR . '/accounts.txt';
if (!file_exists($accounts_file)) {
    // קובץ ברירת מחדל לדוגמה
    file_put_contents($accounts_file, "1111:1234-50\n");
}
$logs_file = GENERAL_DIR . '/logs.txt';
if (!file_exists($logs_file)) touch($logs_file);

$verif_pass_file = GENERAL_DIR . '/verifications_and_passwords.txt';
if (!file_exists($verif_pass_file)) touch($verif_pass_file);

$notif_config_file = GENERAL_DIR . '/notifications_config.txt';
if (!file_exists($notif_config_file)) touch($notif_config_file);

// -----------------------------------------------------------------------------
// פונקציות עזר לניהול האחסון והדוחות
// -----------------------------------------------------------------------------

// קריאת כל החשבונות מהקובץ
function get_accounts() {
    $file = GENERAL_DIR . '/accounts.txt';
    $accounts = [];
    if (!file_exists($file)) return $accounts;
    $lines = file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        if (preg_match('/^([^:]+):([^-]+)-(.+)$/', $line, $matches)) {
            $accounts[$matches[1]] = [
                'password' => $matches[2],
                'balance' => floatval($matches[3])
            ];
        }
    }
    return $accounts;
}

// שמירת כל החשבונות לקובץ
function save_accounts($accounts) {
    $file = GENERAL_DIR . '/accounts.txt';
    $lines = [];
    foreach ($accounts as $user => $data) {
        $lines[] = "{$user}:{$data['password']}-{$data['balance']}";
    }
    file_put_contents($file, implode("\n", $lines) . "\n");
}

// אתחול תיקיית משתמש אישית
function init_user_dir($username) {
    $user_dir = USERS_DIR . '/' . $username;
    if (!file_exists($user_dir)) {
        mkdir($user_dir, 0777, true);
    }
    $recordings_dir = $user_dir . '/recordings';
    if (!file_exists($recordings_dir)) {
        mkdir($recordings_dir, 0777, true);
    }
}

// קריאת הגדרות צינתוקים ואימותים של משתמש
function get_user_config($username) {
    $file = GENERAL_DIR . '/notifications_config.txt';
    $default = [
        'notify_enabled' => 0,
        'notify_min_amount' => 0,
        'notify_phone' => '',
        'auth_enabled' => 0,
        'auth_min_amount' => 0
    ];
    if (!file_exists($file)) return $default;
    $lines = file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    foreach ($lines as $line) {
        $parts = explode(':', $line);
        if ($parts[0] === $username) {
            return [
                'notify_enabled' => isset($parts[1]) ? (int)$parts[1] : 0,
                'notify_min_amount' => isset($parts[2]) ? (float)$parts[2] : 0,
                'notify_phone' => isset($parts[3]) ? $parts[3] : '',
                'auth_enabled' => isset($parts[4]) ? (int)$parts[4] : 0,
                'auth_min_amount' => isset($parts[5]) ? (float)$parts[5] : 0
            ];
        }
    }
    return $default;
}

// שמירת הגדרות צינתוקים ואימותים של משתמש
function save_user_config($username, $config) {
    $file = GENERAL_DIR . '/notifications_config.txt';
    $lines = [];
    if (file_exists($file)) {
        $lines = file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    }
    $updated = false;
    $new_line = "{$username}:{$config['notify_enabled']}:{$config['notify_min_amount']}:{$config['notify_phone']}:{$config['auth_enabled']}:{$config['auth_min_amount']}";
    foreach ($lines as $idx => $line) {
        $parts = explode(':', $line);
        if ($parts[0] === $username) {
            $lines[$idx] = $new_line;
            $updated = true;
            break;
        }
    }
    if (!$updated) {
        $lines[] = $new_line;
    }
    file_put_contents($file, implode("\n", $lines) . "\n");
}

// כתיבת שורה ללוג הכללי
function log_global($message) {
    $file = GENERAL_DIR . '/logs.txt';
    $timestamp = date('Y-m-d H:i:s');
    file_put_contents($file, "[{$timestamp}] {$message}\n", FILE_APPEND);
}

// כתיבת שורה לדוח פעולות אישי
function log_user_activity($username, $type, $target, $amount) {
    init_user_dir($username);
    $file = USERS_DIR . '/' . $username . '/activity_report.txt'; // דוח פעולות - username
    $date = date('d/m/Y');
    $time = date('H:i');
    $line = "{$date},{$time},{$type},{$target},{$amount}\n";
    file_put_contents($file, $line, FILE_APPEND);
}

// כתיבת שורה לדוח אימותים ושינוי סיסמאות
function log_verification($username, $message) {
    $file = GENERAL_DIR . '/verifications_and_passwords.txt';
    $date = date('d/m/Y');
    $time = date('H:i');
    file_put_contents($file, "{$date},{$time},{$username},{$message}\n", FILE_APPEND);
}

// שליחת בקשה חיצונית לימות המשיח (צינתוק או שיחת אימות) - פונקציית שלד להתאמה אישית
function trigger_yemot_action($action_type, $phone) {
    log_global("הופעל מנגנון חיצוני: {$action_type} עבור מספר טלפון: {$phone}");
    
    // לדוגמה, קריאה ל-API של ימות המשיח לשיגור קמפיין צינתוקים:
    // $api_token = "YOUR_TOKEN";
    // $url = "https://www.call2all.co.il/ym/api/RunCampaign?token={$api_token}&phone={$phone}";
    // @file_get_contents($url);
}

// פונקציות לפלט של ימות המשיח
function yemot_read($text, $var_name, $min = 1, $max = 10, $timeout = 10, $allowed = 'N') {
    echo "read=t-{$text}={$var_name},yes,{$min},{$max},{$timeout},{$allowed}";
    exit;
}

function yemot_msg($text) {
    echo "id_list_message=t-{$text}";
    exit;
}

// מיפוי שלוחות תתי-עסק עבור שלוחה 1 (למשל שלוחה 1/1 היא עבור ת"ת, 1/2 עבור מכונות כביסה)
function get_business_by_ext($ext) {
    $map = [
        '1/1' => ['account' => '9999', 'name' => 'ת"ת'],
        '1/2' => ['account' => '8888', 'name' => 'מכונות הכביסה'],
        '1'   => ['account' => '9999', 'name' => 'ת"ת'] // ברירת מחדל
    ];
    return isset($map[$ext]) ? $map[$ext] : ['account' => '9999', 'name' => 'ת"ת'];
}

// -----------------------------------------------------------------------------
// מנגנון ניתוב ושמירת שלב נוכחי
// -----------------------------------------------------------------------------

// זיהוי השלוחה הנוכחית
$current_ext = isset($_GET['ext']) ? $_GET['ext'] : (isset($_GET['ApiExtension']) ? $_GET['ApiExtension'] : 'main');

// איפוס שלבי שיחה פנימיים אם המאזין עבר שלוחה באופן אקטיבי בטלפון
if (!isset($_SESSION['last_ext']) || $_SESSION['last_ext'] !== $current_ext) {
    $_SESSION['last_ext'] = $current_ext;
    unset($_SESSION['step']);
    unset($_SESSION['temp_data']);
}

// -----------------------------------------------------------------------------
// שלב 1: אבטחה והזדהות (Login) - חובה לכל השיחות שאינן מזוהות עדיין!
// -----------------------------------------------------------------------------
if (!isset($_SESSION['auth_user'])) {
    
    // א) אם המשתמש טרם הקיש קוד משתמש (4 ספרות)
    if (!isset($_SESSION['login_username']) && !isset($_GET['login_user'])) {
        yemot_read("אנא הקש את שם המשתמש שלך בן ארבע ספרות", "login_user", 4, 4);
    }
    
    // ב) עיבוד קוד המשתמש שהתקבל
    if (isset($_GET['login_user'])) {
        $entered_user = $_GET['login_user'];
        $accounts = get_accounts();
        
        if (!isset($accounts[$entered_user])) {
            // המשתמש אינו קיים במערכת - השמעת הודעה וניתוק כפי שנדרש באבטחה
            yemot_msg("שם משתמש זה אינו מופיע ברשימת המשתמשים הרשומים למערכת. לרישום למערכת יש לפנות לחדר התת בישיבה.");
        } else {
            // משתמש קיים - מעבר לבקשת סיסמה
            $_SESSION['login_username'] = $entered_user;
            yemot_read("אנא הקש את הסיסמה שלך ולסיום סולמית", "login_pass", 4, 15);
        }
    }
    
    // ג) עיבוד הסיסמה שהתקבלה
    if (isset($_GET['login_pass'])) {
        $entered_pass = $_GET['login_pass'];
        $user = $_SESSION['login_username'];
        $accounts = get_accounts();
        
        if ($accounts[$user]['password'] === $entered_pass) {
            // הזדהות הצליחה!
            $_SESSION['auth_user'] = $user;
            init_user_dir($user); // יצירת התיקיות האישיות במידת הצורך
            unset($_SESSION['login_username']);
            log_global("משתמש {$user} התחבר בהצלחה למערכת");
            
            // השמעת הודעת כניסה ומעבר להמשך השלוחה שהמשתמש ביקש להגיע אליה
            echo "id_list_message=t-זוהית בהצלחה.&";
        } else {
            // סיסמה שגויה - איפוס שלב והשמעת הודעה מתאימה
            unset($_SESSION['login_username']);
            yemot_read("הסיסמה שגויה אנא נסה שנית. נא להקיש שוב את שם המשתמש שלך בן ארבע ספרות", "login_user", 4, 4);
        }
    }
    
    // אם הגענו לכאן ואיננו מאומתים, נבקש סיסמה שוב
    if (isset($_SESSION['login_username'])) {
        yemot_read("אנא הקש את הסיסמה שלך ולסיום סולמית", "login_pass", 4, 15);
    }
}

// -----------------------------------------------------------------------------
// שלב 2: ניתוב שלוחות לאחר מעבר מוצלח של מנגנון הזיהוי
// -----------------------------------------------------------------------------
$user = $_SESSION['auth_user'];
$step = isset($_SESSION['step']) ? $_SESSION['step'] : 'init';

// מיפוי פעולות לפי שלוחות (1, 2, 3, 4, *, 0)
$main_ext_prefix = substr($current_ext, 0, 1);

switch ($main_ext_prefix) {

    // ==========================================
    // שלוחה 1: ביצוע תשלומים לעסק מוגדר
    // ==========================================
    case '1':
        $biz = get_business_by_ext($current_ext);
        
        if ($step === 'init') {
            $_SESSION['step'] = 'ext1_get_amount';
            yemot_read("אנא הקש את הסכום לחיוב ולסיום סולמית", "amount");
        }
        
        if ($step === 'ext1_get_amount' && isset($_GET['amount'])) {
            $amount = floatval($_GET['amount']);
            $accounts = get_accounts();
            $my_balance = $accounts[$user]['balance'];
            
            if ($my_balance < $amount) {
                $_SESSION['step'] = 'ext1_insufficient_retry';
                yemot_read("אין ברשותך מספיק יתרה. היתרה הנוכחית שלך היא {$my_balance} שקלים. לא ניתן לבצע את ההעברה בסכום זה. להקשת סכום אחר הקש 1 ליציאה הקש 2", "insufficient_choice", 1, 1);
            } else {
                $_SESSION['temp_data'] = ['amount' => $amount];
                $_SESSION['step'] = 'ext1_confirm';
                yemot_read("הינך מבקש להעביר סכום של {$amount} שקלים ל{$biz['name']}. לאישור הקש 1 לביטול הקש 2", "confirm_choice", 1, 1);
            }
        }
        
        if ($step === 'ext1_insufficient_retry' && isset($_GET['insufficient_choice'])) {
            if ($_GET['insufficient_choice'] == '1') {
                $_SESSION['step'] = 'ext1_get_amount';
                yemot_read("אנא הקש את הסכום לחיוב ולסיום סולמית", "amount");
            } else {
                yemot_msg("הפעולה בוטלה. שלום ותודה.");
            }
        }
        
        if ($step === 'ext1_confirm' && isset($_GET['confirm_choice'])) {
            if ($_GET['confirm_choice'] == '1') {
                $amount = $_SESSION['temp_data']['amount'];
                $config = get_user_config($user);
                
                // שיחת אימות במידה ומוגדר
                if ($config['auth_enabled'] && $amount >= $config['auth_min_amount']) {
                    trigger_yemot_action('verification', $config['notify_phone']);
                    log_verification($user, "בוצע אימות טלפוני מוצלח להעברת {$amount} שקלים ל{$biz['name']}");
                }
                
                // ביצוע העברה
                $accounts = get_accounts();
                $target_acc = $biz['account'];
                
                if (isset($accounts[$user]) && isset($accounts[$target_acc])) {
                    $accounts[$user]['balance'] -= $amount;
                    $accounts[$target_acc]['balance'] += $amount;
                    save_accounts($accounts);
                    
                    // כתיבה ללוגים ולדוחות
                    log_user_activity($user, "תשלום", $biz['name'], $amount);
                    log_user_activity($target_acc, "קבלה", $user, $amount);
                    log_global("העברה מוצלחת: {$user} העביר {$amount} שקלים ל{$target_acc} ({$biz['name']})");
                    
                    // צינתוק בעת ביצוע פעולה במידה ומוגדר
                    if ($config['notify_enabled'] && $amount >= $config['notify_min_amount'] && !empty($config['notify_phone'])) {
                        trigger_yemot_action('tzintuk', $config['notify_phone']);
                    }
                    
                    unset($_SESSION['step']);
                    unset($_SESSION['temp_data']);
                    yemot_msg("ההעברה בוצעה בהצלחה. שלום ותודה.");
                } else {
                    yemot_msg("חלה שגיאה במסד הנתונים. אנא נסה שנית מאוחר יותר.");
                }
            } else {
                unset($_SESSION['step']);
                unset($_SESSION['temp_data']);
                yemot_msg("הפעולה בוטלה.");
            }
        }
        break;

    // ==========================================
    // שלוחה 2: העברה לחשבון משתמש חופשי
    // ==========================================
    case '2':
        if ($step === 'init') {
            $_SESSION['step'] = 'ext2_get_target';
            yemot_read("הקש את שם המשתמש אליו הינך רוצה להעביר את הסכום המבוקש ולסיום סולמית", "target_user", 4, 10);
        }
        
        if ($step === 'ext2_get_target' && isset($_GET['target_user'])) {
            $target_user = $_GET['target_user'];
            $accounts = get_accounts();
            
            if (!isset($accounts[$target_user])) {
                $_SESSION['step'] = 'ext2_get_target';
                yemot_read("חשבון היעד לא נמצא במערכת. אנא הקש שוב את שם המשתמש להעברה", "target_user", 4, 10);
            } else {
                $_SESSION['temp_data'] = ['target' => $target_user];
                $_SESSION['step'] = 'ext2_get_amount';
                yemot_read("אנא הקש את הסכום להעברה ולסיום סולמית", "amount");
            }
        }
        
        if ($step === 'ext2_get_amount' && isset($_GET['amount'])) {
            $amount = floatval($_GET['amount']);
            $accounts = get_accounts();
            $my_balance = $accounts[$user]['balance'];
            $target_user = $_SESSION['temp_data']['target'];
            
            if ($my_balance < $amount) {
                $_SESSION['step'] = 'ext2_insufficient_retry';
                yemot_read("אין ברשותך מספיק יתרה. היתרה הנוכחית שלך היא {$my_balance} שקלים. להקשת סכום אחר הקש 1 ליציאה הקש 2", "insufficient_choice", 1, 1);
            } else {
                $_SESSION['temp_data']['amount'] = $amount;
                $_SESSION['step'] = 'ext2_confirm';
                yemot_read("הינך מבקש להעביר סכום של {$amount} שקלים למשתמש {$target_user}. לאישור הקש 1 לביטול הקש 2", "confirm_choice", 1, 1);
            }
        }
        
        if ($step === 'ext2_insufficient_retry' && isset($_GET['insufficient_choice'])) {
            if ($_GET['insufficient_choice'] == '1') {
                $_SESSION['step'] = 'ext2_get_amount';
                yemot_read("אנא הקש את הסכום להעברה ולסיום סולמית", "amount");
            } else {
                yemot_msg("הפעולה בוטלה.");
            }
        }
        
        if ($step === 'ext2_confirm' && isset($_GET['confirm_choice'])) {
            if ($_GET['confirm_choice'] == '1') {
                $amount = $_SESSION['temp_data']['amount'];
                $target_user = $_SESSION['temp_data']['target'];
                $config = get_user_config($user);
                
                // שיחת אימות
                if ($config['auth_enabled'] && $amount >= $config['auth_min_amount']) {
                    trigger_yemot_action('verification', $config['notify_phone']);
                    log_verification($user, "בוצע אימות טלפוני מוצלח להעברת {$amount} שקלים למשתמש {$target_user}");
                }
                
                $accounts = get_accounts();
                if (isset($accounts[$user]) && isset($accounts[$target_user])) {
                    $accounts[$user]['balance'] -= $amount;
                    $accounts[$target_user]['balance'] += $amount;
                    save_accounts($accounts);
                    
                    // רישום דוח פעולות ושינויים
                    log_user_activity($user, "העברה", $target_user, $amount);
                    log_user_activity($target_user, "קבלה", $user, $amount);
                    log_global("העברה מוצלחת: {$user} העביר {$amount} למשתמש {$target_user}");
                    
                    // צינתוק הגדרות
                    if ($config['notify_enabled'] && $amount >= $config['notify_min_amount'] && !empty($config['notify_phone'])) {
                        trigger_yemot_action('tzintuk', $config['notify_phone']);
                    }
                    
                    unset($_SESSION['step']);
                    unset($_SESSION['temp_data']);
                    yemot_msg("ההעברה בוצעה בהצלחה.");
                } else {
                    yemot_msg("שגיאה בביצוע ההעברה.");
                }
            } else {
                unset($_SESSION['step']);
                unset($_SESSION['temp_data']);
                yemot_msg("הפעולה בוטלה.");
            }
        }
        break;

    // ==========================================
    // שלוחה 3: היסטוריית פעולות (ניווט מקשים)
    // ==========================================
    case '3':
        $file = USERS_DIR . '/' . $user . '/activity_report.txt';
        $activities = [];
        if (file_exists($file)) {
            $lines = file($file, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            $activities = array_slice(array_reverse($lines), 0, 10); // 10 פעולות אחרונות, מהחדש לישן
        }
        
        if (empty($activities)) {
            yemot_msg("אין פעולות קודמות בחשבונך.");
        }
        
        $index = isset($_SESSION['history_index']) ? $_SESSION['history_index'] : 0;
        
        if (isset($_GET['nav_key'])) {
            $key = $_GET['nav_key'];
            if ($key == '8') {
                $index++; // הבא
            } elseif ($key == '2') {
                $index--; // הקודם
            }
        }
        
        // הגבלת אינדקס
        if ($index < 0) $index = 0;
        if ($index >= count($activities)) $index = count($activities) - 1;
        $_SESSION['history_index'] = $index;
        
        // פירוק שורת דוח הפעולה: Date,Time,Type,Target,Amount
        $parts = explode(',', $activities[$index]);
        $date = isset($parts[0]) ? $parts[0] : '';
        $time = isset($parts[1]) ? $parts[1] : '';
        $type = isset($parts[2]) ? $parts[2] : '';
        $target = isset($parts[3]) ? $parts[3] : '';
        $amount = isset($parts[4]) ? $parts[4] : '';
        
        $direction = ($type === 'קבלה') ? "מ" : "ל";
        $tts_msg = "בתאריך {$date}, בשעה {$time}, בוצעה פעולה של {$type} {$direction} חשבונך, עם גורם {$target}, על סך של {$amount} שקלים. למעבר לפעולה הבאה הקש 8, לפעולה הקודמת הקש 2, ליציאה הקש סולמית";
        
        yemot_read($tts_msg, "nav_key", 1, 1, 10, "2,8,#");
        break;

    // ==========================================
    // שלוחה 4: סליקת אשראי (בפיתוח)
    // ==========================================
    case '4':
        yemot_msg("שלוחה זו עדיין בפיתוח.");
        break;

    // ==========================================
    // שלוחה *: שמיעת מצב החשבון
    // ==========================================
    case '*':
        $accounts = get_accounts();
        $balance = isset($accounts[$user]) ? $accounts[$user]['balance'] : 0;
        yemot_msg("היתרה בחשבונך עומדת על סך של {$balance} שקלים.");
        break;

    // ==========================================
    // שלוחה 0: האזור האישי
    // ==========================================
    case '0':
        // ניתוח תתי-שלוחות באזור האישי (0/1, 0/2, 0/3)
        $sub_ext = isset($_GET['ext']) ? $_GET['ext'] : $current_ext;
        
        if ($sub_ext === '0') {
            $_SESSION['step'] = 'ext0_menu';
            yemot_read("לשינוי סיסמה הקש 1, להגדרות קבלת צינתוק הקש 2, להגדרות קבלת שיחת אימות הקש 3", "ext0_choice", 1, 1);
        }
        
        if ($step === 'ext0_menu' && isset($_GET['ext0_choice'])) {
            $choice = $_GET['ext0_choice'];
            if ($choice == '1') $sub_ext = '0/1';
            elseif ($choice == '2') $sub_ext = '0/2';
            elseif ($choice == '3') $sub_ext = '0/3';
            $_SESSION['step'] = 'init'; // אתחול שלב לתת השלוחה הנבחרת
        }

        // --- 0/1: שינוי סיסמא ---
        if ($sub_ext === '0/1') {
            if ($step === 'init') {
                $_SESSION['step'] = 'ext0_1_current_pass';
                yemot_read("אנא הקש את הסיסמה העכשווית שלך", "current_pass");
            }
            
            if ($step === 'ext0_1_current_pass' && isset($_GET['current_pass'])) {
                $accounts = get_accounts();
                if ($accounts[$user]['password'] === $_GET['current_pass']) {
                    // ביצוע שיחת אימות
                    $config = get_user_config($user);
                    trigger_yemot_action('verification', $config['notify_phone']);
                    log_verification($user, "נשלחה שיחת אימות לצורך החלפת סיסמה");
                    
                    $_SESSION['step'] = 'ext0_1_new_pass';
                    yemot_read("הסיסמה נכונה. אנא הקש את הסיסמה החדשה, באורך 4 ספרות לפחות", "new_pass", 4, 15);
                } else {
                    unset($_SESSION['step']);
                    yemot_msg("הסיסמה שגויה. הפעולה מבוטלת.");
                }
            }
            
            if ($step === 'ext0_1_new_pass' && isset($_GET['new_pass'])) {
                $_SESSION['temp_data'] = ['new_pass' => $_GET['new_pass']];
                $_SESSION['step'] = 'ext0_1_confirm_pass';
                yemot_read("אנא הקש את הסיסמה החדשה פעם נוספת לאימות", "new_pass_confirm", 4, 15);
            }
            
            if ($step === 'ext0_1_confirm_pass' && isset($_GET['new_pass_confirm'])) {
                if ($_GET['new_pass_confirm'] === $_SESSION['temp_data']['new_pass']) {
                    $new_pass = $_SESSION['temp_data']['new_pass'];
                    $accounts = get_accounts();
                    $accounts[$user]['password'] = $new_pass;
                    save_accounts($accounts);
                    
                    log_verification($user, "הסיסמה שונתה בהצלחה");
                    unset($_SESSION['step']);
                    unset($_SESSION['temp_data']);
                    yemot_msg("הסיסמה שונתה בהצלחה.");
                } else {
                    unset($_SESSION['step']);
                    unset($_SESSION['temp_data']);
                    yemot_msg("הסיסמאות אינן תואמות. הפעולה מבוטלת.");
                }
            }
        }

        // --- 0/2: הגדרות צינתוקים ---
        if ($sub_ext === '0/2') {
            if ($step === 'init') {
                $_SESSION['step'] = 'ext0_2_menu';
                yemot_read("להפעלה או ביטול השירות הקש 1, להגדרת סכום מינימלי לקבלת צינתוק הקש 2, להגדרת מספר הטלפון לצינתוק הקש 3", "tzintuk_menu_choice", 1, 1);
            }
            
            if ($step === 'ext0_2_menu' && isset($_GET['tzintuk_menu_choice'])) {
                $choice = $_GET['tzintuk_menu_choice'];
                $config = get_user_config($user);
                
                if ($choice == '1') {
                    // הפעלה או ביטול
                    $config['notify_enabled'] = $config['notify_enabled'] == 1 ? 0 : 1;
                    save_user_config($user, $config);
                    $msg = $config['notify_enabled'] == 1 ? "שירות הצינתוקים הופעל בהצלחה." : "שירות הצינתוקים בוטל בהצלחה.";
                    unset($_SESSION['step']);
                    yemot_msg($msg);
                }
                elseif ($choice == '2') {
                    if ($config['notify_min_amount'] > 0) {
                        $_SESSION['step'] = 'ext0_2_amount_ask';
                        yemot_read("הסכום המוגדר כעת הוא {$config['notify_min_amount']} שקלים. לשינוי הקש 1 ליציאה הקש 2", "change_ask", 1, 1);
                    } else {
                        $_SESSION['step'] = 'ext0_2_amount_set';
                        yemot_read("לא מוגדר סכום לצינתוק. אנא הקש את הסכום ממנו תתחיל לקבל צינתוק בעת ביצוע עיסקה", "new_amount");
                    }
                }
                elseif ($choice == '3') {
                    if (!empty($config['notify_phone'])) {
                        $_SESSION['step'] = 'ext0_2_phone_ask';
                        yemot_read("המספר המוגדר לקבלת צינתוק הינו {$config['notify_phone']}. לשינוי הקש 1 ליציאה הקש 2", "change_ask", 1, 1);
                    } else {
                        $_SESSION['step'] = 'ext0_2_phone_set';
                        yemot_read("לא מוגדר מספר. אנא הקש את המספר אליו יצנתק בעת ביצוע עיסקה במערכת. מינימום שמונה ספרות מקסימום תשע", "new_phone", 8, 9);
                    }
                }
            }
            
            // הגדרת סכום
            if ($step === 'ext0_2_amount_ask' && isset($_GET['change_ask'])) {
                if ($_GET['change_ask'] == '1') {
                    $_SESSION['step'] = 'ext0_2_amount_set';
                    yemot_read("אנא הקש את הסכום ממנו תתחיל לקבל צינתוק בעת ביצוע עיסקה", "new_amount");
                } else {
                    unset($_SESSION['step']);
                    yemot_msg("הפעולה בוטלה.");
                }
            }
            if ($step === 'ext0_2_amount_set' && isset($_GET['new_amount'])) {
                $config = get_user_config($user);
                $config['notify_min_amount'] = floatval($_GET['new_amount']);
                save_user_config($user, $config);
                unset($_SESSION['step']);
                yemot_msg("ההגדרה עודכנה בהצלחה.");
            }
            
            // הגדרת טלפון
            if ($step === 'ext0_2_phone_ask' && isset($_GET['change_ask'])) {
                if ($_GET['change_ask'] == '1') {
                    $_SESSION['step'] = 'ext0_2_phone_set';
                    yemot_read("אנא הקש את המספר אליו יצנתק בעת ביצוע עיסקה במערכת", "new_phone", 8, 9);
                } else {
                    unset($_SESSION['step']);
                    yemot_msg("הפעולה בוטלה.");
                }
            }
            if ($step === 'ext0_2_phone_set' && isset($_GET['new_phone'])) {
                $phone = $_GET['new_phone'];
                if (strlen($phone) >= 8 && strlen($phone) <= 9) {
                    $config = get_user_config($user);
                    $config['notify_phone'] = $phone;
                    save_user_config($user, $config);
                    unset($_SESSION['step']);
                    yemot_msg("המספר הוגדר בהצלחה. שימו לב! כדי לקבל צינתוק יש להירשם בשלוחה 0, 2, ואז 1.");
                } else {
                    yemot_read("מספר לא תקין. אנא הקש את המספר מחדש, שמונה או תשע ספרות", "new_phone", 8, 9);
                }
            }
        }

        // --- 0/3: הגדרות אימותים ---
        if ($sub_ext === '0/3') {
            if ($step === 'init') {
                $_SESSION['step'] = 'ext0_3_menu';
                yemot_read("להפעלה או ביטול קבלת שיחת אימות הקש 1, להגדרת סכום מינימלי לקבלת שיחת אימות הקש 2", "auth_menu_choice", 1, 1);
            }
            
            if ($step === 'ext0_3_menu' && isset($_GET['auth_menu_choice'])) {
                $choice = $_GET['auth_menu_choice'];
                $config = get_user_config($user);
                
                if ($choice == '1') {
                    $config['auth_enabled'] = $config['auth_enabled'] == 1 ? 0 : 1;
                    save_user_config($user, $config);
                    $msg = $config['auth_enabled'] == 1 ? "שיחת אימות הופעלה בהצלחה." : "שיחת אימות בוטלה בהצלחה.";
                    unset($_SESSION['step']);
                    yemot_msg($msg);
                }
                elseif ($choice == '2') {
                    if ($config['auth_min_amount'] > 0) {
                        $_SESSION['step'] = 'ext0_3_amount_ask';
                        yemot_read("הסכום המוגדר הוא {$config['auth_min_amount']} שקלים. לשינוי הקש 1 ליציאה הקש 2", "change_ask", 1, 1);
                    } else {
                        $_SESSION['step'] = 'ext0_3_amount_set';
                        yemot_read("לא מוגדר סכום לשיחת אימות. אנא הקש את הסכום ממנו תתחיל לקבל שיחת אימות בעת ביצוע עיסקה", "new_amount");
                    }
                }
            }
            
            if ($step === 'ext0_3_amount_ask' && isset($_GET['change_ask'])) {
                if ($_GET['change_ask'] == '1') {
                    $_SESSION['step'] = 'ext0_3_amount_set';
                    yemot_read("אנא הקש את הסכום ממנו תתחיל לקבל שיחת אימות בעת ביצוע עיסקה", "new_amount");
                } else {
                    unset($_SESSION['step']);
                    yemot_msg("הפעולה בוטלה.");
                }
            }
            if ($step === 'ext0_3_amount_set' && isset($_GET['new_amount'])) {
                $config = get_user_config($user);
                $config['auth_min_amount'] = floatval($_GET['new_amount']);
                save_user_config($user, $config);
                unset($_SESSION['step']);
                yemot_msg("ההגדרה עודכנה בהצלחה.");
            }
        }
        break;

    default:
        yemot_msg("שלוחה שגויה במערכת.");
        break;
}
