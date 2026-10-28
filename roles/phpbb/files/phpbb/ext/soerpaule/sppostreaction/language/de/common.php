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
	'TFPR_REACT'            => 'Reagieren',
	'TFPR_THANK_REACT'      => 'Bedanken / Reagieren',
	'TFPR_CHOOSE'           => 'Reaktion auswählen',
	'TFPR_LIKE'             => 'Gefällt mir',
	'TFPR_DISLIKE'          => 'Gefällt mir nicht',
	'TFPR_DOUBT'            => 'Sehe ich anders',
	'TFPR_SMILE'            => 'Lächeln',
	'TFPR_LAUGH'            => 'Lachen',
	'TFPR_SURPRISE'         => 'Überrascht',
	'TFPR_HUG'              => 'Umarmung',
	'TFPR_THANKS'           => 'Danke',
	'TFPR_INVALID_REACTION' => 'Die ausgewählte Reaktion ist ungültig.',
	'TFPR_INVALID_TOKEN'    => 'Die Sitzung ist abgelaufen. Bitte lade die Seite neu und versuche es erneut.',
	'TFPR_POST_NOT_FOUND'   => 'Der Beitrag wurde nicht gefunden.',
	'TFPR_REACTORS'          => 'Reagiert haben: %s',
	'TFPR_NO_REACTORS'       => 'Niemand hat diese Reaktion gewählt.',
	'TFPR_SAVE_ERROR'       => 'Die Reaktion konnte nicht gespeichert werden.',

	'TFPR_NOTIFICATION_TYPE_REACTION' => 'Benachrichtigung, wenn jemand auf einen meiner Beiträge reagiert',
	'TFPR_NOTIFICATION_REACTION'      => '%1$s hat mit „%2$s“ auf deinen Beitrag reagiert.',
	'TFPR_NOTIFICATION_REFERENCE'     => 'Beitrag: „%s“',
]);

$lang = array_merge($lang, [
	'UCP_TFPR_TITLE' => 'Reaktionen',
	'UCP_TFPR_SETTINGS' => 'Symbolsatz',
]);
