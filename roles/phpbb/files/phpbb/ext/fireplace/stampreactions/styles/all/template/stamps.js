(function () {
	'use strict';

	var picker = null;
	var openFor = null;
	var busy = false;

	function each(nodes, fn) { Array.prototype.forEach.call(nodes, fn); }

	function closePicker() {
		if (!picker) { return; }
		picker.hidden = true;
		if (openFor) { openFor.setAttribute('aria-expanded', 'false'); }
		openFor = null;
	}

	function openPicker(button) {
		var box = button.closest('.stamps');
		var current = box.querySelector('.stamp-pill.is-mine');
		var currentKey = current ? current.getAttribute('data-stamp') : '';

		each(picker.querySelectorAll('.stamp-choice'), function (choice) {
			choice.classList.toggle('is-current', choice.getAttribute('data-stamp') === currentKey);
		});

		picker.hidden = false;
		picker.setAttribute('data-post-id', box.getAttribute('data-post-id'));
		button.setAttribute('aria-expanded', 'true');
		openFor = button;

		var rect = button.getBoundingClientRect();
		var width = picker.offsetWidth;
		var left = rect.left + window.pageXOffset;
		var maxLeft = window.pageXOffset + document.documentElement.clientWidth - width - 8;
		picker.style.left = Math.max(window.pageXOffset + 8, Math.min(left, maxLeft)) + 'px';
		picker.style.top = (rect.bottom + window.pageYOffset + 6) + 'px';
	}

	function catalogEntry(key) {
		return picker.querySelector('.stamp-choice[data-stamp="' + key + '"]');
	}

	function pill(key, count, names, mine) {
		var entry = catalogEntry(key);
		var label = entry.getAttribute('data-label');
		var el = document.createElement('button');
		var img = document.createElement('img');
		var num = document.createElement('span');

		el.type = 'button';
		el.className = 'stamp-pill' + (mine ? ' is-mine' : '');
		el.setAttribute('data-stamp', key);
		el.title = names.length ? label + ': ' + names.join(', ') : label;
		img.src = entry.getAttribute('data-url');
		img.alt = label;
		img.width = 48;
		img.height = 48;
		num.className = 'stamp-count';
		num.textContent = count;
		el.appendChild(img);
		el.appendChild(num);
		return el;
	}

	function render(box, data) {
		each(box.querySelectorAll('.stamp-pill'), function (el) { el.remove(); });
		var add = box.querySelector('.stamp-add');

		each(picker.querySelectorAll('.stamp-choice'), function (choice) {
			var key = choice.getAttribute('data-stamp');
			var count = parseInt(data.counts[key], 10) || 0;
			if (!count) { return; }
			box.insertBefore(pill(key, count, (data.reactors && data.reactors[key]) || [], data.current === key), add);
		});
	}

	function send(postId, key) {
		if (busy) { return; }
		busy = true;
		picker.classList.add('is-saving');

		var body = new URLSearchParams();
		body.append('post_id', postId);
		body.append('reaction', key);
		body.append('hash', picker.getAttribute('data-hash'));

		fetch(picker.getAttribute('data-url'), {
			method: 'POST',
			credentials: 'same-origin',
			headers: {
				'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
				'X-Requested-With': 'XMLHttpRequest'
			},
			body: body.toString()
		}).then(function (response) {
			return response.json().then(function (data) { return { ok: response.ok, data: data }; });
		}).then(function (result) {
			if (!result.ok || !result.data.success) {
				throw new Error(result.data && result.data.message ? result.data.message : picker.getAttribute('data-error'));
			}
			var box = document.querySelector('.stamps[data-post-id="' + postId + '"]');
			if (box) { render(box, result.data); }
			closePicker();
		}).catch(function (error) {
			window.alert(error.message || picker.getAttribute('data-error'));
		}).then(function () {
			busy = false;
			picker.classList.remove('is-saving');
		});
	}

	document.addEventListener('DOMContentLoaded', function () {
		picker = document.getElementById('stamp-picker');
		if (!picker) { return; }

		document.addEventListener('click', function (event) {
			var add = event.target.closest('.stamp-add');
			var choice = event.target.closest('.stamp-choice');
			var pillButton = event.target.closest('button.stamp-pill');

			if (add) {
				if (openFor === add) { closePicker(); } else { closePicker(); openPicker(add); }
				return;
			}
			if (choice && picker.contains(choice)) {
				send(picker.getAttribute('data-post-id'), choice.getAttribute('data-stamp'));
				return;
			}
			if (pillButton) {
				send(pillButton.closest('.stamps').getAttribute('data-post-id'), pillButton.getAttribute('data-stamp'));
				return;
			}
			if (!picker.contains(event.target)) { closePicker(); }
		});

		document.addEventListener('keydown', function (event) {
			if (event.key === 'Escape') { closePicker(); }
		});
	});
}());
