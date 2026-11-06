<?php
/**
 *
 * Stamp Reactions extension for phpBB.
 *
 * Derived from SP Post Reactions (https://github.com/soerpaule/sp-post-reactions),
 * (c) 2026 soerpaule, GPL-2.0. Modified for a single, manifest-driven stamp set.
 *
 * @license GNU General Public License, version 2 (GPL-2.0)
 *
 */

if (!defined('IN_PHPBB'))
{
	exit;
}

if (empty($lang) || !is_array($lang))
{
	$lang = [];
}

$lang = array_merge($lang, [
	'STAMP_REACT'            => 'React with a stamp',
	'STAMP_CHOOSE'           => 'Choose a stamp',
	'STAMP_REACTED_BY'       => 'Reacted: %s',
	'STAMP_SAVE_ERROR'       => 'The reaction could not be saved.',
	'STAMP_INVALID_REACTION' => 'The selected stamp is invalid.',
	'STAMP_INVALID_TOKEN'    => 'Your session has expired. Reload the page and try again.',
	'STAMP_POST_NOT_FOUND'   => 'The post could not be found.',

	'STAMP_NOTIFICATION_TYPE_REACTION' => 'Notify me when someone reacts to one of my posts',
	'STAMP_NOTIFICATION_REACTION'      => '%1$s reacted “%2$s” to your post.',
	'STAMP_NOTIFICATION_REFERENCE'     => 'Post: “%s”',
]);
