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

namespace fireplace\stampreactions;

class ext extends \phpbb\extension\base
{
	/** @var string Notification type service name. */
	const NOTIFICATION_TYPE = 'fireplace.stampreactions.notification.type.reaction';

	public function is_enableable()
	{
		return PHP_VERSION_ID >= 70200
			&& phpbb_version_compare(PHPBB_VERSION, '3.3.0', '>=')
			&& phpbb_version_compare(PHPBB_VERSION, '3.4.0', '<');
	}

	public function enable_step($old_state)
	{
		if ($old_state === false)
		{
			$this->container->get('notification_manager')->enable_notifications(self::NOTIFICATION_TYPE);
			return 'notifications';
		}

		return parent::enable_step($old_state);
	}

	public function disable_step($old_state)
	{
		if ($old_state === false)
		{
			$this->container->get('notification_manager')->disable_notifications(self::NOTIFICATION_TYPE);
			return 'notifications';
		}

		return parent::disable_step($old_state);
	}

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
