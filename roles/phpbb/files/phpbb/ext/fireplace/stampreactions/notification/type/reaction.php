<?php
/**
 *
 * Stamp Reactions extension for phpBB.
 *
 * Derived from SP Post Reactions (https://github.com/soerpaule/sp-post-reactions),
 * (c) 2026 soerpaule, GPL-2.0. Modified for a single, manifest-driven stamp set.
 *
 * @license GNU General Public License, version 2 (GPL-2.0)
 *
 */

namespace fireplace\stampreactions\notification\type;

class reaction extends \phpbb\notification\type\base
{
	static public $notification_option = [
		'lang'  => 'STAMP_NOTIFICATION_TYPE_REACTION',
		'group' => 'NOTIFICATION_GROUP_POSTING',
	];

	protected $user_loader;

	public function set_user_loader(\phpbb\user_loader $user_loader)
	{
		$this->user_loader = $user_loader;
	}

	public function get_type()
	{
		return 'fireplace.stampreactions.notification.type.reaction';
	}

	static public function get_item_id($data)
	{
		return (int) $data['reaction_id'];
	}

	static public function get_item_parent_id($data)
	{
		return (int) $data['post_id'];
	}

	public function find_users_for_notification($data, $options = [])
	{
		$author_id = (int) $data['post_author_id'];
		$reactor_id = (int) $data['reactor_id'];

		if (!$author_id || $author_id === ANONYMOUS || $author_id === $reactor_id)
		{
			return [];
		}

		$options = array_merge(['ignore_users' => []], $options);

		return $this->get_authorised_recipients(
			[$author_id],
			(int) $data['forum_id'],
			$options,
			true
		);
	}

	public function get_title()
	{
		$username = $this->user_loader->get_username((int) $this->get_data('reactor_id'), 'no_profile');
		// The label is stored with the notification, so it still reads correctly
		// if the stamp is later renamed or removed from the manifest.
		$reaction_name = (string) $this->get_data('reaction_label');

		return $this->language->lang('STAMP_NOTIFICATION_REACTION', $username, $reaction_name);
	}

	public function get_reference()
	{
		return $this->language->lang('STAMP_NOTIFICATION_REFERENCE', censor_text((string) $this->get_data('post_subject')));
	}

	public function get_url()
	{
		$post_id = (int) $this->get_data('post_id');
		return append_sid($this->phpbb_root_path . 'viewtopic.' . $this->php_ext, 'p=' . $post_id . '#p' . $post_id);
	}

	public function get_redirect_url()
	{
		return $this->get_url();
	}

	public function get_avatar()
	{
		return $this->user_loader->get_avatar((int) $this->get_data('reactor_id'), false, true);
	}

	public function users_to_query()
	{
		return [(int) $this->get_data('reactor_id')];
	}

	public function get_email_template()
	{
		return false;
	}

	public function get_email_template_variables()
	{
		return [];
	}

	public function create_insert_array($data, $pre_create_data = [])
	{
		$this->set_data('post_id', (int) $data['post_id']);
		$this->set_data('topic_id', (int) $data['topic_id']);
		$this->set_data('forum_id', (int) $data['forum_id']);
		$this->set_data('reactor_id', (int) $data['reactor_id']);
		$this->set_data('reaction_key', (string) $data['reaction_key']);
		$this->set_data('reaction_label', isset($data['reaction_label']) ? (string) $data['reaction_label'] : (string) $data['reaction_key']);
		$this->set_data('post_subject', (string) $data['post_subject']);
		$this->notification_time = isset($data['reaction_time']) ? (int) $data['reaction_time'] : time();

		parent::create_insert_array($data, $pre_create_data);
	}
}
