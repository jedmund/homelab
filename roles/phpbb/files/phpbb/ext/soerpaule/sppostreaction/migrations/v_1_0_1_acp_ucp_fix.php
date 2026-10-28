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
 * Repairs module paths and authorisation conditions stored by phpBB during
 * the transition from TF Post Reactions to SP Post Reactions.
 *
 * The old extension identifier in module_auth hid the ACP and UCP modules
 * after soerpaule/tfpostreactions was disabled.
 */
class v_1_0_1_acp_ucp_fix extends \phpbb\db\migration\migration
{
	public static function depends_on()
	{
		return ['\\soerpaule\\sppostreaction\\migrations\\v_1_0_0_transition'];
	}

	public function update_data()
	{
		return [
			['custom', [[$this, 'repair_module_entries']]],
		];
	}

	public function repair_module_entries()
	{
		$modules_table = $this->table_prefix . 'modules';

		if (!$this->db_tools->sql_table_exists($modules_table))
		{
			return;
		}

		$old_acp = '\\soerpaule\\tfpostreactions\\acp\\main_module';
		$new_acp = '\\soerpaule\\sppostreaction\\acp\\main_module';
		$old_ucp = '\\soerpaule\\tfpostreactions\\ucp\\main_module';
		$new_ucp = '\\soerpaule\\sppostreaction\\ucp\\main_module';
		$old_auth = 'ext_soerpaule/tfpostreactions';
		$new_auth = 'ext_soerpaule/sppostreaction';

		foreach ([$old_acp => $new_acp, $old_ucp => $new_ucp] as $old => $new)
		{
			$sql = 'UPDATE ' . $modules_table . "
				SET module_basename = '" . $this->db->sql_escape($new) . "'
				WHERE module_basename = '" . $this->db->sql_escape($old) . "'";
			$this->db->sql_query($sql);
		}

		// Update the existing authorisation condition to the new extension identifier.
		$sql = 'UPDATE ' . $modules_table . "
			SET module_auth = REPLACE(module_auth,
				'" . $this->db->sql_escape($old_auth) . "',
				'" . $this->db->sql_escape($new_auth) . "')
			WHERE module_auth LIKE '%" . $this->db->sql_escape($old_auth) . "%'";
		$this->db->sql_query($sql);
	}
}
