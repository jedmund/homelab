<?php
/**
 * Reconciles board settings stored in the database with the environment the
 * stack is deployed with. Best-effort: any failure only logs and exits 0 so
 * the container still starts.
 *
 * Sections:
 * - board email settings (contact address, SMTP)
 * - managed style registration, board default style, and user migration
 */

$root = '/var/www/html';
$configFile = $root . '/config.php';

$changed = false;

if (!is_file($configFile) || !filesize($configFile)) {
    exit(0);
}

require $configFile;

$emailEnabled = (getenv('PHPBB_EMAIL_ENABLED') ?: 'true') === 'true';

$desired = [
    'board_email' => getenv('PHPBB_BOARD_EMAIL') ?: '',
    // The visible From header on outgoing mail. phpBB keeps this separate
    // from board_email (the envelope); Resend rejects From domains outside
    // the API key's scope, so both must track PHPBB_BOARD_EMAIL.
    'board_contact' => getenv('PHPBB_BOARD_EMAIL') ?: '',
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

$configTable = $table_prefix . 'config';

/**
 * Reads one config value, or null when it is absent.
 */
function config_value(mysqli $connection, string $table, string $name): ?string
{
    $result = @mysqli_query(
        $connection,
        'SELECT config_value FROM ' . $table . ' WHERE config_name = "' .
        mysqli_real_escape_string($connection, $name) . '"'
    );

    if (!$result) {
        return null;
    }

    $row = mysqli_fetch_row($result);
    mysqli_free_result($result);

    return $row === null ? null : (string) $row[0];
}

/**
 * Writes one config value.
 */
function set_config_value(mysqli $connection, string $table, string $name, string $value): void
{
    $nameSql = mysqli_real_escape_string($connection, $name);
    $valueSql = mysqli_real_escape_string($connection, $value);
    mysqli_query(
        $connection,
        'UPDATE ' . $table . " SET config_value = '{$valueSql}' WHERE config_name = '{$nameSql}'"
    );
}

// --- board email settings -------------------------------------------------

$current = [];
$result = @mysqli_query(
    $connection,
    'SELECT config_name, config_value FROM ' . $configTable .
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

$statement = mysqli_stmt_init($connection);
$update = 'UPDATE ' . $configTable . ' SET config_value = ? WHERE config_name = ?';

// Prepare once, before the loop; an unprepared statement must never reach
// mysqli_stmt_close (PHP 8.4 throws on close of an uninitialized stmt).
if (!mysqli_stmt_prepare($statement, $update)) {
    fwrite(STDERR, "phpbb-ensure: update prepare failed\n");
    mysqli_stmt_close($statement);
    $statement = null;
}

if ($statement) {
    foreach ($desired as $name => $value) {
        if (!array_key_exists($name, $current) || (string) $current[$name] !== (string) $value) {
            mysqli_stmt_bind_param($statement, 'ss', $value, $name);
            if (mysqli_stmt_execute($statement)) {
                $changed = true;
                fwrite(STDERR, "phpbb-ensure: updated {$name}\n");
            } else {
                fwrite(STDERR, "phpbb-ensure: update failed for {$name}\n");
            }
        }
    }
    mysqli_stmt_close($statement);
}

// --- managed style registration -------------------------------------------

$stylePath = getenv('PHPBB_STYLE_PATH') ?: '';

if ($stylePath !== '') {
    $styleName = getenv('PHPBB_STYLE_NAME') ?: $stylePath;
    $styleCopyright = getenv('PHPBB_STYLE_COPYRIGHT') ?: '';
    $stylesTable = $table_prefix . 'styles';
    $usersTable = $table_prefix . 'users';

    $pathSql = mysqli_real_escape_string($connection, $stylePath);
    $result = mysqli_query(
        $connection,
        "SELECT style_id FROM {$stylesTable} WHERE style_path = '{$pathSql}'"
    );
    $styleId = 0;

    if ($result && ($row = mysqli_fetch_row($result))) {
        $styleId = (int) $row[0];
        mysqli_free_result($result);
    }

    if (!$styleId) {
        // Register the style as a child of prosilver, borrowing the parent's
        // template bitfield the way the ACP's install step does.
        $parent = mysqli_query(
            $connection,
            "SELECT style_id, bbcode_bitfield FROM {$stylesTable} WHERE style_path = 'prosilver'"
        );

        if ($parent && ($row = mysqli_fetch_assoc($parent))) {
            $parentId = (int) $row['style_id'];
            $bitfield = mysqli_real_escape_string($connection, $row['bbcode_bitfield']);
            $nameSql = mysqli_real_escape_string($connection, $styleName);
            $copyrightSql = mysqli_real_escape_string($connection, $styleCopyright);
            mysqli_query(
                $connection,
                "INSERT INTO {$stylesTable}
                    (style_name, style_copyright, style_active, style_path,
                     bbcode_bitfield, style_parent_id, style_parent_tree)
                 VALUES ('{$nameSql}', '{$copyrightSql}', 1, '{$pathSql}',
                         '{$bitfield}', {$parentId}, 'prosilver')"
            );
            $styleId = (int) mysqli_insert_id($connection);
            if ($styleId) {
                $changed = true;
                fwrite(STDERR, "phpbb-ensure: registered style {$stylePath} (id {$styleId})\n");
            }
        } else {
            fwrite(STDERR, "phpbb-ensure: prosilver not found; style not registered\n");
        }
        if (isset($parent) && $parent instanceof mysqli_result) {
            mysqli_free_result($parent);
        }
    }

    if ($styleId && (getenv('PHPBB_STYLE_SET_DEFAULT') ?: 'true') === 'true') {
        $currentDefault = config_value($connection, $configTable, 'default_style');

        if ($currentDefault === null || (int) $currentDefault !== $styleId) {
            $previous = (int) $currentDefault;
            set_config_value($connection, $configTable, 'default_style', (string) $styleId);
            $changed = true;
            fwrite(STDERR, "phpbb-ensure: default style is now {$stylePath} (id {$styleId})\n");

            // Migrate users who were following the previous board default.
            if ($previous && $previous !== $styleId) {
                mysqli_query(
                    $connection,
                    "UPDATE {$usersTable} SET user_style = {$styleId} WHERE user_style = {$previous}"
                );
            }

            // The ACP purges the compiled template cache when a style
            // changes; a direct registration must do the same or stale
            // templates render without the new style's template events.
            // Twig files live in two hash-bucket levels under twig/.
            foreach (glob($root . '/cache/production/twig/*', GLOB_ONLYDIR) ?: [] as $twigBucket) {
                foreach (glob($twigBucket . '/*.php') ?: [] as $twigFile) {
                    @unlink($twigFile);
                }
            }
        }
    }
}

mysqli_close($connection);

if ($changed) {
    // phpBB caches config and style data in cache/production/; drop the data
    // cache so the new values are read on the next request.
    foreach (glob($root . '/cache/production/data_*.php') ?: [] as $cacheFile) {
        @unlink($cacheFile);
    }
    fwrite(STDERR, "phpbb-ensure: board settings reconciled\n");
}

exit(0);
