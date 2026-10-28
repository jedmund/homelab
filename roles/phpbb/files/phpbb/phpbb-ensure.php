<?php
/**
 * Reconciles board email settings stored in the config table with the
 * environment the stack is deployed with. Best-effort: any failure only
 * logs and exits 0 so the container still starts.
 */

$root = '/var/www/html';
$configFile = $root . '/config.php';

if (!is_file($configFile) || !filesize($configFile)) {
    exit(0);
}

require $configFile;

$emailEnabled = (getenv('PHPBB_EMAIL_ENABLED') ?: 'true') === 'true';

$desired = [
    'board_email' => getenv('PHPBB_BOARD_EMAIL') ?: '',
];

if ($emailEnabled) {
    $desired += [
        'smtp_delivery'    => ((getenv('PHPBB_SMTP_DELIVERY') ?: 'true') === 'true') ? '1' : '0',
        'smtp_host'        => getenv('PHPBB_SMTP_HOST') ?: '',
        'smtp_port'        => getenv('PHPBB_SMTP_PORT') ?: '',
        'smtp_auth_method' => getenv('PHPBB_SMTP_AUTH_METHOD') ?: '',
        'smtp_username'    => getenv('PHPBB_SMTP_USERNAME') ?: '',
        'smtp_password'    => getenv('PHPBB_SMTP_PASSWORD') ?: '',
    ];
}

$connection = @mysqli_connect(
    $dbhost,
    $dbuser,
    $dbpasswd,
    $dbname,
    $dbport ? (int) $dbport : 3306
);

if (!$connection) {
    fwrite(STDERR, "phpbb-ensure: database not reachable\n");
    exit(0);
}

$prefix = $table_prefix . 'config';

$current = [];
$result = @mysqli_query(
    $connection,
    'SELECT config_name, config_value FROM ' . $prefix .
    ' WHERE config_name IN ("' . implode('", "', array_keys($desired)) . '")'
);

if (!$result) {
    // The config table does not exist yet (board not installed).
    mysqli_close($connection);
    exit(0);
}

while ($row = mysqli_fetch_assoc($result)) {
    $current[$row['config_name']] = $row['config_value'];
}
mysqli_free_result($result);

$changed = [];
$statement = mysqli_stmt_init($connection);
$update = 'UPDATE ' . $prefix . ' SET config_value = ? WHERE config_name = ?';

foreach ($desired as $name => $value) {
    if (!array_key_exists($name, $current) || (string) $current[$name] !== (string) $value) {
        if (!mysqli_stmt_prepare($statement, $update)) {
            fwrite(STDERR, "phpbb-ensure: update prepare failed\n");
            break;
        }
        mysqli_stmt_bind_param($statement, 'ss', $value, $name);
        if (mysqli_stmt_execute($statement)) {
            $changed[] = $name;
        } else {
            fwrite(STDERR, "phpbb-ensure: update failed for {$name}\n");
        }
    }
}
mysqli_stmt_close($statement);
mysqli_close($connection);

if ($changed) {
    // phpBB caches the config table; drop the data cache so the new values
    // are read on the next request.
    foreach (glob($root . '/cache/data_*.php') ?: [] as $cacheFile) {
        @unlink($cacheFile);
    }
    fwrite(STDERR, 'phpbb-ensure: updated ' . implode(', ', $changed) . "\n");
}

exit(0);
