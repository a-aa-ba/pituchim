<?php
header('Content-Type: text/plain; charset=utf-8');

$db_url = getenv('DATABASE_URL');
$pdo = new PDO($db_url);

// בדיקה אם המשתמש כבר שלח קלט
$user_input = $_REQUEST['user_input'] ?? '';

// אם אין עדיין שם משתמש, נבקש אותו
if (empty($_REQUEST['user_id'])) {
    echo "read=t-שלום, אנא הקישו קוד משתמש בן 4 ספרות=user_id,no,4,4,7,Digits,yes,no,*/";
} else {
    // כאן נמשיך את הלוגיקה של בדיקת הסיסמה והעברות כספים...
    echo "id_list_message=t-קיבלתי את הקוד " . $_REQUEST['user_id'];
}
?>
