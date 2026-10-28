<?php
/**
 *
 * SP Post Reactions extension for phpBB.
 *
 * @copyright (c) 2026 soerpaule
 * @license GNU General Public License, version 2 (GPL-2.0)
 *
 */

namespace soerpaule\sppostreaction;

/**
 * Extension base class.
 */
class ext extends \phpbb\extension\base
{
	/** @var string Notification type service name. */
	const NOTIFICATION_TYPE = 'soerpaule.sppostreaction.notification.type.reaction';

	/**
	 * Check whether the extension can be enabled.
	 *
	 * @return bool
	 */
	public function is_enableable()
	{
		return PHP_VERSION_ID >= 70200
			&& phpbb_version_compare(PHPBB_VERSION, '3.3.0', '>=')
			&& phpbb_version_compare(PHPBB_VERSION, '3.4.0', '<');
	}

	/**
	 * Enable the notification type.
	 *
	 * @param mixed $old_state Previous enable state
	 * @return mixed
	 */
	public function enable_step($old_state)
	{
		if ($old_state === false)
		{
			$this->container->get('notification_manager')->enable_notifications(self::NOTIFICATION_TYPE);
			return 'notifications';
		}

		return parent::enable_step($old_state);
	}

	/**
	 * Disable the notification type.
	 *
	 * @param mixed $old_state Previous disable state
	 * @return mixed
	 */
	public function disable_step($old_state)
	{
		if ($old_state === false)
		{
			$this->container->get('notification_manager')->disable_notifications(self::NOTIFICATION_TYPE);
			return 'notifications';
		}

		return parent::disable_step($old_state);
	}

	/**
	 * Purge notifications belonging to this extension.
	 *
	 * @param mixed $old_state Previous purge state
	 * @return mixed
	 */
	public function purge_step($old_state)
	{
		if ($old_state === false)
		{
			$this->container->get('notification_manager')->purge_notifications(self::NOTIFICATION_TYPE);
			return 'notifications';
		}

		return parent::purge_step($old_state);
	}
}
