<?php
// הגדרת קידוד
header('Content-Type: text/plain; charset=utf-8');

// קבלת נתונים מהשרת
$phone = isset($_GET['Phone']) ? $_GET['Phone'] : '';
$read = isset($_GET['read']) ? $_GET['read'] : '';
$step = isset($_GET['step']) ? $_GET['step'] : 'menu'; // ניהול שלבים

// לוגיקה של ניהול השיחה
switch ($step) {
    
    // תפריט ראשי
    case 'menu':
        echo "id_list_message=t-שלום, הגעת לבנק הוירטואלי. להעברת כסף הקש 1\n";
        echo "read=fld=action|num=1|min=1|max=1\n";
        echo "go_to=ivr.php?step=check_action\n";
        break;

    // בדיקת בחירת המשתמש
    case 'check_action':
        if ($read == '1') {
            echo "id_list_message=t-אנא הקש את מספר הטלפון של המשתמש אליו תרצה להעביר את הכסף\n";
            echo "read=fld=target_phone|min=8|max=10\n"; // 8 עד 10 ספרות (כולל קידומת)
            echo "go_to=ivr.php?step=ask_amount\n";
        } else {
            echo "id_list_message=t-לא נבחרה אפשרות תקינה\n";
            echo "go_to=ivr.php?step=menu\n";
        }
        break;

    // בקשת סכום
    case 'ask_amount':
        $target_phone = $read; // המספר שהוקש בשלב הקודם נשמר ב-$read
        echo "id_list_message=t-אנא הקש את הסכום להעברה\n";
        echo "read=fld=amount|min=1|max=10\n";
        // מעבירים את מספר היעד הלאה ב-URL
        echo "go_to=ivr.php?step=finish&target_phone=$target_phone\n";
        break;

    // סיום
    case 'finish':
        $amount = $read;
        $target_phone = isset($_GET['target_phone']) ? $_GET['target_phone'] : '';
        
        // כאן תוסיף את הלוגיקה של עדכון מסד הנתונים (SQL)
        // לדוגמה: update_balance($phone, $target_phone, $amount);
        
        echo "id_list_message=t-הסכום $amount שקלים הועבר בהצלחה למספר $target_phone\n";
        echo "hangup=yes\n";
        break;
}
?>
