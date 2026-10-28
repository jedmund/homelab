<?php
/**
 *
 * SP Post Reactions extension for phpBB.
 *
 * @copyright (c) 2026 soerpaule
 * @license GNU General Public License, version 2 (GPL-2.0)
 *
 */

namespace soerpaule\sppostreaction\migrations;

class v_1_4_2_fresh_install extends \phpbb\db\migration\migration
{
	public static function depends_on()
	{
		return ['\\phpbb\\db\\migration\\data\\v32x\\v329'];
	}

	/**
	 * The table and user column already exist when transitioning from
	 * soerpaule/tfpostreactions. Treat the installation migration as complete
	 * in that case so data and modules are not created a second time.
	 */
	public function effectively_installed()
	{
		return $this->db_tools->sql_table_exists($this->table_prefix . 'post_reactions')
			&& $this->db_tools->sql_column_exists($this->table_prefix . 'users', 'user_tfpr_icon_set');
	}

	public function update_schema()
	{
		return [
			'add_tables' => [
				$this->table_prefix . 'post_reactions' => [
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
						'post_user' => ['UNIQUE', ['post_id', 'user_id']],
					],
				],
			],
			'add_columns' => [
				$this->table_prefix . 'users' => [
					'user_tfpr_icon_set' => ['VCHAR:64', 'tf-chrom'],
				],
			],
		];
	}

	public function revert_schema()
	{
		return [
			'drop_columns' => [
				$this->table_prefix . 'users' => ['user_tfpr_icon_set'],
			],
			'drop_tables' => [
				$this->table_prefix . 'post_reactions',
			],
		];
	}

	public function update_data()
	{
		return [
			['config.add', ['tfpr_enabled_icon_sets', 'tf-chrom,tf-cherry,tf-ice-blue,tf-silver-new']],
			['config.add', ['tfpr_default_icon_set', 'tf-chrom']],

			['module.add', [
				'ucp',
				'UCP_PREFS',
				[
					'module_basename' => '\\soerpaule\\sppostreaction\\ucp\\main_module',
					'modes' => ['settings'],
				],
			]],

			['module.add', [
				'acp',
				'ACP_CAT_DOT_MODS',
				'ACP_TFPR_TITLE',
			]],
			['module.add', [
				'acp',
				'ACP_TFPR_TITLE',
				[
					'module_basename' => '\\soerpaule\\sppostreaction\\acp\\main_module',
					'modes' => ['settings'],
				],
			]],
		];
	}
}
