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
	'TFPR_REACT'            => 'React',
	'TFPR_THANK_REACT'      => 'Thank / React',
	'TFPR_CHOOSE'           => 'Choose reaction',
	'TFPR_LIKE'             => 'Like',
	'TFPR_DISLIKE'          => 'Dislike',
	'TFPR_DOUBT'            => 'I see it differently',
	'TFPR_SMILE'            => 'Smile',
	'TFPR_LAUGH'            => 'Laugh',
	'TFPR_SURPRISE'         => 'Surprised',
	'TFPR_HUG'              => 'Hug',
	'TFPR_THANKS'           => 'Thanks',
	'TFPR_INVALID_REACTION' => 'The selected reaction is invalid.',
	'TFPR_INVALID_TOKEN'    => 'Your session has expired. Reload the page and try again.',
	'TFPR_POST_NOT_FOUND'   => 'The post could not be found.',
	'TFPR_REACTORS'          => 'Reacted: %s',
	'TFPR_NO_REACTORS'       => 'Nobody chose this reaction.',
	'TFPR_SAVE_ERROR'       => 'The reaction could not be saved.',

	'TFPR_NOTIFICATION_TYPE_REACTION' => 'Notify me when someone reacts to one of my posts',
	'TFPR_NOTIFICATION_REACTION'      => '%1$s reacted “%2$s” to your post.',
	'TFPR_NOTIFICATION_REFERENCE'     => 'Post: “%s”',
]);

$lang = array_merge($lang, [
	'UCP_TFPR_TITLE' => 'Reactions',
	'UCP_TFPR_SETTINGS' => 'Icon set',
]);
