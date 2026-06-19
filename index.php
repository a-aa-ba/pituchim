<?php
// הגדרת קבועים עבור התקשרות מול ה-API של ימות המשיח
define('YEMOT_TOKEN', 'YOUR_YEMOT_SYSTEM_TOKEN_HERE');     // הכנס כאן את הטוקן של המערכת שלך
define('YEMOT_CALLER_ID', 'YOUR_YEMOT_CALLER_ID_HERE');   // מספר המערכת המאושר להוצאת שיחות/צינתוקים

// מיפוי שלוחות לעסקים בשלוחה 1 (ביצוע תשלומים)
// השרת יזהה אוטומטית באיזו שלוחה המאזין נמצא (למשל 1/1 או 1/2) ויציג את שם העסק והחשבון המתאימים
$business_config = [
    '1/1' => ['username' => 'tora_study', 'name' => 'תלמוד תורה'],
    '1/2' => ['username' => 'laundry_machines', 'name' => 'מכונות כביסה'],
    // ניתן להוסיף כאן שלוחות נוספות בקלות לפי הצורך
];

// יצירת תיקיות האחסון אם הן אינן קיימות בשרת
if (!is_dir(__DIR__ . '/storage')) {
    mkdir(__DIR__ . '/storage', 0777, true);
}
if (!is_dir(__DIR__ . '/sessions')) {
    mkdir(__DIR__ . '/sessions', 0777, true);
}

// ==========================================
// 1. מחלקת ניהול בסיס הנתונים (JSON)
// ==========================================
class AccountsDb {
    private $filepath;
    private $data = [];

    public function __construct($filepath) {
        $this->filepath = $filepath;
        $this->load();
    }

    private function load() {
        if (!file_exists($this->filepath)) {
            // יצירת נתוני בדיקה ראשוניים בפורמט מובנה (JSON) המאפשר לשמור את הגדרות האימות והצינתוק
            $this->data = [
                "1111" => [
                    "password" => "1234",
                    "balance" => 50,
                    "phone" => "0554000000",
                    "verification_active" => true,       // האם מוגדרת שיחת אימות
                    "verification_min_amount" => 20,    // סכום מינימלי להפעלת שיחת אימות
                    "tzintuk_on_action" => true,         // האם לשלוח צינתוק לאחר ביצוע פעולה
                    "tzintuk_min_amount" => 10          // סכום מינימלי לשליחת צינתוק בסיום הפעולה
                ],
                "2222" => [
                    "password" => "5678",
                    "balance" => 100,
                    "phone" => "0554111111",
                    "verification_active" => false,
                    "verification_min_amount" => 0,
                    "tzintuk_on_action" => true,
                    "tzintuk_min_amount" => 5
                ],
                "tora_study" => [
                    "password" => "pass",
                    "balance" => 1000,
                    "name" => "תלמוד תורה",
                    "is_business" => true
                ],
                "laundry_machines" => [
                    "password" => "pass",
                    "balance" => 500,
                    "name" => "מכונות כביסה",
                    "is_business" => true
                ]
            ];
            $this->save();
        } else {
            $json = file_get_contents($this->filepath);
            $this->data = json_decode($json, true) ?: [];
        }
    }

    public function save() {
        file_put_contents($this->filepath, json_encode($this->data, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
    }

    public function get($username) {
        return isset($this->data[$username]) ? $this->data[$username] : null;
    }

    public function exists($username) {
        return isset($this->data[$username]);
    }

    public function updateBalance($username, $new_balance) {
        if (isset($this->data[$username])) {
            $this->data[$username]['balance'] = $new_balance;
            $this->save();
            return true;
        }
        return false;
    }
}

// ==========================================
// 2. מחלקת ניהול הסשן (Session) לכל שיחה
// ==========================================
class SessionManager {
    private $filepath;
    private $data = [];

    public function __construct($session_id) {
        $this->filepath = __DIR__ . "/sessions/{$session_id}.json";
        $this->load();
    }

    private function load() {
        if (file_exists($this->filepath)) {
            $json = file_get_contents($this->filepath);
            $this->data = json_decode($json, true) ?: [];
        } else {
            $this->data = [
                'step' => 'start',
                'logged_in_user' => null,
                'amount' => null,
                'recipient' => null,
                'verification_code' => null
            ];
        }
    }

    public function get($key, $default = null) {
        return isset($this->data[$key]) ? $this->data[$key] : $default;
    }

    public function set($key, $value) {
        $this->data[$key] = $value;
        $this->save();
    }

    public function save() {
        file_put_contents($this->filepath, json_encode($this->data));
    }

    public function destroy() {
        if (file_exists($this->filepath)) {
            unlink($this->filepath);
        }
    }
}

// ==========================================
// 3. פונקציית כתיבה ללוג המערכת
// ==========================================
function write_to_log($message) {
    $log_file = __DIR__ . '/storage/log.txt';
    $timestamp = date('Y-m-d H:i:s');
    file_put_contents($log_file, "[$timestamp] $message\n", FILE_APPEND);
}

// ==========================================
// 4. פונקציות שליחת הודעות וצינתוקים דרך API ימות המשיח
// ==========================================

// שליחת הודעה קולית (עבור שיחת קוד האימות)
function trigger_yemot_send_tts($phone, $message) {
    if (YEMOT_TOKEN === 'YOUR_YEMOT_SYSTEM_TOKEN_HERE') {
        write_to_log("סימולציה: נשלחה שיחת TTS לטלפון $phone עם התוכן: '$message' (לא מוגדר Token)");
        return false;
    }
    $url = "https://www.call2all.co.il/ym/api/SendTTS?" . http_build_query([
        'token' => YEMOT_TOKEN,
        'callerId' => YEMOT_CALLER_ID,
        'phones' => $phone,
        'ttsMessage' => $message
    ]);
    $response = @file_get_contents($url);
    write_to_log("שליחת TTS ל-$phone. תגובת שרת: " . ($response ?: 'נכשל'));
    return $response;
}

// הפעלת צינתוק לרשימת תפוצה
function trigger_yemot_tzintuk($phone_list) {
    if (YEMOT_TOKEN === 'YOUR_YEMOT_SYSTEM_TOKEN_HERE') {
        write_to_log("סימולציה: נשלח צינתוק לרשימה $phone_list (לא מוגדר Token)");
        return false;
    }
    $url = "https://www.call2all.co.il/ym/api/RunTzintuk?" . http_build_query([
        'token' => YEMOT_TOKEN,
        'callerId' => YEMOT_CALLER_ID,
        'phones' => "tzl:" . $phone_list
    ]);
    $response = @file_get_contents($url);
    write_to_log("שליחת צינתוק לרשימה $phone_list. תגובת שרת: " . ($response ?: 'נכשל'));
    return $response;
}

// ==========================================
// 5. תהליך הטיפול בבקשה (Main Routing)
// ==========================================

// קבלת הפרמטרים מימות המשיח (תומך ב-GET או POST)
$params = array_merge($_GET, $_POST);

$ApiCallId = isset($params['ApiCallId']) ? $params['ApiCallId'] : null;
$ApiExtension = isset($params['ApiExtension']) ? $params['ApiExtension'] : null;
$ApiPhone = isset($params['ApiPhone']) ? $params['ApiPhone'] : null;

if (!$ApiCallId) {
    echo "ממשק פעיל עבור שרת API של ימות המשיח בלבד.";
    exit;
}

// ניקוי הסשן במקרה של ניתוק המאזין
if (isset($params['hangup']) && $params['hangup'] === 'yes') {
    $session = new SessionManager($ApiCallId);
    $session->destroy();
    exit;
}

// טעינת מסד הנתונים והסשן הנוכחי
$db = new AccountsDb(__DIR__ . '/storage/accounts.json');
$session = new SessionManager($ApiCallId);

$logged_in_user = $session->get('logged_in_user');

// שלב א': אימות וכניסת משתמש (Login)
if (!$logged_in_user) {
    $step = $session->get('step');

    if ($step === 'start') {
        $session->set('step', 'login_user');
        echo "read=t-שלום. אנא הקישו את שם המשתמש שלכם ולסיום סולמית=username,yes,1,10,7,Digits";
        exit;
    }

    if ($step === 'login_user') {
        $username = isset($params['username']) ? trim($params['username']) : '';
        if ($username === '') {
            echo "read=t-אנא הקישו שם משתמש תקין=username,yes,1,10,7,Digits";
            exit;
        }
        $session->set('temp_user', $username);
        $session->set('step', 'login_pass');
        echo "read=t-אנא הקישו את הסיסמה שלכם ולסיום סולמית=password,yes,1,10,7,Digits";
        exit;
    }

    if ($step === 'login_pass') {
        $password = isset($params['password']) ? trim($params['password']) : '';
        $temp_user = $session->get('temp_user');

        $account = $db->get($temp_user);
        if ($account && $account['password'] === $password) {
            $session->set('logged_in_user', $temp_user);
            $session->set('step', 'main_start');
            $logged_in_user = $temp_user;
        } else {
            $session->set('step', 'login_user');
            echo "id_list_message=t-שם משתמש או סיסמה שגויים. &";
            echo "read=t-אנא הקישו שוב את שם המשתמש שלכם ולסיום סולמית=username,yes,1,10,7,Digits";
            exit;
        }
    }
}

// זיהוי השלוחה הנוכחית
$is_extension_1 = (strpos($ApiExtension, '1/') === 0 || $ApiExtension === '1');
$is_extension_2 = ($ApiExtension === '2' || strpos($ApiExtension, '2/') === 0);

// ==========================================
// שלוחה 1: העברת תשלום לעסק מוגדר מראש
// ==========================================
if ($is_extension_1) {
    if (!isset($business_config[$ApiExtension])) {
        echo "id_list_message=t-שלוחה זו אינה מוגדרת במערכת. &";
        exit;
    }

    $business = $business_config[$ApiExtension];
    $business_id = $business['username'];
    $business_name = $business['name'];

    $step = $session->get('step');

    if ($step === 'main_start' || $step === 'start') {
        $session->set('step', 'get_amount');
        echo "read=t-הקש את הסכום לחיוב ולסיום סולמית=amount,yes,1,10,7,Digits";
        exit;
    }

    if ($step === 'get_amount') {
        $amount = isset($params['amount']) ? (int)$params['amount'] : 0;
        
        if ($amount <= 0) {
            echo "read=t-סכום לא תקין. אנא הקש סכום אחר או 0 ליציאה=amount,yes,1,10,7,Digits";
            exit;
        }

        $user_data = $db->get($logged_in_user);
        if ($user_data['balance'] < $amount) {
            $current_balance = $user_data['balance'];
            echo "id_list_message=t-לא ניתן לבצע את העברה בסכום זה. היתרה הנוכחית שלך היא {$current_balance} שקלים. &";
            echo "read=t-אנא הקישו סכום אחר או אפס ליציאה=amount,yes,1,10,7,Digits";
            exit;
        }

        $session->set('amount', $amount);
        $session->set('step', 'confirm_payment');
        echo "read=t-הינך מבקש להעביר סכום של {$amount} שקלים ל{$business_name}. לאישור הקש 1 לביטול הקש 2=confirmation,yes,1,1,7,Digits";
        exit;
    }

    if ($step === 'confirm_payment') {
        $confirmation = isset($params['confirmation']) ? $params['confirmation'] : '';

        if ($confirmation === '2') {
            $session->destroy();
            echo "id_list_message=t-הפעולה בוטלה. &";
            exit;
        }

        if ($confirmation === '1') {
            $amount = $session->get('amount');
            $user_data = $db->get($logged_in_user);

            // בדיקה האם מוגדרת שיחת אימות לחיוב מסכום זה
            $needs_verification = (
                isset($user_data['verification_active']) && 
                $user_data['verification_active'] === true && 
                $amount >= $user_data['verification_min_amount']
            );

            if ($needs_verification) {
                $code = rand(1000, 9999);
                $session->set('verification_code', $code);
                $session->set('step', 'verify_code');
                
                $phone_to_call = isset($user_data['phone']) ? $user_data['phone'] : $ApiPhone;
                // פיצול הקוד עם רווחים כדי שהמערכת תקריא אותו כספרות בודדות
                $readable_code = implode(' ', str_split($code));
                trigger_yemot_send_tts($phone_to_call, "שלום, קוד האימות שלך הוא " . $readable_code);

                echo "read=t-כעת נשלחה אליכם שיחת אימות. אנא הקישו את ארבע הספרות של הקוד שקיבלתם ולסיום סולמית=verify_code_input,yes,4,4,10,Digits";
                exit;
            } else {
                execute_transfer($logged_in_user, $business_id, $amount, $db, $session);
                exit;
            }
        }

        $amount = $session->get('amount');
        echo "read=t-מקש שגוי. הינך מבקש להעביר סכום של {$amount} שקלים ל{$business_name}. לאישור הקש 1 לביטול הקש 2=confirmation,yes,1,1,7,Digits";
        exit;
    }

    if ($step === 'verify_code') {
        $user_code = isset($params['verify_code_input']) ? $params['verify_code_input'] : '';
        $correct_code = $session->get('verification_code');

        if ($user_code == $correct_code) {
            $amount = $session->get('amount');
            execute_transfer($logged_in_user, $business_id, $amount, $db, $session);
            exit;
        } else {
            echo "id_list_message=t-קוד האימות שגוי. &";
            echo "read=t-אנא הקישו את הקוד שוב ולסיום סולמית=verify_code_input,yes,4,4,10,Digits";
            exit;
        }
    }
}

// ==========================================
// שלוחה 2: העברה למשתמש מוגדר ע"י המאזין
// ==========================================
elseif ($is_extension_2) {
    $step = $session->get('step');

    if ($step === 'main_start' || $step === 'start') {
        $session->set('step', 'get_recipient');
        echo "read=t-הקש את שם המשתמש אליו הינך רוצה להעביר את הסכום המבוקש ולסיום סולמית=recipient,yes,1,10,7,Digits";
        exit;
    }

    if ($step === 'get_recipient') {
        $recipient = isset($params['recipient']) ? trim($params['recipient']) : '';

        if ($recipient === '') {
            echo "read=t-אנא הקש שם משתמש תקין=recipient,yes,1,10,7,Digits";
            exit;
        }

        if (!$db->exists($recipient)) {
            echo "id_list_message=t-שם המשתמש אליו ביקשת להעביר אינו קיים במערכת. &";
            echo "read=t-אנא הקש שם משתמש אחר, או 0 ליציאה=recipient,yes,1,10,7,Digits";
            exit;
        }

        $session->set('recipient', $recipient);
        $session->set('step', 'get_amount_transfer');
        echo "read=t-אנא הקש את הסכום להעברה ולסיום סולמית=amount,yes,1,10,7,Digits";
        exit;
    }

    if ($step === 'get_amount_transfer') {
        $amount = isset($params['amount']) ? (int)$params['amount'] : 0;

        if ($amount <= 0) {
            echo "read=t-סכום לא תקין. אנא הקש סכום אחר או 0 ליציאה=amount,yes,1,10,7,Digits";
            exit;
        }

        $user_data = $db->get($logged_in_user);
        if ($user_data['balance'] < $amount) {
            $current_balance = $user_data['balance'];
            echo "id_list_message=t-לא ניתן לבצע את העברה בסכום זה. היתרה הנוכחית שלך היא {$current_balance} שקלים. &";
            echo "read=t-אנא הקישו סכום אחר או אפס ליציאה=amount,yes,1,10,7,Digits";
            exit;
        }

        $session->set('amount', $amount);
        $session->set('step', 'confirm_transfer');
        $recipient = $session->get('recipient');
        echo "read=t-הינך מבקש להעביר סכום של {$amount} שקלים למשתמש {$recipient}. לאישור הקש 1 לביטול הקש 2=confirmation,yes,1,1,7,Digits";
        exit;
    }

    if ($step === 'confirm_transfer') {
        $confirmation = isset($params['confirmation']) ? $params['confirmation'] : '';

        if ($confirmation === '2') {
            $session->destroy();
            echo "id_list_message=t-העברה בוטלה. &";
            exit;
        }

        if ($confirmation === '1') {
            $amount = $session->get('amount');
            $recipient = $session->get('recipient');
            $user_data = $db->get($logged_in_user);

            // בדיקת שיחת אימות
            $needs_verification = (
                isset($user_data['verification_active']) && 
                $user_data['verification_active'] === true && 
                $amount >= $user_data['verification_min_amount']
            );

            if ($needs_verification) {
                $code = rand(1000, 9999);
                $session->set('verification_code', $code);
                $session->set('step', 'verify_code_transfer');
                
                $phone_to_call = isset($user_data['phone']) ? $user_data['phone'] : $ApiPhone;
                $readable_code = implode(' ', str_split($code));
                trigger_yemot_send_tts($phone_to_call, "שלום, קוד האימות שלך עבור ההעברה הוא " . $readable_code);

                echo "read=t-כעת נשלחה אליכם שיחת אימות. אנא הקישו את ארבע הספרות של הקוד שקיבלתם ולסיום סולמית=verify_code_input,yes,4,4,10,Digits";
                exit;
            } else {
                execute_transfer($logged_in_user, $recipient, $amount, $db, $session);
                exit;
            }
        }

        $amount = $session->get('amount');
        $recipient = $session->get('recipient');
        echo "read=t-מקש שגוי. הינך מבקש להעביר סכום של {$amount} שקלים למשתמש {$recipient}. לאישור הקש 1 לביטול הקש 2=confirmation,yes,1,1,7,Digits";
        exit;
    }

    if ($step === 'verify_code_transfer') {
        $user_code = isset($params['verify_code_input']) ? $params['verify_code_input'] : '';
        $correct_code = $session->get('verification_code');
        $recipient = $session->get('recipient');

        if ($user_code == $correct_code) {
            $amount = $session->get('amount');
            execute_transfer($logged_in_user, $recipient, $amount, $db, $session);
            exit;
        } else {
            echo "id_list_message=t-קוד האימות שגוי. &";
            echo "read=t-אנא הקישו את הקוד שוב ולסיום סולמית=verify_code_input,yes,4,4,10,Digits";
            exit;
        }
    }
}

// ==========================================
// 6. ביצוע העברה בפועל (מחייב עדכון בבסיס הנתונים ורשימת לוג)
// ==========================================
function execute_transfer($from_user, $to_user, $amount, $db, $session) {
    $sender = $db->get($from_user);
    $recipient = $db->get($to_user);

    if (!$sender || !$recipient) {
        echo "id_list_message=t-שגיאה בביצוע ההעברה, אחד החשבונות לא נמצא במערכת. &";
        $session->destroy();
        exit;
    }

    $new_sender_balance = $sender['balance'] - $amount;
    $new_recipient_balance = $recipient['balance'] + $amount;

    // עדכון היתרות בקובץ ה-JSON
    $db->updateBalance($from_user, $new_sender_balance);
    $db->updateBalance($to_user, $new_recipient_balance);

    // כתיבה לקובץ הלוג
    $log_msg = "User '$from_user' transferred $amount ILS to user '$to_user'. ";
    $log_msg .= "New Balances -> $from_user: $new_sender_balance, $to_user: $new_recipient_balance";
    write_to_log($log_msg);

    // פלט חוזר למערכת הטלפונית להקראת היתרה החדשה
    echo "id_list_message=t-ההעברה בוצעה בהצלחה. היתרה החדשה שלך היא {$new_sender_balance} שקלים. &";

    // בדיקת הגדרת צינתוק בסיום פעולה (צינתוק בעת ביצוע פעולה)
    $tzintuk_active = isset($sender['tzintuk_on_action']) && $sender['tzintuk_on_action'] === true;
    $meets_tzintuk_threshold = isset($sender['tzintuk_min_amount']) && $amount >= $sender['tzintuk_min_amount'];

    if ($tzintuk_active && $meets_tzintuk_threshold) {
        $tzintuk_phone = isset($sender['phone']) ? $sender['phone'] : '';
        if ($tzintuk_phone !== '') {
            // הצינתוק יישלח לרשימת הצינתוקים ששמה הוא מספר הטלפון המוגדר
            trigger_yemot_tzintuk($tzintuk_phone);
        }
    }

    // סגירת השיחה וניקוי קובץ הסשן הזמני
    $session->destroy();
    exit;
}
