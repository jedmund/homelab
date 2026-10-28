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
	'ACP_TFPR_SYMBOLSETS' => 'Icon sets',
	'ACP_TFPR_EXPLAIN' => 'Choose which icon sets users may select in the UCP. Disabled sets are hidden. TF Silver always remains available.',
	'ACP_TFPR_AVAILABLE_SETS' => 'Available icon sets',
	'ACP_TFPR_ACTIVE' => 'Enabled',
	'ACP_TFPR_DEFAULT' => 'Default',
	'ACP_TFPR_PREVIEW' => 'Preview',
	'ACP_TFPR_SET_NAME' => 'Icon set and description',
	'ACP_TFPR_STANDARD_ALWAYS' => 'TF Chrom is always enabled as a safe fallback.',
	'ACP_TFPR_DEFAULT_EXPLAIN' => 'The selected default is used when a user has not made a personal choice or when their previous set is no longer enabled.',
	'ACP_TFPR_SAVED' => 'Icon set settings have been saved.',
	'ACP_TFPR_DESC_TF-CHROM' => 'TF Chrom: polished chrome finish with reflections.',
	'ACP_TFPR_DESC_TF-CHERRY' => 'TF Cherry: glossy cherry-red finish with reflections.',
	'ACP_TFPR_DESC_TF-ICE-BLUE' => 'TF Ice Blue: cool ice-blue finish with reflections.',
	'ACP_TFPR_DESC_TF-SILVER-NEW' => 'TF Silver New: bright silver finish with dimensional metal styling.',

	'ACP_TFPR_UPLOAD_TITLE' => 'Install a new icon set',
	'ACP_TFPR_UPLOAD_EXPLAIN' => 'Upload a ZIP archive containing thanks.png, like.png, dislike.png, laugh.png, smile.png, surprise.png, doubt.png and hug.png. An optional icon.json may provide name, author, version and description.',
	'ACP_TFPR_UPLOAD_BUTTON' => 'Upload and install',
	'ACP_TFPR_UPLOAD_SUCCESS' => 'The icon set “%s” was installed and is initially disabled.',
	'ACP_TFPR_UPLOAD_INVALID' => 'The uploaded archive is not a valid icon set.',
	'ACP_TFPR_UPLOAD_MISSING' => 'Required PNG files are missing: %s',
	'ACP_TFPR_UPLOAD_EXISTS' => 'An icon set with this directory name already exists.',
	'ACP_TFPR_UPLOAD_ZIP_UNAVAILABLE' => 'The PHP ZipArchive extension is not available on this server.',
	'ACP_TFPR_UPLOAD_TOO_LARGE' => 'The ZIP archive or one of its files is too large.',
	'ACP_TFPR_AUTHOR' => 'Author',
	'ACP_TFPR_VERSION' => 'Version',
	'ACP_TFPR_TYPE' => 'Type',
	'ACP_TFPR_SYSTEM_SET' => 'System set',
	'ACP_TFPR_CUSTOM_SET' => 'Uploaded',
	'ACP_TFPR_ACTIONS' => 'Actions',
	'ACP_TFPR_DELETE' => 'Delete',
	'ACP_TFPR_DELETE_CONFIRM' => 'Do you really want to permanently delete the icon set “%s”?',
	'ACP_TFPR_DELETE_SUCCESS' => 'The icon set “%s” was deleted.',
	'ACP_TFPR_DELETE_FORBIDDEN' => 'System sets cannot be deleted.',
	'ACP_TFPR_NO_FILE' => 'Please select a ZIP archive first.',
]);
