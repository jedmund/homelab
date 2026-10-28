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

/**
 * One-time compatibility bridge from soerpaule/tfpostreactions to
 * soerpaule/sppostreaction.
 *
 * Existing reaction data, configuration values and user selections remain
 * untouched. Only class and service names stored by phpBB are updated.
 */
class v_1_0_0_transition extends \phpbb\db\migration\migration
{
	public static function depends_on()
	{
		return ['\\soerpaule\\sppostreaction\\migrations\\v_1_5_0_symbolsets'];
	}

	public function update_data()
	{
		return [
			['custom', [[$this, 'update_module_basenames']]],
			['custom', [[$this, 'update_notification_type']]],
		];
	}

	public function update_module_basenames()
	{
		$modules_table = $this->table_prefix . 'modules';

		if (!$this->db_tools->sql_table_exists($modules_table))
		{
			return;
		}

		$replacements = [
			'\\soerpaule\\tfpostreactions\\acp\\main_module' => '\\soerpaule\\sppostreaction\\acp\\main_module',
			'\\soerpaule\\tfpostreactions\\ucp\\main_module' => '\\soerpaule\\sppostreaction\\ucp\\main_module',
		];

		foreach ($replacements as $old => $new)
		{
			$sql = 'UPDATE ' . $modules_table . "
				SET module_basename = '" . $this->db->sql_escape($new) . "'
				WHERE module_basename = '" . $this->db->sql_escape($old) . "'";
			$this->db->sql_query($sql);
		}
	}

	public function update_notification_type()
	{
		$types_table = $this->table_prefix . 'notification_types';

		if (!$this->db_tools->sql_table_exists($types_table)
			|| !$this->db_tools->sql_column_exists($types_table, 'notification_type_name'))
		{
			return;
		}

		$old = 'soerpaule.tfpostreactions.notification.type.reaction';
		$new = 'soerpaule.sppostreaction.notification.type.reaction';

		// Rename the type only when the new name does not already exist.
		$sql = 'SELECT notification_type_id
			FROM ' . $types_table . "
			WHERE notification_type_name = '" . $this->db->sql_escape($new) . "'";
		$result = $this->db->sql_query_limit($sql, 1);
		$new_exists = (bool) $this->db->sql_fetchfield('notification_type_id');
		$this->db->sql_freeresult($result);

		if (!$new_exists)
		{
			$sql = 'UPDATE ' . $types_table . "
				SET notification_type_name = '" . $this->db->sql_escape($new) . "'
				WHERE notification_type_name = '" . $this->db->sql_escape($old) . "'";
			$this->db->sql_query($sql);
		}
	}
}
