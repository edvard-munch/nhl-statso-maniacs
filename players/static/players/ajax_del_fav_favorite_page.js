$(function () {
  let busy = false;
  const message = $('#favorites-update-message');
  const groups = ['skaters', 'goalies'];

  function showMessage(text, failed) {
    message.text(text).attr('class', failed ? 'alert alert-danger' : 'alert alert-primary')
      .prop('hidden', false);
  }

  $('body').on('click', '.js-fav-del', function (event) {
    event.preventDefault();
    if (busy) return;
    const button = $(this);
    const table = button.closest('table');
    const group = table.attr('id').includes('skaters') ? 'skaters' : 'goalies';
    const url = new URL(button.attr('href'), window.location.href);
    if (!url.pathname.endsWith('/')) url.pathname += '/';
    const season = $('#saved-players-season').attr('data-season');
    if (season) url.searchParams.set('season', season);
    busy = true;
    button.attr('aria-disabled', 'true');

    $.getJSON(url.href).done(function (data) {
      if (!data.authenticated) {
        showMessage('Sign in to update your favorites.', true);
        return;
      }
      if (!Number.isInteger(data.skaters_count) || !Number.isInteger(data.goalies_count)) {
        showMessage('Could not confirm removal. Refresh the page and try again.', true);
        return;
      }
      const counts = {skaters: data.skaters_count, goalies: data.goalies_count};
      const currentPage = table[0].config.pager.page;
      button.closest('tr').remove();
      groups.forEach(function (kind) {
        const tab = $('#js_' + kind + '_switch');
        tab.text(kind.toUpperCase() + ' (' + counts[kind] + ')').toggle(counts[kind] > 0);
        if (!counts[kind]) {
          tab.removeClass('current-tab');
          $('#js_' + kind + '_block').hide();
          $('#js_' + kind + '_block [role="status"]').prop('hidden', true);
          $('#js_' + kind + '_block tbody').empty();
        }
      });
      $('#favorites-empty-state').prop('hidden', counts.skaters + counts.goalies > 0);
      if (!counts[group]) {
        const remaining = groups.find(kind => counts[kind] > 0);
        if (remaining) $('#js_' + remaining + '_switch').trigger('click');
      } else {
        const pageEmpty = table.find('tbody tr:visible').length === 0;
        // Pager requests use one-based pages; return to the previous page if the
        // last visible row was removed, retaining the current filters otherwise.
        table.trigger('pagerUpdate', Math.max(1, currentPage + (pageEmpty ? 0 : 1)));
      }
      showMessage(data.message, false);
    }).fail(function () {
      showMessage('Could not remove favorite. Please try again.', true);
    }).always(function () {
      busy = false;
      button.attr('aria-disabled', 'false');
    });
  });
});
