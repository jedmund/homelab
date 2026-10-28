<?php
/**
 *
 * SP Post Reactions extension for phpBB.
 *
 * @copyright (c) 2026 soerpaule
 * @license GNU General Public License, version 2 (GPL-2.0)
 *
 */

namespace soerpaule\sppostreaction\event;

use Symfony\Component\EventDispatcher\EventSubscriberInterface;
use soerpaule\sppostreaction\service\reaction_manager;
use soerpaule\sppostreaction\service\reaction_repository;

class listener implements EventSubscriberInterface
{
	protected $repository;
	protected $user;
	protected $helper;
	protected $config;
	protected $root_path;

	public function __construct(reaction_repository $repository, \phpbb\user $user, \phpbb\controller\helper $helper, \phpbb\config\config $config, $root_path)
	{
		$this->repository = $repository;
		$this->user = $user;
		$this->helper = $helper;
		$this->config = $config;
		$this->root_path = $root_path;
	}

	public static function getSubscribedEvents()
	{
		return [
			'core.user_setup' => 'load_language',
			'core.viewtopic_modify_post_row' => 'add_reactions_to_postrow',
		];
	}

	public function load_language($event)
	{
		$lang_set_ext = $event['lang_set_ext'];
		$lang_set_ext[] = [
			'ext_name' => 'soerpaule/sppostreaction',
			'lang_set' => 'common',
		];
		$event['lang_set_ext'] = $lang_set_ext;
	}

	public function add_reactions_to_postrow($event)
	{
		$row = $event['row'];
		$post_row = $event['post_row'];

		// Guests must not see reaction data or controls.
		if ((int) $this->user->data['user_id'] === ANONYMOUS)
		{
			$post_row['S_TFPR_CAN_REACT'] = false;
			$event['post_row'] = $post_row;
			return;
		}

		$post_id = (int) $row['post_id'];
		$counts = $this->repository->get_counts($post_id, reaction_manager::ALLOWED);
		$reactors = $this->repository->get_reactors($post_id, reaction_manager::ALLOWED);
		$user_reaction = $this->repository->get_user_reaction($post_id, (int) $this->user->data['user_id']);
		$current = $user_reaction ? (string) $user_reaction['reaction_key'] : '';

		$base_path = $this->root_path . 'ext/soerpaule/sppostreaction/styles/prosilver/theme/images/reactions/';
		$enabled_sets = array_filter(array_map('trim', explode(',', (string) ($this->config['tfpr_enabled_icon_sets'] ?? 'tf-chrom'))));
		$enabled_sets = array_values(array_filter($enabled_sets, function ($set) use ($base_path) {
			return preg_match('/^[a-z0-9_-]+$/', $set) && is_dir($base_path . $set);
		}));
		if (!in_array('tf-chrom', $enabled_sets, true))
		{
			array_unshift($enabled_sets, 'tf-chrom');
		}

		$default_set = (string) ($this->config['tfpr_default_icon_set'] ?? 'tf-chrom');
		if (!in_array($default_set, $enabled_sets, true))
		{
			$default_set = 'tf-chrom';
		}

		$icon_set = isset($this->user->data['user_tfpr_icon_set']) && (string) $this->user->data['user_tfpr_icon_set'] !== ''
			? (string) $this->user->data['user_tfpr_icon_set']
			: $default_set;
		if (!in_array($icon_set, $enabled_sets, true))
		{
			$icon_set = $default_set;
		}

		$post_row = array_merge($post_row, [
			'U_TFPR_REACT' => $this->helper->route('soerpaule_sppostreaction_react'),
			'TFPR_HASH' => generate_link_hash('tfpr_react'),
			'TFPR_CURRENT' => $current,
			'TFPR_ICON_SET' => $icon_set,
			'TFPR_ICON_BASE' => $this->build_icon_base($icon_set),
			'TFPR_CURRENT_ICON' => $this->build_icon_base($icon_set) . ($current !== '' ? rawurlencode($current) : 'thanks') . '.png',
			'TFPR_DESKTOP_DEFAULT_ICON' => $this->build_icon_base($icon_set) . 'like.png',
			'TFPR_ICON_STYLE' => $this->build_icon_style($icon_set),
			'TFPR_LIKE_COUNT' => $counts['like'],
			'TFPR_DISLIKE_COUNT' => $counts['dislike'],
			'TFPR_DOUBT_COUNT' => $counts['doubt'],
			'TFPR_SMILE_COUNT' => $counts['smile'],
			'TFPR_LAUGH_COUNT' => $counts['laugh'],
			'TFPR_SURPRISE_COUNT' => $counts['surprise'],
			'TFPR_THANKS_COUNT' => $counts['thanks'],
			'TFPR_HUG_COUNT' => $counts['hug'],
			'TFPR_LIKE_USERS' => implode(', ', $reactors['like']),
			'TFPR_DISLIKE_USERS' => implode(', ', $reactors['dislike']),
			'TFPR_DOUBT_USERS' => implode(', ', $reactors['doubt']),
			'TFPR_SMILE_USERS' => implode(', ', $reactors['smile']),
			'TFPR_LAUGH_USERS' => implode(', ', $reactors['laugh']),
			'TFPR_SURPRISE_USERS' => implode(', ', $reactors['surprise']),
			'TFPR_THANKS_USERS' => implode(', ', $reactors['thanks']),
			'TFPR_HUG_USERS' => implode(', ', $reactors['hug']),
			'S_TFPR_CAN_REACT' => true,
		]);

		$event['post_row'] = $post_row;
	}
	private function build_icon_base($set)
	{
		return generate_board_url() . '/ext/soerpaule/sppostreaction/styles/prosilver/theme/images/reactions/' . rawurlencode($set) . '/';
	}

	private function build_icon_style($set)
	{
		$base = $this->build_icon_base($set);
		return '--tfpr-thanks:url(\'' . $base . 'thanks.png\');'
			. '--tfpr-like:url(\'' . $base . 'like.png\');'
			. '--tfpr-dislike:url(\'' . $base . 'dislike.png\');'
			. '--tfpr-laugh:url(\'' . $base . 'laugh.png\');'
			. '--tfpr-smile:url(\'' . $base . 'smile.png\');'
			. '--tfpr-surprise:url(\'' . $base . 'surprise.png\');'
			. '--tfpr-doubt:url(\'' . $base . 'doubt.png\');'
			. '--tfpr-hug:url(\'' . $base . 'hug.png\');';
	}

}
