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

class reaction_repository
{
	protected $db;
	protected $table;
	protected $users_table;

	public function __construct(\phpbb\db\driver\driver_interface $db, $table, $users_table)
	{
		$this->db = $db;
		$this->table = $table;
		$this->users_table = $users_table;
	}

	public function get_user_reaction($post_id, $user_id)
	{
		$sql = 'SELECT reaction_id, reaction_key
				FROM ' . $this->table . '
				WHERE post_id = ' . (int) $post_id . '
				  AND user_id = ' . (int) $user_id;
		$result = $this->db->sql_query_limit($sql, 1);
		$row = $this->db->sql_fetchrow($result);
		$this->db->sql_freeresult($result);

		return $row ?: null;
	}

	public function get_counts($post_id, array $allowed)
	{
		$counts = array_fill_keys($allowed, 0);
		$sql = 'SELECT reaction_key, COUNT(*) AS reaction_count
				FROM ' . $this->table . '
				WHERE post_id = ' . (int) $post_id . '
				GROUP BY reaction_key';
		$result = $this->db->sql_query($sql);
		while ($row = $this->db->sql_fetchrow($result))
		{
			if (isset($counts[$row['reaction_key']]))
			{
				$counts[$row['reaction_key']] = (int) $row['reaction_count'];
			}
		}
		$this->db->sql_freeresult($result);

		return $counts;
	}

	public function get_reactors($post_id, array $allowed)
	{
		$reactors = array_fill_keys($allowed, []);
		$sql = 'SELECT r.reaction_key, u.username
				FROM ' . $this->table . ' r
				INNER JOIN ' . $this->users_table . ' u
					ON u.user_id = r.user_id
				WHERE r.post_id = ' . (int) $post_id . '
				ORDER BY r.reaction_time ASC';
		$result = $this->db->sql_query($sql);
		while ($row = $this->db->sql_fetchrow($result))
		{
			if (isset($reactors[$row['reaction_key']]))
			{
				$reactors[$row['reaction_key']][] = (string) $row['username'];
			}
		}
		$this->db->sql_freeresult($result);

		return $reactors;
	}

	public function insert($post_id, $user_id, $reaction_key)
	{
		$sql_ary = [
			'post_id'       => (int) $post_id,
			'user_id'       => (int) $user_id,
			'reaction_key'  => (string) $reaction_key,
			'reaction_time' => time(),
		];
		$sql = 'INSERT INTO ' . $this->table . ' ' . $this->db->sql_build_array('INSERT', $sql_ary);
		$this->db->sql_query($sql);
		return (int) $this->db->sql_nextid();
	}

	public function update($reaction_id, $reaction_key)
	{
		$sql_ary = [
			'reaction_key'  => (string) $reaction_key,
			'reaction_time' => time(),
		];
		$sql = 'UPDATE ' . $this->table . '
				SET ' . $this->db->sql_build_array('UPDATE', $sql_ary) . '
				WHERE reaction_id = ' . (int) $reaction_id;
		$this->db->sql_query($sql);
	}

	public function delete($reaction_id)
	{
		$sql = 'DELETE FROM ' . $this->table . '
				WHERE reaction_id = ' . (int) $reaction_id;
		$this->db->sql_query($sql);
	}
}
