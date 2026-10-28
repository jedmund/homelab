<?php
/**
 *
 * SP Post Reactions extension for phpBB.
 *
 * @copyright (c) 2026 soerpaule
 * @license GNU General Public License, version 2 (GPL-2.0)
 *
 */

namespace soerpaule\sppostreaction\acp;

class main_info
{
	public function module()
	{
		return [
			'filename' => '\\soerpaule\\sppostreaction\\acp\\main_module',
			'title' => 'ACP_TFPR_TITLE',
			'modes' => [
				'settings' => [
					'title' => 'ACP_TFPR_SYMBOLSETS',
					'auth' => 'ext_soerpaule/sppostreaction && acl_a_board',
					'cat' => ['ACP_TFPR_TITLE'],
				],
			],
		];
	}
}
