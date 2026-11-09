/* Poll saved application data only; never trigger an NHL loader. */
(function ($) {
    'use strict';
    const INTERVAL = 60000;
    const MAX_DELAY = 300000;
    const TIMEOUT = 10000;
    const root = document.getElementById('game-refresh');
    if (!root) return;
    const auto = document.getElementById('auto-refresh');
    const button = document.getElementById('refresh-now');
    const status = document.getElementById('refresh-status');
    let timer, pending = false, delay = INTERVAL, generation = 0;
    let metadata = JSON.parse(document.getElementById('initial-freshness').textContent);
    let checked = null;

    // A response started before a favorite mutation must not restore stale buttons.
    $(document).ajaxSend(function (_, xhr, settings) {
        if (!/^(GET|HEAD|OPTIONS)$/i.test(settings.type)) generation += 1;
    });
    function showFreshness() {
        let text = metadata.text;
        if (metadata.saved_at) {
            text = text.replace(metadata.saved_at, new Date(metadata.saved_at).toLocaleString());
            const old = Date.now() - Date.parse(metadata.saved_at) >= metadata.stale_after_seconds * 1000;
            if (!metadata.final && old && !text.includes('Data may be out of date.')) text += ' Data may be out of date.';
        }
        document.getElementById('game-freshness').textContent = text;
    }
    function schedule() {
        clearTimeout(timer);
        if (auto.checked && !document.hidden) timer = setTimeout(refresh, delay);
    }
    function reconcile(container, html, key) {
        const template = document.createElement('template');
        template.innerHTML = html;
        const previous = new Map(Array.from(container.children).map(row => [row.getAttribute(key), row]));
        const retained = new Set();
        let position = container.firstElementChild;
        for (const row of Array.from(template.content.children)) {
            const old = previous.get(row.getAttribute(key));
            const node = old && old.outerHTML === row.outerHTML ? old : row;
            retained.add(node);
            if (node !== position) container.insertBefore(node, position);
            position = node.nextElementSibling;
        }
        for (const row of Array.from(container.children)) if (!retained.has(row)) row.remove();
    }
    function apply(data) {
        if (data.entity !== root.dataset.entity || !data.freshness) throw new Error('Unexpected refresh response');
        const active = document.activeElement;
        const scoreboardLink = active?.closest('#scoreboard-games a')?.getAttribute('href');
        const row = active?.closest('[data-player-id]');
        const table = active?.closest('table');
        const focus = row && table ? {table: table.id, player: row.dataset.playerId,
            index: Array.from(row.querySelectorAll('a, button, input')).indexOf(active)} : null;
        const scroll = {x: window.scrollX, y: window.scrollY};
        if (data.tables) {
            for (const [id, html] of Object.entries(data.tables)) {
                const element = document.getElementById(id);
                if (!element?.tBodies[0]) throw new Error('Missing game table');
                if (element.tBodies[0].innerHTML !== html) {
                    element.querySelectorAll('.js-fav-alert').forEach(alert => root.after(alert));
                    element.tBodies[0].innerHTML = html;
                    $(element).trigger('update', [true]);
                }
            }
            document.getElementById('game-result').textContent = data.result;
        } else {
            reconcile(document.getElementById('scoreboard-games'), data.games, 'data-game-id');
        }
        if (focus && !active.isConnected) {
            const rows = document.getElementById(focus.table).querySelectorAll('[data-player-id]');
            const replacement = Array.from(rows).find(item => item.dataset.playerId === focus.player);
            replacement?.querySelectorAll('a, button, input')[focus.index]?.focus({preventScroll: true});
        }
        if (scoreboardLink && !active.isConnected) {
            Array.from(document.querySelectorAll('#scoreboard-games a'))
                .find(link => link.getAttribute('href') === scoreboardLink)?.focus({preventScroll: true});
        }
        window.scrollTo(scroll.x, scroll.y);
        metadata = data.freshness;
        checked = new Date(data.freshness.checked_at).toLocaleTimeString();
        showFreshness();
    }
    function refresh() {
        clearTimeout(timer);
        if (pending || document.hidden || $.active) { schedule(); return; }
        pending = true;
        button.disabled = true;
        status.textContent = 'Checking saved data…';
        const started = generation;
        $.ajax({url: root.dataset.url, dataType: 'json', timeout: TIMEOUT, cache: false})
            .done(function (data) {
                if (started !== generation) {
                    status.textContent = 'Your selection changed. Refresh again to check saved data.';
                    return;
                }
                try {
                    apply(data);
                    delay = INTERVAL;
                    status.textContent = 'Last checked ' + checked + '. Checks saved data; NHL updates run separately.';
                } catch (_) { failed(); }
            })
            .fail(failed)
            .always(function () { pending = false; button.disabled = false; schedule(); });
    }
    function failed() {
        delay = Math.min(delay * 2, MAX_DELAY);
        showFreshness();
        status.textContent = 'Refresh failed. Displayed data is unchanged.' + (checked ? ' Last checked ' + checked + '.' : '') +
            (auto.checked ? ' Will retry automatically, or use Refresh now.' : ' Use Refresh now to retry.');
    }
    button.addEventListener('click', refresh);
    auto.addEventListener('change', function () {
        status.textContent = auto.checked ? 'Auto-refresh enabled.' : 'Auto-refresh paused.';
        schedule();
    });
    document.addEventListener('visibilitychange', function () {
        if (!document.hidden && auto.checked) refresh(); else schedule();
    });
    showFreshness();
    schedule();
})(jQuery);
