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

namespace fireplace\stampreactions\event;

use Symfony\Component\EventDispatcher\EventSubscriberInterface;
use fireplace\stampreactions\service\reaction_repository;
use fireplace\stampreactions\service\stamp_catalog;

class listener implements EventSubscriberInterface
{
	protected $repository;
	protected $catalog;
	protected $user;
	protected $template;
	protected $helper;

	public function __construct(reaction_repository $repository, stamp_catalog $catalog, \phpbb\user $user, \phpbb\template\template $template, \phpbb\controller\helper $helper)
	{
		$this->repository = $repository;
		$this->catalog = $catalog;
		$this->user = $user;
		$this->template = $template;
		$this->helper = $helper;
	}

	public static function getSubscribedEvents()
	{
		return [
			'core.user_setup'                         => 'load_language',
			'core.viewtopic_assign_template_vars_before' => 'assign_picker',
			'core.viewtopic_post_row_after'           => 'assign_post_stamps',
		];
	}

	public function load_language($event)
	{
		$lang_set_ext = $event['lang_set_ext'];
		$lang_set_ext[] = [
			'ext_name' => 'fireplace/stampreactions',
			'lang_set' => 'common',
		];
		$event['lang_set_ext'] = $lang_set_ext;
	}

	/**
	 * Page-level data: the picker (rendered once, not per post), the AJAX
	 * endpoint, and whether this visitor may react. Guests see the counts
	 * but not the picker.
	 */
	public function assign_picker($event)
	{
		$can_react = (int) $this->user->data['user_id'] !== ANONYMOUS && !$this->user->data['is_bot'];

		$this->template->assign_vars([
			'S_STAMPS'          => true,
			'S_STAMP_CAN_REACT' => $can_react,
			'U_STAMP_REACT'     => $can_react ? $this->helper->route('fireplace_stampreactions_react') : '',
			'STAMP_HASH'        => $can_react ? generate_link_hash('stamp_react') : '',
		]);

		if (!$can_react)
		{
			return;
		}

		foreach ($this->catalog->all() as $stamp)
		{
			$this->template->assign_block_vars('stamp_catalog', [
				'KEY'   => $stamp['key'],
				'LABEL' => htmlspecialchars($stamp['label'], ENT_QUOTES),
				'URL'   => $this->catalog->url($stamp['key']),
			]);
		}
	}

	/**
	 * Per-post pills: one nested block row per stamp that has at least one
	 * reaction, in manifest order.
	 */
	public function assign_post_stamps($event)
	{
		$post_id = (int) $event['row']['post_id'];
		$summary = $this->repository->get_summary($post_id, $this->catalog->keys());
		$mine = '';

		if ((int) $this->user->data['user_id'] !== ANONYMOUS)
		{
			$reaction = $this->repository->get_user_reaction($post_id, (int) $this->user->data['user_id']);
			$mine = $reaction ? (string) $reaction['reaction_key'] : '';
		}

		foreach ($this->catalog->all() as $stamp)
		{
			$count = $summary['counts'][$stamp['key']];
			if ($count < 1)
			{
				continue;
			}

			$this->template->assign_block_vars('postrow.stamps', [
				'KEY'   => $stamp['key'],
				'LABEL' => htmlspecialchars($stamp['label'], ENT_QUOTES),
				'URL'   => $this->catalog->url($stamp['key']),
				'COUNT' => $count,
				'USERS' => htmlspecialchars(implode(', ', $summary['reactors'][$stamp['key']]), ENT_QUOTES),
				'MINE'  => $stamp['key'] === $mine,
			]);
		}
	}
}
