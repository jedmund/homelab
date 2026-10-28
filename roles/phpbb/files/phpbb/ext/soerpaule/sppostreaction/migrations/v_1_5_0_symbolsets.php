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

class v_1_5_0_symbolsets extends \phpbb\db\migration\migration
{
	public static function depends_on()
	{
		return ['\\soerpaule\\sppostreaction\\migrations\\v_1_4_2_fresh_install'];
	}

	public function update_schema()
	{
		return [
			'change_columns' => [
				$this->table_prefix . 'users' => [
					'user_tfpr_icon_set' => ['VCHAR:64', 'tf-chrom'],
				],
			],
		];
	}

	public function revert_schema()
	{
		return [
			'change_columns' => [
				$this->table_prefix . 'users' => [
					'user_tfpr_icon_set' => ['VCHAR:64', 'standard'],
				],
			],
		];
	}

	public function update_data()
	{
		return [
			['config.update', ['tfpr_enabled_icon_sets', 'tf-chrom,tf-cherry,tf-ice-blue,tf-silver-new']],
			['config.update', ['tfpr_default_icon_set', 'tf-chrom']],
			['custom', [[$this, 'migrate_user_sets']]],
		];
	}

	public function migrate_user_sets()
	{
		$map = [
			'standard' => 'tf-chrom',
			'gunmetal' => 'tf-chrom',
			'copper' => 'tf-silver-new',
			'carbon' => 'tf-chrom',
			'ice' => 'tf-ice-blue',
			'tf-cherry-2' => 'tf-cherry',
		];

		foreach ($map as $old => $new)
		{
			$sql = 'UPDATE ' . $this->table_prefix . "users
				SET user_tfpr_icon_set = '" . $this->db->sql_escape($new) . "'
				WHERE user_tfpr_icon_set = '" . $this->db->sql_escape($old) . "'";
			$this->db->sql_query($sql);
		}
	}
}
