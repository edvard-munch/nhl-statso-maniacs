$(function () {
  const root = $('#team-season-tables');
  const defence = $('#js_defencemen_sect');
  const forwards = $('#js_forwards_sect');
  const error = $('#team-stats-error');
  let busy = false;

  function statsUrl(mode, position) {
    const url = root.attr('data-stats-url').replace(
      '/__mode__/__position__/', '/' + mode + '/' + position + '/'
    );
    const season = root.attr('data-season');
    return season ? url + '?season=' + encodeURIComponent(season) : url;
  }

  function setBusy(value) {
    busy = value;
    root.find('[data-team-stats], [data-team-layout]').attr('aria-disabled', String(value));
    if (value) error.prop('hidden', true);
  }

  function showError() {
    error.text('Could not load team statistics. Please try again.').prop('hidden', false);
  }

  function render(section, data) {
    section.attr('data-mode', data.stat_type).attr('data-position', data.position_filter);
    section.find('tbody').html(data.stats);
    section.find('table').trigger('update');
    const nextMode = data.stat_type === 'tot' ? 'avg' : 'tot';
    section.find('[data-team-stats]')
      .text(nextMode === 'avg' ? 'See average stats' : 'See total stats')
      .attr('href', statsUrl(nextMode, data.position_filter));
    section.find('[data-team-empty]').text(data.empty_message).prop('hidden', data.total > 0);
    section.find('[data-team-layout]').attr(
      'href', statsUrl(data.stat_type, data.position_filter === 't' ? 'd' : 't')
    );
  }

  root.on('click', '[data-team-stats]', function (event) {
    event.preventDefault();
    if (busy || !root.attr('data-season')) return;
    const section = $(this).closest('[data-team-skater-section]');
    const mode = section.attr('data-mode') === 'tot' ? 'avg' : 'tot';
    setBusy(true);
    $.getJSON(statsUrl(mode, section.attr('data-position')))
      .done(function (data) { render(section, data); })
      .fail(showError)
      .always(function () { setBusy(false); });
  });

  root.on('click', '[data-team-layout]', function (event) {
    event.preventDefault();
    if (busy || !root.attr('data-season')) return;
    const button = $(this);
    const mode = defence.attr('data-mode');
    setBusy(true);
    if (defence.attr('data-position') !== 't') {
      $.getJSON(statsUrl(mode, 't'))
        .done(function (data) {
          render(defence, data);
          forwards.hide();
          defence.find('h5').text('Skaters');
          button.text('Back to split mode');
        })
        .fail(showError)
        .always(function () { setBusy(false); });
    } else {
      // Publish both split bodies together; a failed request keeps joined mode.
      $.when($.getJSON(statsUrl(mode, 'd')), $.getJSON(statsUrl(mode, 'f')))
        .done(function (defenceResult, forwardsResult) {
          render(defence, defenceResult[0]);
          render(forwards, forwardsResult[0]);
          forwards.show();
          defence.find('h5').text('Defencemen');
          button.text('D + F in one table');
        })
        .fail(showError)
        .always(function () { setBusy(false); });
    }
  });
});
