<?php
// הגדרת ראש כותרת תקין
header('Content-Type: text/plain; charset=utf-8');

// קבלת פרמטרים
$step = isset($_REQUEST['step']) ? $_REQUEST['step'] : 'menu';
$read = isset($_REQUEST['value']) ? $_REQUEST['value'] : ''; // שינוי ל-value כפי שרוב המערכות שולחות

switch ($step) {
    
    case 'menu':
        // שימוש ב-id_list_message להשמעה
        echo "id_list_message=t-שלום, הגעת לבנק הוירטואלי. להעברת כסף הקש 1" . PHP_EOL;
        // read תקין
        echo "read=fld=action|num=1|min=1|max=1" . PHP_EOL;
        // הכתובת אליה המערכת תשלח את הנתונים לאחר ההקשה
        echo "go_to=ivr.php?step=check_action" . PHP_EOL;
        break;

    case 'check_action':
        if ($read == '1') {
            echo "id_list_message=t-אנא הקש את מספר הטלפון של המשתמש אליו תרצה להעביר את הכסף" . PHP_EOL;
            echo "read=fld=target_phone|min=8|max=10" . PHP_EOL;
            echo "go_to=ivr.php?step=ask_amount" . PHP_EOL;
        } else {
            echo "id_list_message=t-לא נבחרה אפשרות תקינה" . PHP_EOL;
            echo "go_to=ivr.php?step=menu" . PHP_EOL;
        }
        break;

    case 'ask_amount':
        // כאן ה-read הוא מספר הטלפון שהוקש
        $target_phone = $read;
        echo "id_list_message=t-אנא הקש את הסכום להעברה" . PHP_EOL;
        echo "read=fld=amount|min=1|max=10" . PHP_EOL;
        echo "go_to=ivr.php?step=finish&target_phone=$target_phone" . PHP_EOL;
        break;

    case 'finish':
        $amount = $read;
        $target_phone = isset($_GET['target_phone']) ? $_GET['target_phone'] : '';
        
        echo "id_list_message=t-הסכום $amount שקלים הועבר בהצלחה למספר $target_phone" . PHP_EOL;
        echo "hangup=yes" . PHP_EOL;
        break;
}
?>
