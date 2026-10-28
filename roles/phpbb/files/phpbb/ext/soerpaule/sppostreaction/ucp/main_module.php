<?php
/**
 *
 * SP Post Reactions extension for phpBB.
 *
 * @copyright (c) 2026 soerpaule
 * @license GNU General Public License, version 2 (GPL-2.0)
 *
 */

namespace soerpaule\sppostreaction\ucp;

class main_module
{
	public $u_action;
	public $tpl_name;
	public $page_title;

	public function main($id, $mode)
	{
		global $db, $user, $template, $request, $phpbb_container, $config, $phpbb_root_path;

		$user->add_lang_ext('soerpaule/sppostreaction', 'ucp');
		$this->tpl_name = '@soerpaule_sppostreaction/ucp_sppostreaction';
		$this->page_title = $user->lang('UCP_TFPR_SETTINGS');

		add_form_key('tfpr_ucp_settings');

		$base_path = $phpbb_root_path . 'ext/soerpaule/sppostreaction/styles/prosilver/theme/images/reactions/';
		$allowed = array_filter(array_map('trim', explode(',', (string) ($config['tfpr_enabled_icon_sets'] ?? 'tf-chrom'))));
		$allowed = array_values(array_filter($allowed, function ($set) use ($base_path) {
			return preg_match('/^[a-z0-9_-]+$/', $set) && is_dir($base_path . $set);
		}));
		if (!in_array('tf-chrom', $allowed, true))
		{
			array_unshift($allowed, 'tf-chrom');
		}
		$default_set = (string) ($config['tfpr_default_icon_set'] ?? 'tf-chrom');
		if (!in_array($default_set, $allowed, true))
		{
			$default_set = 'tf-chrom';
		}

		$current = isset($user->data['user_tfpr_icon_set']) && (string) $user->data['user_tfpr_icon_set'] !== ''
			? (string) $user->data['user_tfpr_icon_set']
			: $default_set;
		if (!in_array($current, $allowed, true))
		{
			$current = $default_set;
		}

		if ($request->is_set_post('submit'))
		{
			if (!check_form_key('tfpr_ucp_settings'))
			{
				trigger_error('FORM_INVALID');
			}

			$selected = $request->variable('tfpr_icon_set', 'tf-chrom');
			if (!in_array($selected, $allowed, true))
			{
				$selected = 'tf-chrom';
			}

			$sql = 'UPDATE ' . USERS_TABLE . "
				SET user_tfpr_icon_set = '" . $db->sql_escape($selected) . "'
				WHERE user_id = " . (int) $user->data['user_id'];
			$db->sql_query($sql);

			$user->data['user_tfpr_icon_set'] = $selected;
			$current = $selected;

			meta_refresh(3, $this->u_action);
			$message = $user->lang('TFPR_SETTINGS_SAVED') . '<br><br>' . sprintf($user->lang('RETURN_UCP'), '<a href="' . $this->u_action . '">', '</a>');
			trigger_error($message);
		}

		foreach ($allowed as $set)
		{
			$template->assign_block_vars('tfpr_sets', [
				'VALUE' => $set,
				'NAME' => $this->get_set_name($set, $base_path, $user),
				'CHECKED' => $current === $set,
				'CSS_CLASS' => 'tfpr-set-' . $set . ' tfpr-dynamic-set',
				'STYLE' => $this->build_icon_style($set),
				'BASE' => $this->build_icon_base($set),
			]);
		}

		$template->assign_vars([
			'U_ACTION' => $this->u_action,
			'TFPR_CURRENT_SET' => $current,
		]);
	}

	private function build_icon_base($set)
	{
		return generate_board_url() . '/ext/soerpaule/sppostreaction/styles/prosilver/theme/images/reactions/' . rawurlencode($set) . '/';
	}

	private function build_icon_style($set)
	{
		$base = $this->build_icon_base($set);
		return '--tfpr-thanks:url(\'' . $base . 'thanks.png\');'
			. '--tfpr-like:url(\'' . $base . 'like.png\');'
			. '--tfpr-dislike:url(\'' . $base . 'dislike.png\');'
			. '--tfpr-laugh:url(\'' . $base . 'laugh.png\');'
			. '--tfpr-smile:url(\'' . $base . 'smile.png\');'
			. '--tfpr-surprise:url(\'' . $base . 'surprise.png\');'
			. '--tfpr-doubt:url(\'' . $base . 'doubt.png\');'
			. '--tfpr-hug:url(\'' . $base . 'hug.png\');';
	}

	private function get_set_name($set, $base_path, $user)
	{
		$key = 'TFPR_SET_' . strtoupper($set);
		$translated = $user->lang($key);
		if ($translated !== $key)
		{
			return $translated;
		}
		$manifest = $base_path . $set . '/icon.json';
		if (is_file($manifest))
		{
			$json = json_decode((string) file_get_contents($manifest), true);
			if (is_array($json) && !empty($json['name']))
			{
				return htmlspecialchars((string) $json['name'], ENT_QUOTES, 'UTF-8');
			}
		}
		return ucfirst(str_replace(['-', '_'], ' ', $set));
	}
}

