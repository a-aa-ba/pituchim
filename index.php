<?php
// אין לכתוב שום דבר לפני ה-<?php, ולוודא שהקובץ נשמר ב-UTF-8 ללא BOM

header('Content-Type: text/plain; charset=utf-8');

// קבלת הפרמטרים שימות המשיח שולחים
$step = isset($_REQUEST['step']) ? $_REQUEST['step'] : 'menu';

switch ($step) {
    
    case 'menu':
        // תפריט ראשי
        echo "id_list_message=t-שלום, הגעת לבנק הוירטואלי. להעברת כסף הקש 1" . PHP_EOL;
        echo "read=fld=action|min=1|max=1" . PHP_EOL;
        echo "go_to=ivr.php?step=check_action" . PHP_EOL;
        break;

    case 'check_action':
        // המשתנה שהמשתמש הקיש נשמר ב-action (לפי ה-fld שהגדרנו)
        $action = isset($_REQUEST['action']) ? $_REQUEST['action'] : '';
        
        if ($action == '1') {
            echo "id_list_message=t-אנא הקש את מספר הטלפון של המשתמש אליו תרצה להעביר את הכסף" . PHP_EOL;
            echo "read=fld=target_phone|min=8|max=10" . PHP_EOL;
            echo "go_to=ivr.php?step=ask_amount" . PHP_EOL;
        } else {
            echo "id_list_message=t-לא נבחרה אפשרות תקינה" . PHP_EOL;
            echo "go_to=ivr.php?step=menu" . PHP_EOL;
        }
        break;

    case 'ask_amount':
        // שמירת המספר שהוקש בשלב הקודם
        $target_phone = isset($_REQUEST['target_phone']) ? $_REQUEST['target_phone'] : '';
        
        echo "id_list_message=t-אנא הקש את הסכום להעברה" . PHP_EOL;
        echo "read=fld=amount|min=1|max=10" . PHP_EOL;
        // מעבירים את מספר היעד הלאה ב-URL של ה-go_to
        echo "go_to=ivr.php?step=finish&target_phone=$target_phone" . PHP_EOL;
        break;

    case 'finish':
        $amount = isset($_REQUEST['amount']) ? $_REQUEST['amount'] : '';
        $target_phone = isset($_GET['target_phone']) ? $_GET['target_phone'] : '';
        
        echo "id_list_message=t-הסכום $amount שקלים הועבר בהצלחה למספר $target_phone" . PHP_EOL;
        echo "hangup=yes" . PHP_EOL;
        break;
}
?>
