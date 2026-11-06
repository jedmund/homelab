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

namespace fireplace\stampreactions\service;

/**
 * The stamp set: one ordered list of {key, label, file} read from
 * stamps.json. Every other class asks this for the allowed keys, so adding
 * or removing a stamp is a manifest edit plus an image file.
 */
class stamp_catalog
{
	/** @var array[] Stamps in display order. */
	protected $stamps = [];

	/** @var string Path of the stamp images relative to the board root. */
	protected $image_path;

	public function __construct($ext_path)
	{
		$this->image_path = $ext_path . 'stamps/';
		$manifest = @file_get_contents($ext_path . 'stamps.json');
		$decoded = $manifest === false ? null : json_decode($manifest, true);

		foreach ((array) $decoded as $stamp)
		{
			$key = isset($stamp['key']) ? (string) $stamp['key'] : '';

			// Keys are stored in a VCHAR:20 column and used in CSS and data attributes.
			if (!preg_match('/^[a-z0-9-]{1,20}$/', $key) || isset($this->stamps[$key]))
			{
				continue;
			}

			$this->stamps[$key] = [
				'key'   => $key,
				'label' => isset($stamp['label']) ? (string) $stamp['label'] : $key,
				'file'  => isset($stamp['file']) ? basename((string) $stamp['file']) : $key . '.png',
			];
		}
	}

	public function all()
	{
		return array_values($this->stamps);
	}

	public function keys()
	{
		return array_keys($this->stamps);
	}

	public function has($key)
	{
		return isset($this->stamps[$key]);
	}

	public function label($key)
	{
		return isset($this->stamps[$key]) ? $this->stamps[$key]['label'] : (string) $key;
	}

	public function url($key)
	{
		return isset($this->stamps[$key]) ? $this->image_path . rawurlencode($this->stamps[$key]['file']) : '';
	}
}
