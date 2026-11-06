<?php
/**
 * Liveness endpoint for the container health checks: proves nginx and
 * PHP-FPM are serving, and, once the board is installed, that the database
 * connection works. Carries no board state or credentials.
 */

echo "ok\n";

$root = '/var/www/html';
$configFile = $root . '/config.php';

if (is_file($configFile) && filesize($configFile)) {
    require $configFile;

    $connection = @mysqli_connect(
        $dbhost,
        $dbuser,
        $dbpasswd,
        $dbname,
        $dbport ? (int) $dbport : 3306
    );

    echo $connection ? "db ok\n" : "db unavailable\n";

    if ($connection) {
        mysqli_close($connection);
    }
}
