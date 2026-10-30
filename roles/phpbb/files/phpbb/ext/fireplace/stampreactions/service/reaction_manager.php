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

namespace fireplace\stampreactions\service;

class reaction_manager
{
	protected $repository;
	protected $catalog;

	public function __construct(reaction_repository $repository, stamp_catalog $catalog)
	{
		$this->repository = $repository;
		$this->catalog = $catalog;
	}

	public function is_allowed($reaction_key)
	{
		return $this->catalog->has((string) $reaction_key);
	}

	/**
	 * One reaction per user per post: choosing the stamp you already have
	 * removes it, choosing a different one replaces it.
	 */
	public function toggle($post_id, $user_id, $reaction_key)
	{
		$existing = $this->repository->get_user_reaction($post_id, $user_id);
		$current = '';
		$action = '';
		$reaction_id = 0;

		if ($existing && $existing['reaction_key'] === $reaction_key)
		{
			$reaction_id = (int) $existing['reaction_id'];
			$this->repository->delete($reaction_id);
			$action = 'deleted';
		}
		else if ($existing)
		{
			$reaction_id = (int) $existing['reaction_id'];
			$this->repository->update($reaction_id, $reaction_key);
			$current = $reaction_key;
			$action = 'updated';
		}
		else
		{
			$reaction_id = (int) $this->repository->insert($post_id, $user_id, $reaction_key);
			$current = $reaction_key;
			$action = 'inserted';
		}

		$summary = $this->repository->get_summary($post_id, $this->catalog->keys());

		return [
			'current'     => $current,
			'action'      => $action,
			'reaction_id' => $reaction_id,
			'counts'      => $summary['counts'],
			'reactors'    => $summary['reactors'],
		];
	}
}
