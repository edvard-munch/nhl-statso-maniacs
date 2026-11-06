$(function () {
  const root = $('#comparison-content');
  if (!root.length) return;
  const groups = ['skaters', 'goalies'];
  let active = Number(root.attr('data-skaters-count')) ? 'skaters' : 'goalies';
  let busy = false;

  function modeAttribute(group) {
    return group === 'skaters' ? 'data-skater-mode' : 'data-goalie-mode';
  }
  function selectedUrl(href) {
    const url = new URL(href, window.location.href);
    const season = root.attr('data-season');
    if (season) url.searchParams.set('season', season);
    url.searchParams.set('skater_mode', root.attr('data-skater-mode'));
    url.searchParams.set('goalie_mode', root.attr('data-goalie-mode'));
    return url.href;
  }
  function refresh() {
    if (!Number(root.attr('data-' + active + '-count'))) {
      active = groups.find(group => Number(root.attr('data-' + group + '-count'))) || 'skaters';
    }
    let total = 0;
    groups.forEach(function (group) {
      const count = Number(root.attr('data-' + group + '-count'));
      total += count;
      $('#js_' + group + '_switch').toggle(count > 0).toggleClass('current-tab', group === active);
      $('#js_' + group + '_block, #' + group + '_table').toggle(count > 0 && group === active);
      $('[data-player-type="' + group + '"]').each(function () {
        $(this).toggleClass('current-tab', $(this).attr('data-comparison-mode') === root.attr(modeAttribute(group)));
      });
    });
    $('#comparison-empty').prop('hidden', total > 0);
    // Keep the selected modes when changing season through the form.
    ['skater_mode', 'goalie_mode'].forEach(function (name) {
      const form = $('#saved-players-season').closest('form');
      let input = form.find('input[name="' + name + '"]');
      if (!input.length) input = $('<input>', {type: 'hidden', name: name}).appendTo(form);
      input.val(root.attr(name === 'skater_mode' ? 'data-skater-mode' : 'data-goalie-mode'));
    });
  }
  function applyPayload(data) {
    groups.forEach(function (group) {
      $('#' + group + '_table tbody').html(data['compare_' + group]);
      root.attr('data-' + group + '-count', data[group + '_count']);
      $('#js_' + group + '_switch').text(data[group + '_button']);
    });
    refresh();
  }
  function request(link, success, method = 'GET') {
    if (busy) return;
    busy = true;
    $('#comparison-error').prop('hidden', true);
    $.ajax({url: selectedUrl(link.attr('href')), type: method, dataType: 'json'}).done(success).fail(function () {
      $('#comparison-error').text('Could not update comparison. Please try again.').prop('hidden', false);
    }).always(function () { busy = false; });
  }
  root.on('click', '[data-comparison-type]', function (event) {
    event.preventDefault();
    active = $(this).attr('data-comparison-type');
    refresh();
  });
  root.on('click', '[data-comparison-mode]', function (event) {
    event.preventDefault();
    const link = $(this);
    request(link, function (data) {
      $('#' + data.player_type + '_table tbody').html(data.table);
      root.attr(modeAttribute(data.player_type), data.stat_type);
      refresh();
    });
  });
  root.on('click', '[data-comparison-remove], [data-comparison-reset]', function (event) {
    event.preventDefault();
    const link = $(this);
    if (link.is('[data-comparison-reset]') && !window.confirm('Clear these players from comparison?')) return;
    request(link, applyPayload, 'POST');
  });
  refresh();
});
