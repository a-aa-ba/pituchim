<?php
 
header('Content-Type: text/plain; charset=utf-8');
 
$apiCallId = $_REQUEST['ApiCallId'] ?? '';
$apiExtension = $_REQUEST['ApiExtension'] ?? '';
$hangup = $_REQUEST['hangup'] ?? '';
$what = $_REQUEST['what'] ?? '';
 
if ($apiCallId === '') {
    exit('Missing ApiCallId');
}
 
if ($apiExtension === '') {
    exit('Missing ApiExtension');
}
 
if ($hangup === 'yes') {
 
    foreach (glob(__DIR__ . '/counter_*.txt') as $counterFile) {
 
        $counters = json_decode(file_get_contents($counterFile), true);
 
        if (!is_array($counters)) {
            continue;
        }
 
        unset($counters[$apiCallId]);
 
        file_put_contents(
            $counterFile,
            json_encode($counters),
            LOCK_EX
        );
    }
 
    exit('hangup_ok');
}
 
$extensionKey = trim($apiExtension, '/');
$extensionKey = str_replace('/', '_', $extensionKey);
 
if ($extensionKey === '') {
    exit('Invalid ApiExtension');
}
 
$configFile = __DIR__ . "/settings_{$extensionKey}.txt";
$dataFile = __DIR__ . "/counter_{$extensionKey}.txt";
 
if (!file_exists($configFile)) {
    exit('Missing settings file');
}
 
if (!file_exists($dataFile)) {
    file_put_contents(
        $dataFile,
        json_encode([]),
        LOCK_EX
    );
}
 
$counters = json_decode(file_get_contents($dataFile), true);
 
if (!is_array($counters)) {
    $counters = [];
}
 
$steps = [];
$offset = null;
 
foreach (file($configFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
 
    $line = trim($line);
 
    if ($line === '') {
        continue;
    }
 
    if (preg_match('/^offset\s*=\s*(-?\d+)$/i', $line, $match)) {
        $offset = (int)$match[1];
        continue;
    }
 
    if (!str_contains($line, '=')) {
        continue;
    }
 
    [$index, $value] = explode('=', $line, 2);
 
    if (!is_numeric($index)) {
        continue;
    }
 
    $steps[(int)$index] = trim($value);
}
 
if ($offset !== null) {
 
    if ($what === '') {
        exit('Missing what');
    }
 
    $fileName = basename($what);
 
    $dotPos = strrpos($fileName, '.');
 
    if ($dotPos !== false) {
        $fileName = substr($fileName, 0, $dotPos);
    }
 
    if (!ctype_digit($fileName)) {
        exit('Invalid filename in what');
    }
 
    $originalLength = strlen($fileName);
 
    $targetNumber = ((int)$fileName + $offset);
 
    $target = str_pad(
        (string)$targetNumber,
        $originalLength,
        '0',
        STR_PAD_LEFT
    );
 
    echo 'go_to_folder_and_play=' . $apiExtension . ',' . $target;
    exit;
}
 
ksort($steps);
 
if (empty($steps)) {
    exit('No steps configured');
}
 
$currentStep = $counters[$apiCallId] ?? 0;
 
if (isset($steps[$currentStep])) {
    $target = $steps[$currentStep];
} else {
    $target = end($steps);
}
 
$counters[$apiCallId] = $currentStep + 1;
 
file_put_contents(
    $dataFile,
    json_encode($counters),
    LOCK_EX
);
 
echo 'go_to_folder_and_play=' . $apiExtension . ',' . $target;
