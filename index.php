<?php
header('Content-Type: text/plain; charset=utf-8');

// קבלת הערך מהמערכת (ימות המשיח שולחים את הקלט בדרך כלל בפרמטר בשם value)
$value = isset($_REQUEST['value']) ? $_REQUEST['value'] : '';
$step = isset($_REQUEST['step']) ? $_REQUEST['step'] : 'menu';

switch ($step) {
    case 'menu':
        echo "id_list_message=t-שלום, הגעת לבנק הוירטואלי. להעברת כסף הקש 1" . PHP_EOL;
        echo "read=fld=action|num=1|min=1|max=1" . PHP_EOL;
        echo "go_to=ivr.php?step=check_action" . PHP_EOL;
        break;

    case 'check_action':
        if ($value == '1') {
            echo "id_list_message=t-אנא הקש את מספר הטלפון של המשתמש אליו תרצה להעביר את הכסף" . PHP_EOL;
            echo "read=fld=target_phone|min=8|max=10" . PHP_EOL;
            echo "go_to=ivr.php?step=ask_amount" . PHP_EOL;
        } else {
            echo "id_list_message=t-לא נבחרה אפשרות תקינה" . PHP_EOL;
            echo "go_to=ivr.php?step=menu" . PHP_EOL;
        }
        break;

    case 'ask_amount':
        $target_phone = $value;
        echo "id_list_message=t-אנא הקש את הסכום להעברה" . PHP_EOL;
        echo "read=fld=amount|min=1|max=10" . PHP_EOL;
        echo "go_to=ivr.php?step=finish&target_phone=$target_phone" . PHP_EOL;
        break;

    case 'finish':
        $amount = $value;
        $target_phone = isset($_REQUEST['target_phone']) ? $_REQUEST['target_phone'] : 'לא ידוע';
        echo "id_list_message=t-הסכום $amount שקלים הועבר בהצלחה למספר $target_phone" . PHP_EOL;
        echo "hangup=yes" . PHP_EOL;
        break;
}
?>
