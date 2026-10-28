<?php
/**
 *
 * SP Post Reactions extension for phpBB.
 *
 * @copyright (c) 2026 soerpaule
 * @license GNU General Public License, version 2 (GPL-2.0)
 *
 */

namespace soerpaule\sppostreaction\controller;

use Symfony\Component\HttpFoundation\JsonResponse;
use soerpaule\sppostreaction\service\reaction_manager;

class reaction_controller
{
	const NOTIFICATION_TYPE = 'soerpaule.sppostreaction.notification.type.reaction';

	protected $manager;
	protected $db;
	protected $user;
	protected $request;
	protected $auth;
	protected $posts_table;
	protected $topics_table;
	protected $notification_manager;

	public function __construct(reaction_manager $manager, \phpbb\db\driver\driver_interface $db, \phpbb\user $user, \phpbb\request\request_interface $request, \phpbb\auth\auth $auth, $posts_table, $topics_table, \phpbb\notification\manager $notification_manager)
	{
		$this->manager = $manager;
		$this->db = $db;
		$this->user = $user;
		$this->request = $request;
		$this->auth = $auth;
		$this->posts_table = $posts_table;
		$this->topics_table = $topics_table;
		$this->notification_manager = $notification_manager;
	}

	public function react()
	{
		$this->user->add_lang_ext('soerpaule/sppostreaction', 'common');

		if ((int) $this->user->data['user_id'] === ANONYMOUS)
		{
			return $this->error($this->user->lang('LOGIN_REQUIRED'), 401);
		}

		$hash = $this->request->variable('hash', '');
		if (!check_link_hash($hash, 'tfpr_react'))
		{
			return $this->error($this->user->lang('TFPR_INVALID_TOKEN'), 403);
		}

		$post_id = $this->request->variable('post_id', 0);
		$reaction_key = $this->request->variable('reaction', '');

		if (!$post_id || !$this->manager->is_allowed($reaction_key))
		{
			return $this->error($this->user->lang('TFPR_INVALID_REACTION'), 400);
		}

		$sql = 'SELECT p.post_id, p.poster_id, p.forum_id, p.topic_id, p.post_subject, t.topic_title
				FROM ' . $this->posts_table . ' p
				LEFT JOIN ' . $this->topics_table . ' t ON t.topic_id = p.topic_id
				WHERE p.post_id = ' . (int) $post_id;
		$result_db = $this->db->sql_query_limit($sql, 1);
		$post = $this->db->sql_fetchrow($result_db);
		$this->db->sql_freeresult($result_db);

		if (!$post)
		{
			return $this->error($this->user->lang('TFPR_POST_NOT_FOUND'), 404);
		}

		$forum_id = (int) $post['forum_id'];
		if (!$this->auth->acl_get('f_read', $forum_id))
		{
			return $this->error($this->user->lang('NOT_AUTHORISED'), 403);
		}

		$user_id = (int) $this->user->data['user_id'];
		$result = $this->manager->toggle($post_id, $user_id, $reaction_key);

		if (!empty($result['reaction_id']))
		{
			try
			{
				if ($result['action'] === 'deleted' || $result['action'] === 'updated')
				{
					$this->notification_manager->delete_notifications(self::NOTIFICATION_TYPE, (int) $result['reaction_id']);
				}

				if ($result['action'] === 'inserted' || $result['action'] === 'updated')
				{
					$subject = trim((string) $post['post_subject']);
					if ($subject === '')
					{
						$subject = (string) $post['topic_title'];
					}

					$this->notification_manager->add_notifications(self::NOTIFICATION_TYPE, [
						'reaction_id'   => (int) $result['reaction_id'],
						'post_id'       => $post_id,
						'post_author_id'=> (int) $post['poster_id'],
						'topic_id'      => (int) $post['topic_id'],
						'forum_id'      => $forum_id,
						'post_subject'  => $subject,
						'reactor_id'    => $user_id,
						'reaction_key'  => $reaction_key,
						'reaction_time' => time(),
					]);
				}
			}
			catch (\Throwable $e)
			{
				// A notification failure must never break the reaction AJAX response.
				if (function_exists('phpbb_log'))
				{
					phpbb_log('SP Post Reactions notification error: ' . $e->getMessage());
				}
			}
		}

		return new JsonResponse([
			'success' => true,
			'post_id' => $post_id,
			'current' => $result['current'],
			'counts'   => $result['counts'],
			'reactors' => $result['reactors'],
		]);
	}

	protected function error($message, $status)
	{
		return new JsonResponse(['success' => false, 'message' => (string) $message], (int) $status);
	}
}
