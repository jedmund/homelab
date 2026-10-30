<?php
/**
 *
 * Derived from SP Post Reactions (https://github.com/soerpaule/sp-post-reactions),
 * (c) 2026 soerpaule, GPL-2.0. Modified for a single, manifest-driven stamp set.
 *
 * @license GNU General Public License, version 2 (GPL-2.0)
 *
 */

namespace fireplace\stampreactions\migrations;

class v1_0_0_install extends \phpbb\db\migration\migration
{
	public static function depends_on()
	{
		return ['\\phpbb\\db\\migration\\data\\v32x\\v329'];
	}

	public function effectively_installed()
	{
		return $this->db_tools->sql_table_exists($this->table_prefix . 'stamp_reactions');
	}

	public function update_schema()
	{
		return [
			'add_tables' => [
				$this->table_prefix . 'stamp_reactions' => [
					'COLUMNS' => [
						'reaction_id'   => ['UINT', null, 'auto_increment'],
						'post_id'       => ['UINT', 0],
						'user_id'       => ['UINT', 0],
						'reaction_key'  => ['VCHAR:20', ''],
						'reaction_time' => ['TIMESTAMP', 0],
					],
					'PRIMARY_KEY' => 'reaction_id',
					'KEYS' => [
						'post_id'   => ['INDEX', 'post_id'],
						'user_id'   => ['INDEX', 'user_id'],
						// One reaction per user per post, enforced by the database too.
						'post_user' => ['UNIQUE', ['post_id', 'user_id']],
					],
				],
			],
		];
	}

	public function revert_schema()
	{
		return [
			'drop_tables' => [
				$this->table_prefix . 'stamp_reactions',
			],
		];
	}
}
