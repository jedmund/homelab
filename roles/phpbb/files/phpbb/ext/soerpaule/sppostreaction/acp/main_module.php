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

class main_module
{
	public $u_action;
	public $tpl_name;
	public $page_title;

	private $system_sets = ['tf-chrom', 'tf-cherry', 'tf-ice-blue', 'tf-silver-new'];
	private $legacy_sets = ['standard', 'gunmetal', 'copper', 'carbon', 'ice', 'tf-cherry-2'];
	private $icons = ['thanks', 'like', 'dislike', 'laugh', 'smile', 'surprise', 'doubt', 'hug'];

	public function main($id, $mode)
	{
		global $config, $request, $template, $user, $phpbb_root_path;

		$user->add_lang_ext('soerpaule/sppostreaction', 'acp');
		$user->add_lang_ext('soerpaule/sppostreaction', 'ucp');

		$this->tpl_name = '@soerpaule_sppostreaction/acp_sppostreaction';
		$this->page_title = $user->lang('ACP_TFPR_SYMBOLSETS');
		add_form_key('tfpr_acp_settings');

		$base_path = $phpbb_root_path . 'ext/soerpaule/sppostreaction/styles/prosilver/theme/images/reactions/';
		$image_base = '../ext/soerpaule/sppostreaction/styles/prosilver/theme/images/reactions';
		$sets = $this->discover_sets($base_path, $user);
		$all_sets = array_keys($sets);

		$enabled = $this->configured_sets((string) ($config['tfpr_enabled_icon_sets'] ?? 'tf-chrom,tf-cherry,tf-ice-blue,tf-silver-new'), $all_sets);
		$default_set = (string) ($config['tfpr_default_icon_set'] ?? 'tf-chrom');
		if (!in_array($default_set, $enabled, true))
		{
			$default_set = 'tf-chrom';
		}

		if ($request->is_set_post('upload_set'))
		{
			if (!check_form_key('tfpr_acp_settings'))
			{
				trigger_error('FORM_INVALID');
			}
			$installed = $this->install_uploaded_set($request, $base_path, $user);
			trigger_error(sprintf($user->lang('ACP_TFPR_UPLOAD_SUCCESS'), $installed) . adm_back_link($this->u_action));
		}

		if ($request->is_set_post('delete_set'))
		{
			$slug = $request->variable('delete_slug', '');

			if (in_array($slug, $this->system_sets, true))
			{
				trigger_error($user->lang('ACP_TFPR_DELETE_FORBIDDEN') . adm_back_link($this->u_action), E_USER_WARNING);
			}
			if (!isset($sets[$slug]))
			{
				trigger_error($user->lang('ACP_TFPR_UPLOAD_INVALID') . adm_back_link($this->u_action), E_USER_WARNING);
			}

			// phpBB validates the confirmation request with its own confirm-box token.
			// The ACP form token is therefore checked only on the initial delete click.
			if (confirm_box(true))
			{
				$name = $sets[$slug]['name'];
				$this->remove_directory($base_path . $slug);
				$enabled = array_values(array_diff($enabled, [$slug]));
				$config->set('tfpr_enabled_icon_sets', implode(',', $enabled));
				if ($default_set === $slug)
				{
					$config->set('tfpr_default_icon_set', 'tf-chrom');
				}
				trigger_error(sprintf($user->lang('ACP_TFPR_DELETE_SUCCESS'), $name) . adm_back_link($this->u_action));
			}

			if (!check_form_key('tfpr_acp_settings'))
			{
				trigger_error('FORM_INVALID');
			}

			confirm_box(false, sprintf($user->lang('ACP_TFPR_DELETE_CONFIRM'), $sets[$slug]['name']), build_hidden_fields([
				'delete_set' => 1,
				'delete_slug' => $slug,
			]));
		}

		if ($request->is_set_post('submit'))
		{
			if (!check_form_key('tfpr_acp_settings'))
			{
				trigger_error('FORM_INVALID');
			}
			$selected = $request->variable('tfpr_enabled_sets', ['' => '']);
			$selected = array_keys(array_filter($selected));
			$selected = array_values(array_intersect($all_sets, $selected));
			if (!in_array('tf-chrom', $selected, true))
			{
				array_unshift($selected, 'tf-chrom');
			}
			$new_default = $request->variable('tfpr_default_icon_set', 'tf-chrom');
			if (!in_array($new_default, $selected, true))
			{
				$new_default = 'tf-chrom';
			}
			$config->set('tfpr_enabled_icon_sets', implode(',', $selected));
			$config->set('tfpr_default_icon_set', $new_default);
			trigger_error($user->lang('ACP_TFPR_SAVED') . adm_back_link($this->u_action));
		}

		foreach ($sets as $set => $meta)
		{
			$preview = [];
			foreach ($this->icons as $icon)
			{
				$preview[] = $image_base . '/' . $set . '/' . $icon . '.png';
			}
			$template->assign_block_vars('tfpr_sets', [
				'VALUE' => $set,
				'NAME' => $meta['name'],
				'DESCRIPTION' => $meta['description'],
				'AUTHOR' => $meta['author'],
				'VERSION' => $meta['version'],
				'SYSTEM' => $meta['system'],
				'ENABLED' => in_array($set, $enabled, true),
				'LOCKED' => $set === 'tf-chrom',
				'DEFAULT' => $set === $default_set,
				'PREVIEW' => $preview,
			]);
		}

		$template->assign_vars(['U_ACTION' => $this->u_action]);
	}

	private function configured_sets($value, array $all_sets)
	{
		$enabled = array_filter(array_map('trim', explode(',', $value)));
		$enabled = array_values(array_intersect($all_sets, $enabled));
		if (!in_array('tf-chrom', $enabled, true))
		{
			array_unshift($enabled, 'tf-chrom');
		}
		return $enabled;
	}

	private function discover_sets($base_path, $user)
	{
		$sets = [];
		if (!is_dir($base_path))
		{
			return $sets;
		}
		foreach (scandir($base_path) as $slug)
		{
			if ($slug === '.' || $slug === '..' || !preg_match('/^[a-z0-9_-]+$/', $slug) || !is_dir($base_path . $slug))
			{
				continue;
			}
			if (in_array($slug, $this->legacy_sets, true))
			{
				continue;
			}
			$valid = true;
			foreach ($this->icons as $icon)
			{
				if (!is_file($base_path . $slug . '/' . $icon . '.png'))
				{
					$valid = false;
					break;
				}
			}
			if (!$valid)
			{
				continue;
			}
			$system = in_array($slug, $this->system_sets, true);
			$meta = [
				'name' => $system ? $user->lang('TFPR_SET_' . strtoupper($slug)) : ucfirst(str_replace(['-', '_'], ' ', $slug)),
				'description' => $system ? $user->lang('ACP_TFPR_DESC_' . strtoupper($slug)) : '',
				'author' => $system ? 'TF Design' : '',
				'version' => '1.0',
				'system' => $system,
			];
			$manifest = $base_path . $slug . '/icon.json';
			if (is_file($manifest))
			{
				$json = json_decode((string) file_get_contents($manifest), true);
				if (is_array($json))
				{
					foreach (['name', 'description', 'author', 'version'] as $key)
					{
						if (isset($json[$key]) && is_string($json[$key]) && trim($json[$key]) !== '')
						{
							$meta[$key] = htmlspecialchars(trim($json[$key]), ENT_QUOTES, 'UTF-8');
						}
					}
				}
			}
			$sets[$slug] = $meta;
		}
		uksort($sets, function ($a, $b) {
			$ia = array_search($a, $this->system_sets, true);
			$ib = array_search($b, $this->system_sets, true);
			if ($ia !== false || $ib !== false)
			{
				$ia = $ia === false ? 999 : $ia;
				$ib = $ib === false ? 999 : $ib;
				return $ia <=> $ib;
			}
			return strcasecmp($a, $b);
		});
		return $sets;
	}

	private function install_uploaded_set($request, $base_path, $user)
	{
		if (!class_exists('ZipArchive'))
		{
			trigger_error($user->lang('ACP_TFPR_UPLOAD_ZIP_UNAVAILABLE') . adm_back_link($this->u_action), E_USER_WARNING);
		}
		$upload = $request->file('tfpr_symbolset_zip');
		if (empty($upload) || empty($upload['tmp_name']) || !is_uploaded_file($upload['tmp_name']))
		{
			trigger_error($user->lang('ACP_TFPR_NO_FILE') . adm_back_link($this->u_action), E_USER_WARNING);
		}
		if (!empty($upload['error']) || (int) $upload['size'] > 10 * 1024 * 1024)
		{
			trigger_error($user->lang('ACP_TFPR_UPLOAD_TOO_LARGE') . adm_back_link($this->u_action), E_USER_WARNING);
		}
		$zip = new \ZipArchive();
		if ($zip->open($upload['tmp_name']) !== true)
		{
			trigger_error($user->lang('ACP_TFPR_UPLOAD_INVALID') . adm_back_link($this->u_action), E_USER_WARNING);
		}
		$entries = [];
		$manifest = [];
		for ($i = 0; $i < $zip->numFiles; $i++)
		{
			$stat = $zip->statIndex($i);
			$name = str_replace('\\', '/', $stat['name']);
			if (substr($name, -1) === '/')
			{
				continue;
			}
			if (strpos($name, '../') !== false || strpos($name, '/') === 0 || (int) $stat['size'] > 2 * 1024 * 1024)
			{
				$zip->close();
				trigger_error($user->lang('ACP_TFPR_UPLOAD_INVALID') . adm_back_link($this->u_action), E_USER_WARNING);
			}
			$base = basename($name);
			if ($base === 'icon.json')
			{
				$decoded = json_decode((string) $zip->getFromIndex($i), true);
				if (is_array($decoded))
				{
					$manifest = $decoded;
				}
				continue;
			}
			if (preg_match('/^(thanks|like|dislike|laugh|smile|surprise|doubt|hug)\.png$/', $base))
			{
				$data = $zip->getFromIndex($i);
				if ($data === false || substr($data, 1, 3) !== 'PNG')
				{
					$zip->close();
					trigger_error($user->lang('ACP_TFPR_UPLOAD_INVALID') . adm_back_link($this->u_action), E_USER_WARNING);
				}
				$entries[$base] = $data;
			}
		}
		$zip->close();
		$missing = [];
		foreach ($this->icons as $icon)
		{
			if (!isset($entries[$icon . '.png']))
			{
				$missing[] = $icon . '.png';
			}
		}
		if ($missing)
		{
			trigger_error(sprintf($user->lang('ACP_TFPR_UPLOAD_MISSING'), implode(', ', $missing)) . adm_back_link($this->u_action), E_USER_WARNING);
		}
		$name = isset($manifest['name']) && is_string($manifest['name']) ? trim($manifest['name']) : pathinfo($upload['name'], PATHINFO_FILENAME);
		$slug_source = isset($manifest['id']) && is_string($manifest['id']) ? $manifest['id'] : $name;
		$slug = strtolower(preg_replace('/[^a-zA-Z0-9_-]+/', '-', $slug_source));
		$slug = trim($slug, '-_');
		if ($slug === '' || in_array($slug, $this->system_sets, true) || is_dir($base_path . $slug))
		{
			trigger_error($user->lang('ACP_TFPR_UPLOAD_EXISTS') . adm_back_link($this->u_action), E_USER_WARNING);
		}
		if (!mkdir($base_path . $slug, 0755, true) && !is_dir($base_path . $slug))
		{
			trigger_error($user->lang('ACP_TFPR_UPLOAD_INVALID') . adm_back_link($this->u_action), E_USER_WARNING);
		}
		foreach ($entries as $file => $data)
		{
			file_put_contents($base_path . $slug . '/' . $file, $data, LOCK_EX);
		}
		$safe_manifest = [
			'id' => $slug,
			'name' => $name !== '' ? $name : ucfirst($slug),
			'author' => isset($manifest['author']) && is_string($manifest['author']) ? $manifest['author'] : '',
			'version' => isset($manifest['version']) && is_string($manifest['version']) ? $manifest['version'] : '1.0',
			'description' => isset($manifest['description']) && is_string($manifest['description']) ? $manifest['description'] : '',
		];
		file_put_contents($base_path . $slug . '/icon.json', json_encode($safe_manifest, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE), LOCK_EX);
		return $safe_manifest['name'];
	}

	private function remove_directory($path)
	{
		if (!is_dir($path))
		{
			return;
		}
		foreach (scandir($path) as $item)
		{
			if ($item === '.' || $item === '..')
			{
				continue;
			}
			$full = $path . '/' . $item;
			if (is_dir($full))
			{
				$this->remove_directory($full);
			}
			else
			{
				@unlink($full);
			}
		}
		@rmdir($path);
	}
}
