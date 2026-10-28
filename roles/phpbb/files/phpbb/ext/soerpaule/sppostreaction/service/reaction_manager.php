<?php
/**
 *
 * SP Post Reactions extension for phpBB.
 *
 * @copyright (c) 2026 soerpaule
 * @license GNU General Public License, version 2 (GPL-2.0)
 *
 */

namespace soerpaule\sppostreaction\service;

class reaction_manager
{
	const ALLOWED = ['thanks', 'like', 'dislike', 'laugh', 'smile', 'surprise', 'doubt', 'hug'];

	protected $repository;

	public function __construct(reaction_repository $repository)
	{
		$this->repository = $repository;
	}

	public function is_allowed($reaction_key)
	{
		return in_array($reaction_key, self::ALLOWED, true);
	}

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

		return [
			'current'     => $current,
			'action'      => $action,
			'reaction_id' => $reaction_id,
			'counts'      => $this->repository->get_counts($post_id, self::ALLOWED),
			'reactors'    => $this->repository->get_reactors($post_id, self::ALLOWED),
		];
	}

}
