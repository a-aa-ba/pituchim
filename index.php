<?php
// הגדרת סוג התוכן כטקסט פשוט בעברית עבור ימות המשיח
header('Content-Type: text/plain; charset=utf-8');

// הפעלת סשן מבוסס מזהה שיחה טלפונית (ApiCallId) של ימות המשיח
$call_id = isset($_GET['ApiCallId']) ? $_GET['ApiCallId'] : 'test_session';
session_id($call_id);
session_start();

// -----------------------------------------------------------------------------
// הגדרת קישור הגוגל סקריפט שלכם (נא להחליף בקישור שלכם!)
// -----------------------------------------------------------------------------
define('GSHEET_API_URL', 'https://script.google.com/macros/s/AKfycbyutWqr3ozMwzd9dJUxkOXkfQmVM8QS-kRCDF-bwgm7utJTFnLYtL0ndrCIVHBKj2Vw/exec');

// פונקציית תקשורת מול גוגל שיטס דרך API
function call_gsheet_api($params, $post_data = null) {
    $url = GSHEET_API_URL . '?' . http_build_query($params);
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
    curl_setopt($ch, CURLOPT_FOLLOWLOCATION, true);
    if ($post_data !== null) {
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($post_data));
        curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/json']);
    }
    $response = curl_exec($ch);
    curl_close($ch);
    return $response;
}

// -----------------------------------------------------------------------------
// פונקציות תקשורת נתונים
// -----------------------------------------------------------------------------

// קריאת כל החשבונות מגוגל שיטס
function get_accounts() {
    $res = call_gsheet_api(['action' => 'getAccounts']);
    $data = json_decode($res, true);
    return is_array($data) ? $data : [];
}

// עדכון חשבונות מרוכז
function save_accounts_bulk($updates) {
    call_gsheet_api(['action' => 'saveAccountsBulk'], [
        'action' => 'saveAccountsBulk',
        'updates' => $updates
    ]);
}

// קריאת הגדרות משתמש מגוגל שיטס
function get_user_config($username) {
    $res = call_gsheet_api(['action' => 'getUserConfig', 'user' => $username]);
    $data = json_decode($res, true);
    return is_array($data) ? $data : [
        'notify_enabled' => 0,
        'notify_min_amount' => 0,
        'notify_phone' => '',
        'auth_enabled' => 0,
        'auth_min_amount' => 0
    ];
}

// שמירת הגדרות משתמש לגוגל שיטס
function save_user_config($username, $config) {
    call_gsheet_api(['action' => 'saveUserConfig'], array_merge(['action' => 'saveUserConfig', 'user' => $username], $config));
}

// כתיבה ללוג הכללי בגוגל שיטס
function log_global($message) {
    call_gsheet_api(['action' => 'logGlobal'], [
        'action' => 'logGlobal',
        'message' => $message
    ]);
}

// כתיבה לדוח פעולות אישי בגוגל שיטס
function log_user_activity($username, $type, $target, $amount) {
    $date = date('d/m/Y');
    $time = date('H:i');
    call_gsheet_api(['action' => 'logActivity'], [
        'action' => 'logActivity',
        'user' => $username,
        'date' => $date,
        'time' => $time,
        'type' => $type,
        'target' => $target,
        'amount' => $amount
    ]);
}

// כתיבה ללוג אימותים בגוגל שיטס
function log_verification($username, $message) {
    $date = date('d/m/Y');
    $time = date('H:i');
    call_gsheet_api(['action' => 'logVerification'], [
        'action' => 'logVerification',
        'user' => $username,
        'date' => $date,
        'time' => $time,
        'message' => $message
    ]);
}

// הדמיית פונקציה חיצונית לביצוע צינתוק או אימות טלפוני
function trigger_yemot_action($action_type, $phone) {
    log_global("הופעל מנגנון חיצוני: {$action_type} עבור מספר טלפון: {$phone}");
}

// פונקציות להחזרת תשובה לימות המשיח בפורמט הנדרש
function yemot_read($text, $var_name, $max = '', $min = '', $timeout = 10, $allowed = 'No') {
    // בפורמט של ימות המשיח: [שם_המשתנה],[האם להחליף-yes],[מקסימום],[מינימום],[timeout],[סוג],[האם להמתין לסולמית-yes]
    echo "read=t-{$text}={$var_name},yes,{$max},{$min},{$timeout},{$allowed},yes";
    exit;
}

function yemot_msg($text) {
    echo "id_list_message=t-{$text}";
    exit;
}

// מיפוי שלוחות תשלום עבור שלוחה 1 (עסק מוגדר מראש)
function get_business_by_ext($ext) {
    $map = [
        '1/1' => ['account' => '9999', 'name' => 'ת"ת'],
        '1/2' => ['account' => '8888', 'name' => 'מכונות הכביסה'],
        '1'   => ['account' => '9999', 'name' => 'ת"ת']
    ];
    return isset($map[$ext]) ? $map[$ext] : ['account' => '9999', 'name' => 'ת"ת'];
}

// -----------------------------------------------------------------------------
// מנגנון ניתוב ושמירת שלב נוכחי
// -----------------------------------------------------------------------------

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
    
    // א) בקשת קוד משתמש (4 ספרות)
    if (!isset($_SESSION['login_username']) && !isset($_GET['login_user'])) {
        yemot_read("אנא הקש את שם המשתמש שלך בן ארבע ספרות", "login_user", 4, 4);
    }
    
    // ב) עיבוד קוד המשתמש שהתקבל
    if (isset($_GET['login_user'])) {
        $entered_user = $_GET['login_user'];
        $accounts = get_accounts();
        
        if (!isset($accounts[$entered_user])) {
            yemot_msg("שם משתמש זה אינו מופיע ברשימת המשתמשים הרשומים למערכת. לרישום למערכת יש לפנות לחדר התת בישיבה.");
        } else {
            $_SESSION['login_username'] = $entered_user;
            // מעבר לקבלת סיסמה ללא הגבלת תווים בטלפון כדי למנוע שגיאות של ימות המשיח
            yemot_read("אנא הקש את הסיסמה שלך ולסיום סולמית", "login_pass", "", "");
        }
    }
    
    // ג) עיבוד הסיסמה שהתקבלה
    if (isset($_GET['login_pass'])) {
        $entered_pass = $_GET['login_pass'];
        $user = $_SESSION['login_username'];
        $accounts = get_accounts();
        
        if (isset($accounts[$user]) && $accounts[$user]['password'] === $entered_pass) {
            $_SESSION['auth_user'] = $user;
            unset($_SESSION['login_username']);
            log_global("משתמש {$user} התחבר בהצלחה למערכת");
            
            echo "id_list_message=t-זוהית בהצלחה.&";
        } else {
            unset($_SESSION['login_username']);
            yemot_read("הסיסמה שגויה אנא נסה שנית. נא להקיש שוב את שם המשתמש שלך בן ארבע ספרות", "login_user", 4, 4);
        }
    }
    
    if (isset($_SESSION['login_username'])) {
        yemot_read("אנא הקש את הסיסמה שלך ולסיום סולמית", "login_pass", "", "");
    }
}

// -----------------------------------------------------------------------------
// שלב 2: ניתוב שלוחות לאחר מעבר מוצלח של מנגנון הזיהוי
// -----------------------------------------------------------------------------
$user = $_SESSION['auth_user'];
$step = isset($_SESSION['step']) ? $_SESSION['step'] : 'init';

$main_ext_prefix = substr($current_ext, 0, 1);

switch ($main_ext_prefix) {

    // ==========================================
    // שלוחה 1: ביצוע תשלומים לעסק מוגדר
    // ==========================================
    case '1':
        $biz = get_business_by_ext($current_ext);
        
        if ($step === 'init') {
            $_SESSION['step'] = 'ext1_get_amount';
            yemot_read("אנא הקש את הסכום לחיוב ולסיום סולמית", "amount", 10, 1);
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
                yemot_read("אנא הקש את הסכום לחיוב ולסיום סולמית", "amount", 10, 1);
            } else {
                yemot_msg("הפעולה בוטלה. שלום ותודה.");
            }
        }
        
        if ($step === 'ext1_confirm' && isset($_GET['confirm_choice'])) {
            if ($_GET['confirm_choice'] == '1') {
                $amount = $_SESSION['temp_data']['amount'];
                $config = get_user_config($user);
                
                if ($config['auth_enabled'] && $amount >= $config['auth_min_amount']) {
                    trigger_yemot_action('verification', $config['notify_phone']);
                    log_verification($user, "בוצע אימות טלפוני מוצלח להעברת {$amount} שקלים ל{$biz['name']}");
                }
                
                $accounts = get_accounts();
                $target_acc = $biz['account'];
                
                if (isset($accounts[$user]) && isset($accounts[$target_acc])) {
                    $accounts[$user]['balance'] -= $amount;
                    $accounts[$target_acc]['balance'] += $amount;
                    
                    $updates = [
                        ['user' => $user, 'pass' => $accounts[$user]['password'], 'balance' => $accounts[$user]['balance']],
                        ['user' => $target_acc, 'pass' => $accounts[$target_acc]['password'], 'balance' => $accounts[$target_acc]['balance']]
                    ];
                    save_accounts_bulk($updates);
                    
                    log_user_activity($user, "תשלום", $biz['name'], $amount);
                    log_user_activity($target_acc, "קבלה", $user, $amount);
                    log_global("העברה מוצלחת: {$user} העביר {$amount} שקלים ל{$target_acc} ({$biz['name']})");
                    
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
            yemot_read("הקש את שם המשתמש אליו הינך רוצה להעביר את הסכום המבוקש ולסיום סולמית", "target_user", 4, 4);
        }
        
        if ($step === 'ext2_get_target' && isset($_GET['target_user'])) {
            $target_user = $_GET['target_user'];
            $accounts = get_accounts();
            
            if (!isset($accounts[$target_user])) {
                $_SESSION['step'] = 'ext2_get_target';
                yemot_read("חשבון היעד לא נמצא במערכת. אנא הקש שוב את שם המשתמש להעברה", "target_user", 4, 4);
            } else {
                $_SESSION['temp_data'] = ['target' => $target_user];
                $_SESSION['step'] = 'ext2_get_amount';
                yemot_read("אנא הקש את הסכום להעברה ולסיום סולמית", "amount", 10, 1);
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
                yemot_read("אנא הקש את הסכום להעברה ולסיום סולמית", "amount", 10, 1);
            } else {
                yemot_msg("הפעולה בוטלה.");
            }
        }
        
        if ($step === 'ext2_confirm' && isset($_GET['confirm_choice'])) {
            if ($_GET['confirm_choice'] == '1') {
                $amount = $_SESSION['temp_data']['amount'];
                $target_user = $_SESSION['temp_data']['target'];
                $config = get_user_config($user);
                
                if ($config['auth_enabled'] && $amount >= $config['auth_min_amount']) {
                    trigger_yemot_action('verification', $config['notify_phone']);
                    log_verification($user, "בוצע אימות טלפוני מוצלח להעברת {$amount} שקלים למשתמש {$target_user}");
                }
                
                $accounts = get_accounts();
                if (isset($accounts[$user]) && isset($accounts[$target_user])) {
                    $accounts[$user]['balance'] -= $amount;
                    $accounts[$target_user]['balance'] += $amount;
                    
                    $updates = [
                        ['user' => $user, 'pass' => $accounts[$user]['password'], 'balance' => $accounts[$user]['balance']],
                        ['user' => $target_user, 'pass' => $accounts[$target_user]['password'], 'balance' => $accounts[$target_user]['balance']]
                    ];
                    save_accounts_bulk($updates);
                    
                    log_user_activity($user, "העברה", $target_user, $amount);
                    log_user_activity($target_user, "קבלה", $user, $amount);
                    log_global("העברה מוצלחת: {$user} העביר {$amount} למשתמש {$target_user}");
                    
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
        $res = call_gsheet_api(['action' => 'getUserActivity', 'user' => $user]);
        $activities = json_decode($res, true);
        if (!is_array($activities)) $activities = [];
        
        $activities = array_slice(array_reverse($activities), 0, 10);
        
        if (empty($activities)) {
            yemot_msg("אין פעולות קודמות בחשבונך.");
        }
        
        $index = isset($_SESSION['history_index']) ? $_SESSION['history_index'] : 0;
        
        if (isset($_GET['nav_key'])) {
            $key = $_GET['nav_key'];
            if ($key == '8') {
                $index++;
            } elseif ($key == '2') {
                $index--;
            }
        }
        
        if ($index < 0) $index = 0;
        if ($index >= count($activities)) $index = count($activities) - 1;
        $_SESSION['history_index'] = $index;
        
        $parts = explode(',', $activities[$index]);
        $date = isset($parts[0]) ? $parts[0] : '';
        $time = isset($parts[1]) ? $parts[1] : '';
        $type = isset($parts[2]) ? $parts[2] : '';
        $target = isset($parts[3]) ? $parts[3] : '';
        $amount = isset($parts[4]) ? $parts[4] : '';
        
        $direction = ($type === 'קבלה') ? "מ" : "ל";
        $tts_msg = "בתאריך {$date}, בשעה {$time}, בוצעה פעולה של {$type} {$direction} חשבונך, עם גורם {$target}, על סך של {$amount} שקלים. למעבר לפעולה הבאה הקש 8, לפעולה הקודמת הקש 2, ליציאה הקש סולמית";
        
        yemot_read($tts_msg, "nav_key", 1, 1, 10, "No");
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
            $_SESSION['step'] = 'init';
        }

        if ($sub_ext === '0/1') {
            if ($step === 'init') {
                $_SESSION['step'] = 'ext0_1_current_pass';
                yemot_read("אנא הקש את הסיסמה העכשווית שלך ולסיום סולמית", "current_pass", "", "");
            }
            
            if ($step === 'ext0_1_current_pass' && isset($_GET['current_pass'])) {
                $accounts = get_accounts();
                if ($accounts[$user]['password'] === $_GET['current_pass']) {
                    $config = get_user_config($user);
                    trigger_yemot_action('verification', $config['notify_phone']);
                    log_verification($user, "נשלחה שיחת אימות לצורך החלפת סיסמה");
                    
                    $_SESSION['step'] = 'ext0_1_new_pass';
                    yemot_read("הסיסמה נכונה. אנא הקש את הסיסמה החדשה, באורך 4 ספרות לפחות ולסיום סולמית", "new_pass", "", "");
                } else {
                    unset($_SESSION['step']);
                    yemot_msg("הסיסמה שגויה. הפעולה מבוטלת.");
                }
            }
            
            if ($step === 'ext0_1_new_pass' && isset($_GET['new_pass'])) {
                $new_pass = $_GET['new_pass'];
                if (strlen($new_pass) < 4) {
                    yemot_read("הסיסמה קצרה מדי. עליה להיות לפחות ארבע ספרות. אנא הקש סיסמה חדשה ולסיום סולמית", "new_pass", "", "");
                }
                $_SESSION['temp_data'] = ['new_pass' => $new_pass];
                $_SESSION['step'] = 'ext0_1_confirm_pass';
                yemot_read("אנא הקש את הסיסמה החדשה פעם נוספת לאימות ולסיום סולמית", "new_pass_confirm", "", "");
            }
            
            if ($step === 'ext0_1_confirm_pass' && isset($_GET['new_pass_confirm'])) {
                if ($_GET['new_pass_confirm'] === $_SESSION['temp_data']['new_pass']) {
                    $new_pass = $_SESSION['temp_data']['new_pass'];
                    $accounts = get_accounts();
                    $accounts[$user]['password'] = $new_pass;
                    
                    $updates = [
                        ['user' => $user, 'pass' => $new_pass, 'balance' => $accounts[$user]['balance']]
                    ];
                    save_accounts_bulk($updates);
                    
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

        if ($sub_ext === '0/2') {
            if ($step === 'init') {
                $_SESSION['step'] = 'ext0_2_menu';
                yemot_read("להפעלה או ביטול השירות הקש 1, להגדרת סכום מינימלי לקבלת צינתוק הקש 2, להגדרת מספר הטלפון לצינתוק הקש 3", "tzintuk_menu_choice", 1, 1);
            }
            
            if ($step === 'ext0_2_menu' && isset($_GET['tzintuk_menu_choice'])) {
                $choice = $_GET['tzintuk_menu_choice'];
                $config = get_user_config($user);
                
                if ($choice == '1') {
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
                        yemot_read("לא מוגדר סכום לצינתוק. אנא הקש את הסכום ממנו תתחיל לקבל צינתוק בעת ביצוע עיסקה", "new_amount", 10, 1);
                    }
                }
                elseif ($choice == '3') {
                    if (!empty($config['notify_phone'])) {
                        $_SESSION['step'] = 'ext0_2_phone_ask';
                        yemot_read("המספר המוגדר לקבלת צינתוק הינו {$config['notify_phone']}. לשינוי הקש 1 ליציאה הקש 2", "change_ask", 1, 1);
                    } else {
                        $_SESSION['step'] = 'ext0_2_phone_set';
                        yemot_read("לא מוגדר מספר. אנא הקש את המספר אליו יצנתק בעת ביצוע עיסקה במערכת. מינימום שמונה ספרות מקסימום תשע", "new_phone", 9, 8);
                    }
                }
            }
            
            if ($step === 'ext0_2_amount_ask' && isset($_GET['change_ask'])) {
                if ($_GET['change_ask'] == '1') {
                    $_SESSION['step'] = 'ext0_2_amount_set';
                    yemot_read("אנא הקש את הסכום ממנו תתחיל לקבל צינתוק בעת ביצוע עיסקה", "new_amount", 10, 1);
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
            
            if ($step === 'ext0_2_phone_ask' && isset($_GET['change_ask'])) {
                if ($_GET['change_ask'] == '1') {
                    $_SESSION['step'] = 'ext0_2_phone_set';
                    yemot_read("אנא הקש את המספר אליו יצנתק בעת ביצוע עיסקה במערכת", "new_phone", 9, 8);
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
                    yemot_read("מספר לא תקין. אנא הקש את המספר מחדש, שמונה או תשע ספרות", "new_phone", 9, 8);
                }
            }
        }

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
                        yemot_read("לא מוגדר סכום לשיחת אימות. אנא הקש את הסכום ממנו תתחיל לקבל שיחת אימות בעת ביצוע עיסקה", "new_amount", 10, 1);
                    }
                }
            }
            
            if ($step === 'ext0_3_amount_ask' && isset($_GET['change_ask'])) {
                if ($_GET['change_ask'] == '1') {
                    $_SESSION['step'] = 'ext0_3_amount_set';
                    yemot_read("אנא הקש את הסכום ממנו תתחיל לקבל שיחת אימות בעת ביצוע עיסקה", "new_amount", 10, 1);
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
