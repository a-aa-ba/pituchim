<?php
// נבטל הצגת שגיאות למסך כדי לא לשבש את התקשורת עם ימות המשיח
error_reporting(0);

// נבדוק מה ימות המשיח שלחה לנו
$action = $_REQUEST['action'] ?? 'start';

// תשובה פשוטה לימות המשיח
if ($action == 'start') {
    // נבקש מהמאזין סכום ונשלח חזרה לשרת תחת השם "sum"
    echo "read=t-הקישו את הסכום הרצוי, בסיום הקישו סולמית=sum";
} 
elseif (isset($_REQUEST['sum'])) {
    // אם קיבלנו סכום, נגיד לו תודה
    echo "id_list_message=t-קיבלתי את הסכום " . $_REQUEST['sum'] . ", תודה רבה.";
}
else {
    // למקרה שאין לנו מושג מה קרה
    echo "id_list_message=t-אירעה שגיאה";
}
?>
