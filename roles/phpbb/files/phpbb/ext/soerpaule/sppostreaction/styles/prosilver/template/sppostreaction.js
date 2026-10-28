(function () {
	'use strict';

	var keys = ['thanks', 'like', 'dislike', 'laugh', 'smile', 'surprise', 'doubt', 'hug'];

	function each(nodes, callback) {
		Array.prototype.forEach.call(nodes, callback);
	}

	function byPost(selector, postId) {
		return document.querySelector(selector + '[data-post-id="' + postId + '"]');
	}

	function closePicker(wrap) {
		if (!wrap) { return; }
		var picker = wrap.querySelector('.tfpr-picker');
		var button = wrap.querySelector('.tfpr-toolbar-button');
		if (picker) {
			picker.hidden = true;
			picker.classList.remove('is-open');
		}
		if (button) {
			button.setAttribute('aria-expanded', 'false');
		}
	}

	function closeAll(exceptWrap) {
		each(document.querySelectorAll('.tfpr-action-wrap'), function (wrap) {
			if (wrap !== exceptWrap) { closePicker(wrap); }
		});
	}

	function setBusy(wrap, busy) {
		wrap.classList.toggle('is-saving', busy);
		each(wrap.querySelectorAll('.tfpr-choice'), function (choice) {
			choice.disabled = busy;
		});
	}

	function updateToolbarIcon(wrap, current) {
		var symbol = wrap.querySelector('.tfpr-toolbar-symbol');
		if (!symbol) { return; }
		keys.forEach(function (key) {
			symbol.classList.remove('tfpr-icon-' + key);
		});
		var key = current || (wrap.classList.contains('tfpr-desktop-action') ? 'like' : 'thanks');
		symbol.classList.add('tfpr-icon-' + key);
		symbol.classList.toggle('is-current', !!current);
		if (symbol.tagName && symbol.tagName.toLowerCase() === 'img') {
			var base = wrap.getAttribute('data-icon-base') || '';
			var defaultIcon = wrap.getAttribute('data-default-icon') || '';
			symbol.setAttribute('src', (!current && defaultIcon) ? defaultIcon : base + key + '.png');
		}
	}

	function closeReactorPopovers(exceptWrap) {
		each(document.querySelectorAll('.tfpr-summary-wrap'), function (summaryWrap) {
			if (summaryWrap === exceptWrap) { return; }
			var popover = summaryWrap.querySelector('.tfpr-reactor-popover');
			if (popover) { popover.hidden = true; }
		});
	}

	function formatReactors(summaryWrap, names) {
		if (!names || !names.length) {
			return summaryWrap.getAttribute('data-no-reactors') || '';
		}
		var label = summaryWrap.getAttribute('data-reactors-label') || '%s';
		return label.replace('%s', names.join(', '));
	}

	function updateView(wrap, response) {
		var postId = wrap.getAttribute('data-post-id');
		var summaryWrap = byPost('.tfpr-summary-wrap', postId);
		each(document.querySelectorAll('.tfpr-action-wrap[data-post-id="' + postId + '"]'), function (actionWrap) {
			actionWrap.setAttribute('data-current', response.current || '');
			updateToolbarIcon(actionWrap, response.current || '');
			each(actionWrap.querySelectorAll('.tfpr-choice'), function (choice) {
				choice.classList.toggle('is-current', choice.getAttribute('data-reaction') === response.current);
			});
		});
		if (summaryWrap) {
			summaryWrap.setAttribute('data-current', response.current || '');
		}

		if (!summaryWrap) { return; }
		keys.forEach(function (key) {
			var count = parseInt(response.counts[key], 10) || 0;
			var item = summaryWrap.querySelector('.tfpr-count-' + key);
			if (!item) { return; }
			item.classList.toggle('is-empty', count === 0);
			item.classList.toggle('is-mine', response.current === key);
			var badge = item.querySelector('.tfpr-badge');
			if (badge) { badge.textContent = count; }
			var names = response.reactors && response.reactors[key] ? response.reactors[key] : [];
			item.setAttribute('data-users', names.join(', '));
			item.setAttribute('title', formatReactors(summaryWrap, names));
		});
	}

	function saveReaction(wrap, reaction) {
		if (wrap.classList.contains('is-saving')) { return; }
		setBusy(wrap, true);

		var body = new URLSearchParams();
		body.append('post_id', wrap.getAttribute('data-post-id'));
		body.append('reaction', reaction);
		body.append('hash', wrap.getAttribute('data-hash'));

		fetch(wrap.getAttribute('data-url'), {
			method: 'POST',
			credentials: 'same-origin',
			headers: {
				'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
				'X-Requested-With': 'XMLHttpRequest'
			},
			body: body.toString()
		})
		.then(function (response) {
			return response.json().then(function (data) {
				if (!response.ok || !data.success) {
					throw new Error(data.message || wrap.getAttribute('data-error'));
				}
				return data;
			});
		})
		.then(function (data) {
			updateView(wrap, data);
			closePicker(wrap);
		})
		.catch(function (error) {
			window.alert(error.message || wrap.getAttribute('data-error'));
		})
		.then(function () {
			setBusy(wrap, false);
		});
	}

	function initWrap(wrap) {
		if (wrap.getAttribute('data-tfpr-ready') === '1') { return; }
		wrap.setAttribute('data-tfpr-ready', '1');

		var button = wrap.querySelector('.tfpr-toolbar-button');
		var picker = wrap.querySelector('.tfpr-picker');
		if (!button || !picker) { return; }

		button.addEventListener('click', function (event) {
			event.preventDefault();
			event.stopPropagation();
			var open = picker.hidden;
			closeAll(wrap);
			picker.hidden = !open;
			picker.classList.toggle('is-open', open);
			button.setAttribute('aria-expanded', open ? 'true' : 'false');
		});

		picker.addEventListener('click', function (event) {
			event.stopPropagation();
			var choice = event.target.closest ? event.target.closest('.tfpr-choice') : null;
			if (choice) {
				saveReaction(wrap, choice.getAttribute('data-reaction'));
			}
		});
	}

	function initSummary(summaryWrap) {
		if (summaryWrap.getAttribute('data-tfpr-reactors-ready') === '1') { return; }
		summaryWrap.setAttribute('data-tfpr-reactors-ready', '1');
		var popover = summaryWrap.querySelector('.tfpr-reactor-popover');
		if (!popover) { return; }

		summaryWrap.addEventListener('click', function (event) {
			var item = event.target.closest ? event.target.closest('.tfpr-count') : null;
			if (!item || item.classList.contains('is-empty')) { return; }
			event.preventDefault();
			event.stopPropagation();
			var users = item.getAttribute('data-users') || '';
			var names = users ? users.split(', ') : [];
			var wasOpen = !popover.hidden && popover.getAttribute('data-reaction') === item.getAttribute('data-reaction');
			closeReactorPopovers(summaryWrap);
			if (wasOpen) {
				popover.hidden = true;
				return;
			}
			popover.textContent = formatReactors(summaryWrap, names);
			popover.setAttribute('data-reaction', item.getAttribute('data-reaction'));
			popover.hidden = false;
		});
	}

	function init() {
		each(document.querySelectorAll('.tfpr-action-wrap'), initWrap);
		each(document.querySelectorAll('.tfpr-summary-wrap'), initSummary);
	}

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', init);
	} else {
		init();
	}

	document.addEventListener('click', function (event) {
		if (!event.target.closest || !event.target.closest('.tfpr-action-wrap')) {
			closeAll(null);
			closeReactorPopovers(null);
		}
	});

	document.addEventListener('keydown', function (event) {
		if (event.key === 'Escape' || event.keyCode === 27) {
			closeAll(null);
		}
	});
}());
