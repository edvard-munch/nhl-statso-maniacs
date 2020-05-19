const favoritesParam = 'fav_filt=True';
const rookiesParam = 'rookie_filter=';
const goaliesLogParam = 'gls_log';
const skatersLogParam = 'skt_log';
const goaliesTotalsParam = 'gls';
const skatersTotalsParam = 'tot';
const skatersAveragesParam = 'avg';
let statType = '';

let clickedButtons = [$('#js_switch_to_skaters_gamelog')]
let tables = [$("#js_skaters_log_table")]
let js_goalies_log_table = $("#js_goalies_log_table").data;
let js_skaters_log_table = $("#js_skaters_log_table").data;

$("#js_skaters_log_table").data['pageSizesArr'] = [];
$("#js_skaters_log_table").data['pageNumbersArr'] = [];
$("#js_goalies_log_table").data['pageSizesArr'] = [];
$("#js_goalies_log_table").data['pageNumbersArr'] = [];

js_goalies_log_table['statType'] = 'gls_log';
js_goalies_log_table['ascOrderCols'] = [0, 1, 3];
js_goalies_log_table['headersCount'] = $("#js_goalies_log_table > thead > tr:first > th").length;

js_skaters_log_table['statType'] = 'skt_log';
js_skaters_log_table['ascOrderCols'] = [0, 1, 3];
js_skaters_log_table['headersCount'] = $("#js_skaters_log_table > thead > tr:first > th").length;

$("#js_goalies_block, #js_goalies_log_table, #js_goalies_total_table, #js_skaters_total_table").hide();
$("#js_skaters_averages_table").hide();
$(".select").hide();
$('.js_external_filter_skaters_log').show();

// HELPER FUNCTIONS
function headers(headersCount, ascOrderCols, noSorterCols, noFilterCols) {
    let headers = {};
    for (let column = 0; column < headersCount; column++) {
        headers[column] = {}
        if (noSorterCols.includes(column)) {
            headers[column]['sorter'] = false
        };
        if (noFilterCols.includes(column)) {
            headers[column]['filter'] = false
        };
        if (ascOrderCols.includes(column)) {
            headers[column]['sortInitialOrder'] = 'asc'
        };
    };
    return headers;
};

function prevClicked() {
  return clickedButtons[clickedButtons.length - 2];
};

function prevTable() {
  return tables[tables.length - 2];
};

function adjustUrl(url, table) {
  tablePagerConf = table[0].config.pager;
  table = table.data
  table['currentPageSize'] = tablePagerConf.size;

  if (table['pageSizesArr'].length > 0){
      table['prevPageSize'] = table['pageSizesArr'][table['pageSizesArr'].length - 1];
  } else {
      table['prevPageSize'] = table['currentPageSize'];
  };

  table['pageSizesArr'].push(table['currentPageSize']);

  if (table['currentPageSize'] === 'all' || table['prevPageSize'] === 'all') {
    //pass
  } else {
      if (table['currentPageSize'] != table['prevPageSize']) {

          table['prevPage'] = parseInt(table['pageNumbersArr'][table['pageNumbersArr'].length - 1]);
          table['currentPage'] = (tablePagerConf.page + 1);
          start = table['prevPageSize'] * (table['prevPage'] - 1)
          table['nextPage'] = Math.floor(start / table['currentPageSize']) + 1;
          url = url.replace(`page=${table['currentPage'].toString()}`, `page=${table['nextPage']}`);
          tablePagerConf.page = table['nextPage'] - 1;
      }
    }
    let pageNumRegex = /page\=(\d{1,2})/gm;
    table['pageNumbersArr'].push(pageNumRegex.exec(url)[1]);
    return url;
};

function pageSizeOptions(filteredRows) {
  let pageSizeOptionsArr = [25, 50, 100, 200];
  let optionsHtml = '';
  for (const option of pageSizeOptionsArr) {
    if (option < filteredRows) {
      optionsHtml += `<option value="${option}">${option}</option>`
    }
  }
  return `${optionsHtml} <option value="All">All</option>`
};

function togglePager(filteredRows, pager, table, select) {
  if (filteredRows <= 25) {
    pager.hide();
  if (filteredRows < 1) {
      // $('<br><br><h5>No results matched the query</h5>').insertAfter($(this));
        table.hide();
    } else if (filteredRows > 0) {
        table.show();
    }
  }
     else if (filteredRows > 25) {
      table.show();
      pager.show();
      select.html(pageSizeOptions(filteredRows));
  };
};

// PAGE 1 WHEN RESORT
$('table').on("sortEnd", function(){
    $(this).trigger('pageSet', 1);
});

// console.log(js_skaters_log_table['headersCount'])

// SKATERS GAMELOG TABLESORTER
function skatersGamelog() {
$("#js_skaters_log_table")
  .tablesorter({
    headers: headers(js_skaters_log_table['headersCount'], js_skaters_log_table['ascOrderCols'], [], []),
    sortInitialOrder: 'desc',
    sortRestart: true,
    widgets: ['filter'],
    widgetOptions: {
        filter_external: ".js_external_filter_skaters_log",
        filter_columnFilters: false,
    },
  })

.tablesorterPager({
   container: $(".pager-skt-log"),
   savePages: false,
   size: 25,
   output: '{page} / {totalPages}',
   ajaxUrl: `http://127.0.0.1:8000/ajax_fav_players_gamelog/${skatersLogParam}/page={page+1}/size={size}/{sort:col}/{filter:fcol}`,
   customAjaxUrl: function(table, url) {
     return adjustUrl(url, $("#js_skaters_log_table"));
   },
   ajaxObject: {
       success: function(data) {
         togglePager(data['total'], $('.pager-skt-log'), $('#js_skaters_log_table'), $('#skaters_games_options'));
       },
       dataType: 'json',
       type: 'GET'
     },
});
};

// SKATERS TOTALS and AVERAGES TABLESORTER
function skatersTotals() {
$("#js_skaters_total_table")
  .tablesorter({
      sortInitialOrder: 'desc',
      sortRestart: true,
      widgets: ['filter'],
      widgetOptions: {
          filter_external: ".js_external_filter_skaters_totals",
          filter_columnFilters: false,
      },
})

.tablesorterPager({
    container: $(".pager-skt-tot"),
    size: 25,
    output: '{page} / {totalPages}',
    savePages: false,
    ajaxUrl: `http://127.0.0.1:8000/ajax_players/${statType}/page={page+1}/size={size}/{sort:col}/{filter:fcol}/${rookiesParam}/${favoritesParam}`,
    customAjaxUrl: function(table, url) {
        return adjustUrl(url, $("#js_skaters_total_table"));
    },
    // needed to remove a pager when pager was hidden in average stats table before
    // switching to total stats
    ajaxObject: {
        success: function(data) {
          togglePager(data['total'], $('.pager-skt-tot'), $('#js_skaters_total_table'), $('#skaters_totals_options'));
        },
        dataType: 'json',
        type: 'GET'
      },
});
};

// GOALIES GAMELOG TABLESORTER
function goaliesGamelog() {
$("#js_goalies_log_table")
  .tablesorter({
    headers: headers(js_goalies_log_table['headersCount'], js_goalies_log_table['ascOrderCols'], [], []),
    sortInitialOrder: 'desc',
    sortRestart: true,
    widgets: ['filter'],
    widgetOptions: {
        filter_external: ".js_external_filter_goalies_log",
        filter_columnFilters: false,
    },
  })
.tablesorterPager({
   container: $(".pager-gls-log"),
   savePages: false,
   size: 25,
   output: '{page} / {totalPages}',
   ajaxUrl: `http://127.0.0.1:8000/ajax_fav_players_gamelog/${goaliesLogParam}/page={page+1}/size={size}/{sort:col}/{filter:fcol}`,
   customAjaxUrl: function(table, url) {
      return adjustUrl(url, $("#js_goalies_log_table"));
   },
   ajaxObject: {
       success: function(data) {
         togglePager(data['total'], $('.pager-gls-log'), $('#js_goalies_log_table'), $('#goalies_games_options'));
       },
       dataType: 'json',
       type: 'GET'
     },
});
};

// GOALIES TOTALS TABLESORTER
function goaliesTotals() {
$("#js_goalies_total_table")
  .tablesorter({
      sortInitialOrder: 'desc',
      sortRestart: true,
      widgets: ['filter'],
      widgetOptions: {
          filter_external: ".js_external_filter_goalies_totals",
          filter_columnFilters: false,
      },
})
.tablesorterPager({
    container: $(".pager-gls-tot"),
    size: 25,
    output: '{page} / {totalPages}',
    savePages: false,
    ajaxUrl: `http://127.0.0.1:8000/ajax_players/${goaliesTotalsParam}/page={page+1}/size={size}/{sort:col}/{filter:fcol}/${rookiesParam}/${favoritesParam}`,
    customAjaxUrl: function(table, url) {
        return adjustUrl(url, $("#js_goalies_total_table"));
    },
    ajaxObject: {
        success: function(data) {
          togglePager(data['total'], $('.pager-gls-tot'), $('#js_goalies_total_table'), $('#goalies_totals_options'));
        },
        dataType: 'json',
        type: 'GET'
      },
});
};

// INITIAL LOADING
skatersGamelog();

// MAIN SKATERS BUTTON CLICK
$('body').on('click', '#js_skaters_switch', function() {
  $("#js_goalies_block").hide();
  $("#js_skaters_block").show();
  let currTable = $("#js_skaters_log_table");
  currTable.show();
  $('#js_skaters_switch').addClass('current-tab')
  $('#js_goalies_switch').removeClass('current-tab')
  let btn = $('#js_switch_to_skaters_gamelog');
  clickedButtons.push(btn);
  tables.push(currTable);
  prevTable().hide();
  btn.addClass('current-tab');
  prevClicked().removeClass('current-tab');
  $('.select').hide();
  $('.js_external_filter_skaters_log').show();
  skatersGamelog();
});

// MAIN GOALIES BUTTON CLICK
$('body').on('click', '#js_goalies_switch', function() {
  $("#js_skaters_block").hide();
  $("#js_goalies_block").show();
  let currTable = $("#js_goalies_log_table");
  currTable.show();
  $('#js_goalies_switch').addClass('current-tab')
  $('#js_skaters_switch').removeClass('current-tab')
  let btn = $('#js_switch_to_goalies_gamelog');
  clickedButtons.push(btn);
  tables.push(currTable);
  prevTable().hide();
  btn.addClass('current-tab');
  prevClicked().removeClass('current-tab');
  $('.select').hide();
  $('.js_external_filter_goalies_log').show();
  goaliesGamelog();
});

// SKATERS GAMELOG CLICK
$(function() {
  $('body').on('click', '#js_switch_to_skaters_gamelog', function() {
      btn = $(this);
      clickedButtons.push(btn);
      let currTable = $("#js_skaters_log_table");
      currTable.show();
      tables.push(currTable);
      prevTable().hide();
      btn.addClass('current-tab');
      prevClicked().removeClass('current-tab');
      $('.select').hide();
      $('.js_external_filter_skaters_log').show();
      skatersGamelog();
  });
});

// SKATERS GAMELOG PAGER ON FILTER
$('#js_skaters_log_table').on('filterEnd', function(){
    let filteredRows = $(this)[0].config.filteredRows;
    // togglePager(filteredRows, $('.pager-skt-log'), $(this), $('#skaters_games_options'));
});

// SKATERS TOTALS CLICK
$(function() {
  $('body').on('click', '#js_switch_to_skaters_season_tot', function() {
      btn = $(this)
      statType = 'tot';
      clickedButtons.push(btn);
      let currTable = $("#js_skaters_total_table");
      currTable.show();
      tables.push(currTable);
      if (currTable.attr('id') !== prevTable().attr('id')) {
        prevTable().hide();
      };
      btn.addClass('current-tab');
      prevClicked().removeClass('current-tab');
      $('.select').hide();
      $('.js_external_filter_skaters_totals').show();
      skatersTotals();
  });
});

// SKATERS TOTALS PAGER ON FILTER
$('#js_skaters_total_table').on('filterEnd', function(){
    let filteredRows = $(this)[0].config.filteredRows;
    togglePager(filteredRows, $('.pager-skt-tot'), $(this), $('#skaters_totals_options'));
});

// SKATERS AVERAGES CLICK
$(function() {
  $('body').on('click', '#js_switch_to_skaters_season_avg', function() {
      statType = 'avg';
      btn = $(this);
      clickedButtons.push(btn);
      let currTable = $("#js_skaters_total_table");
      currTable.show();
      tables.push(currTable);
      if (currTable.attr('id') !== prevTable().attr('id')) {
        prevTable().hide();
      };
      btn.addClass('current-tab');
      prevClicked().removeClass('current-tab');
      $('.select').hide();
      $('.js_external_filter_skaters_totals').show();
      skatersTotals();
  });
});

// SKATERS AVERAGES PAGER ON FILTER
$('#js_skaters_averages_table').on('filterEnd', function(){
    let filteredRows = $(this)[0].config.filteredRows;
    togglePager(filteredRows, $('.pager-skt-avg'), $(this), $('#skaters_averages_options'));
});

// GOALIES GAMELOG CLICK
$(function() {
  $('body').on('click', '#js_switch_to_goalies_gamelog', function() {
      btn = $(this);
      clickedButtons.push(btn);
      let currTable = $("#js_goalies_log_table");
      currTable.show();
      tables.push(currTable);
      prevTable().hide();
      btn.addClass('current-tab');
      prevClicked().removeClass('current-tab');
      $('.select').hide();
      $('.js_external_filter_goalies_log').show();
      goaliesGamelog();
  });
});

// GOALIES GAMELOG PAGER ON FILTER
$('#js_goalies_log_table').on('filterEnd', function(){
    let filteredRows = $(this)[0].config.filteredRows;
    togglePager(filteredRows, $('.pager-gls-log'), $(this), $('#goalies_games_options'));
});

// GOALIES TOTALS CLICK
$(function() {
  $('body').on('click', '#js_switch_to_goalies_season_tot', function() {
      btn = $(this);
      clickedButtons.push(btn);
      let currTable = $("#js_goalies_total_table");
      currTable.show();
      tables.push(currTable);
      prevTable().hide();
      btn.addClass('current-tab');
      prevClicked().removeClass('current-tab');
      $('.select').hide();
      $('.js_external_filter_goalies_totals').show();
      goaliesTotals();
  });
});

// GOALIES TOTALS PAGER ON FILTER
$('#js_goalies_total_table').on('filterEnd', function(){
    let filteredRows = $(this)[0].config.filteredRows;
    togglePager(filteredRows, $('.pager-gls-tot'), $(this), $('#goalies_totals_options'));
});