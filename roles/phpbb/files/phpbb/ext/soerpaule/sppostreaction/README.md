# SP Post Reactions

SP Post Reactions adds AJAX-powered reactions to phpBB 3.3 posts.

## Features

- Eight reactions without reloading the page
- Notifications for post authors
- Display of users who reacted
- Four bundled icon sets
- Installation and management of custom icon sets in the ACP
- Personal icon-set selection in the UCP
- Responsive desktop and mobile display
- British English and German language packs
- Reaction data and controls are hidden from guests

## Requirements

- phpBB 3.3.x
- PHP 7.2 or newer

## Installation

1. Copy `soerpaule/sppostreaction` to `ext/soerpaule/sppostreaction`.
2. Open **ACP → Customise → Manage extensions**.
3. Enable **SP Post Reactions**.
4. Configure the available icon sets in the ACP.

## Updating

1. Disable the extension. Do **not** delete its data.
2. Replace the files in `ext/soerpaule/sppostreaction`.
3. Enable the extension again.
4. Purge the phpBB cache.

Existing reactions, settings and user selections are retained during a normal update.

## Support

- Website: https://ext.soerpaule.de
- Source and issues: https://github.com/soerpaule/sp-post-reactions

## License

GNU General Public License, version 2 only (`GPL-2.0-only`).
