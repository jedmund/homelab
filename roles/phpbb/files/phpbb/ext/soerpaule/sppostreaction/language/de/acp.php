<?php
/**
 *
 * SP Post Reactions extension for phpBB.
 *
 * @copyright (c) 2026 soerpaule
 * @license GNU General Public License, version 2 (GPL-2.0)
 *
 */

if (!defined('IN_PHPBB'))
{
	exit;
}

$lang = array_merge($lang, [
	'ACP_TFPR_TITLE' => 'SP Post Reactions',
	'ACP_TFPR_SYMBOLSETS' => 'Symbolsets',
	'ACP_TFPR_EXPLAIN' => 'Lege fest, welche Symbolsets deine Benutzer im Persönlichen Bereich auswählen dürfen. Deaktivierte Sets werden im UCP ausgeblendet. TF Chrom bleibt als sicherer Fallback immer verfügbar.',
	'ACP_TFPR_AVAILABLE_SETS' => 'Verfügbare Symbolsets',
	'ACP_TFPR_ACTIVE' => 'Freigegeben',
	'ACP_TFPR_DEFAULT' => 'Standard',
	'ACP_TFPR_PREVIEW' => 'Vorschau',
	'ACP_TFPR_SET_NAME' => 'Symbolsatz und Beschreibung',
	'ACP_TFPR_STANDARD_ALWAYS' => 'TF Chrom ist als sicherer Fallback immer freigegeben.',
	'ACP_TFPR_DEFAULT_EXPLAIN' => 'Der gewählte Standardsatz wird verwendet, wenn ein Benutzer noch keine eigene Auswahl getroffen hat oder sein bisheriger Satz nicht mehr freigegeben ist.',
	'ACP_TFPR_SAVED' => 'Die Symbolsatz-Einstellungen wurden gespeichert.',
	'ACP_TFPR_DESC_TF-CHROM' => 'TF Chrom: glänzende Chromoptik mit Spiegelungen.',
	'ACP_TFPR_DESC_TF-CHERRY' => 'TF Cherry: kirschrote Hochglanzoptik mit Spiegelungen.',
	'ACP_TFPR_DESC_TF-ICE-BLUE' => 'TF Ice Blue: eisblaue Optik mit kühlen Spiegelungen.',
	'ACP_TFPR_DESC_TF-SILVER-NEW' => 'TF Silver New: helle Silberoptik mit plastischer Metallwirkung.',

	'ACP_TFPR_UPLOAD_TITLE' => 'Neuen Symbolsatz installieren',
	'ACP_TFPR_UPLOAD_EXPLAIN' => 'Lade ein ZIP-Archiv mit den acht PNG-Dateien thanks.png, like.png, dislike.png, laugh.png, smile.png, surprise.png, doubt.png und hug.png hoch. Eine optionale icon.json kann Name, Autor, Version und Beschreibung enthalten.',
	'ACP_TFPR_UPLOAD_BUTTON' => 'Hochladen und installieren',
	'ACP_TFPR_UPLOAD_SUCCESS' => 'Der Symbolsatz „%s“ wurde installiert und ist zunächst nicht freigegeben.',
	'ACP_TFPR_UPLOAD_INVALID' => 'Das hochgeladene Archiv ist kein gültiger Symbolsatz.',
	'ACP_TFPR_UPLOAD_MISSING' => 'Im Archiv fehlen erforderliche PNG-Dateien: %s',
	'ACP_TFPR_UPLOAD_EXISTS' => 'Ein Symbolsatz mit diesem Verzeichnisnamen existiert bereits.',
	'ACP_TFPR_UPLOAD_ZIP_UNAVAILABLE' => 'Die PHP-Erweiterung ZipArchive ist auf dem Server nicht verfügbar.',
	'ACP_TFPR_UPLOAD_TOO_LARGE' => 'Das ZIP-Archiv oder eine enthaltene Datei ist zu groß.',
	'ACP_TFPR_AUTHOR' => 'Autor',
	'ACP_TFPR_VERSION' => 'Version',
	'ACP_TFPR_TYPE' => 'Typ',
	'ACP_TFPR_SYSTEM_SET' => 'Systemset',
	'ACP_TFPR_CUSTOM_SET' => 'Hochgeladen',
	'ACP_TFPR_ACTIONS' => 'Aktionen',
	'ACP_TFPR_DELETE' => 'Löschen',
	'ACP_TFPR_DELETE_CONFIRM' => 'Soll der Symbolsatz „%s“ wirklich vollständig gelöscht werden?',
	'ACP_TFPR_DELETE_SUCCESS' => 'Der Symbolsatz „%s“ wurde gelöscht.',
	'ACP_TFPR_DELETE_FORBIDDEN' => 'Systemsets können nicht gelöscht werden.',
	'ACP_TFPR_NO_FILE' => 'Bitte wähle zuerst ein ZIP-Archiv aus.',
]);
