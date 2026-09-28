<?php

header('Content-Type: text/plain; charset=utf-8');

$apiCallId    = $_REQUEST['ApiCallId'] ?? '';
$apiExtension = $_REQUEST['ApiExtension'] ?? '';
$hangup       = $_REQUEST['hangup'] ?? '';
$what         = $_REQUEST['what'] ?? '';
$skip         = $_REQUEST['skip'] ?? '';

if ($apiCallId === '') {
    exit('Missing ApiCallId');
}

// קובץ זמני לשמירת מיקום הקובץ של השיחה הנוכחית
$sessionFile = __DIR__ . "/session_{$apiCallId}.json";

// ניקוי הנתונים בסיום שיחה
if ($hangup === 'yes') {
    if (file_exists($sessionFile)) {
        unlink($sessionFile);
    }
    exit('hangup_ok');
}

// -------------------------------------------------------------
// שלב 2: המאזין כבר הקיש את כמות הקבצים לדילוג
// -------------------------------------------------------------
if ($skip !== '') {
    if (!file_exists($sessionFile)) {
        exit('Session expired');
    }

    $sessionData = json_decode(file_get_contents($sessionFile), true);
    if (file_exists($sessionFile)) {
        unlink($sessionFile); // מחיקת הקובץ הזמני לאחר שימוש
    }

    $currentFile    = (int)($sessionData['file'] ?? 1);
    $originalLength = (int)($sessionData['length'] ?? 3);
    $extension      = $sessionData['extension'] ?? $apiExtension;

    $skipCount = (int)$skip;

    // חישוב הקובץ החדש (דילוג קדימה)
    $targetNumber = $currentFile + $skipCount;

    // מניעת ירידה מתחת לקובץ 1
    if ($targetNumber < 1) {
        $targetNumber = 1;
    }

    // החזרת האפסים המובילים (לדוגמה: 025)
    $target = str_pad((string)$targetNumber, $originalLength, '0', STR_PAD_LEFT);

    // שליחת פקודה לימות המשיח לקפוץ לקובץ המבוקש
    echo 'go_to_folder_and_play=' . $extension . ',' . $target;
    exit;
}

// -------------------------------------------------------------
// שלב 1: המאזין לחץ על מקש הדילוג -> שואלים כמה לדלג
// -------------------------------------------------------------
if ($what === '' || $apiExtension === '') {
    exit('Missing what or ApiExtension');
}

// חילוץ מספר הקובץ הנוכחי שמושמע
$fileName = basename($what);
$dotPos = strrpos($fileName, '.');
if ($dotPos !== false) {
    $fileName = substr($fileName, 0, $dotPos);
}

if (!ctype_digit($fileName)) {
    exit('Invalid filename in what');
}

// שמירת פרטי השיחה והקובץ הנוכחי
$sessionData = [
    'file'      => (int)$fileName,
    'length'    => strlen($fileName),
    'extension' => $apiExtension
];
file_put_contents($sessionFile, json_encode($sessionData), LOCK_EX);

// הודעה קולית למאזין ב-TTS
$promptText = 'הקישו כמה קבצים ברצונכם לדלג ובסיום סולמית';

// שליחת פקודת קליטת נתונים (read) לימות המשיח
echo "read=t-{$promptText},skip,digits,3,1,7,No,,";
