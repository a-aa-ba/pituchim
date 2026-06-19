<?php
// הגדרת משתני ה-API
$token = "0775311511:124578";
$apiUrl = "https://www.call2all.co.il/ym/api/";

// פונקציה לשליחת בקשה ל-API
function callYemotApi($command, $params = []) {
    global $apiUrl, $token;
    $params['token'] = $token;
    $url = $apiUrl . $command . '?' . http_build_query($params);
    $response = file_get_contents($url);
    return json_decode($response, true);
}

// קבלת נתונים מהבקשה (למשל מהטלפון)
$fromId = $_GET['from_id']; // המשתמש המעביר
$toId = $_GET['to_id'];     // המשתמש המקבל
$amount = (int)$_GET['amount']; // כמות הנקודות

if ($amount <= 0) {
    die("סכום לא תקין");
}

// בדיקת יתרה (בדוגמה זו נשתמש ב-points_edit לבדיקה או במודול קיים)
// בימות המשיח, ניתן לבצע העברה ישירה באמצעות המודול points_to_other_id אם זמין
// או בשיטה של הפחתה מהאחד והוספה לשני:

// 1. הפחתה מהמשתמש המעביר
$sub = callYemotApi("points_edit", [
    "id" => $fromId,
    "amount" => -$amount,
    "reason" => "Transfer to $toId"
]);

if ($sub['responseStatus'] == 'OK') {
    // 2. הוספה למשתמש המקבל
    $add = callYemotApi("points_edit", [
        "id" => $toId,
        "amount" => $amount,
        "reason" => "Transfer from $fromId"
    ]);

    if ($add['responseStatus'] == 'OK') {
        echo "ההעברה בוצעה בהצלחה!";
    } else {
        // אם ההוספה נכשלה, נחזיר את הנקודות למעביר
        callYemotApi("points_edit", ["id" => $fromId, "amount" => $amount]);
        echo "שגיאה בהוספת נקודות למקבל";
    }
} else {
    echo "שגיאה: יתרה לא מספיקה או משתמש לא קיים";
}
?>
