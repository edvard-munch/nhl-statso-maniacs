let statType = 'tot';
$("#tab2").hide();
$(".js_rookie_filter_gls").hide();
$('.js_reset_goalies').hide();
$("#js_external_filter_goalies").hide();

tab1 = $("#tab1").data;
tab2 = $("#tab2").data;
tab1['pageSizesArr'] = [];
tab1['pageNumbersArr'] = [];
tab2['pageSizesArr'] = [];
tab2['pageNumbersArr'] = [];

tab1['ascOrderCols'] = [...Array(12).keys()];
tab1['headersCount'] = $("#tab1 > thead > tr:first > th").length;

tab2['ascOrderCols'] = [...Array(12).keys()];
tab2['headersCount'] = $("#tab2 > thead > tr:first > th").length;

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


$("#tab1")
  .tablesorter({
      sortInitialOrder: 'desc',
      sortRestart: true,
      headers: headers(tab1['headersCount'], tab1['ascOrderCols'], [0], [0, 1, 2]),
      widgets: ['filter'],
      widgetOptions: {
        filter_functions: {
          7: {
            "< 180"      : function(e, n, f, i, $r, c, data) {return n < 180;},
            "180 to 220" : function(e, n, f, i, $r, c, data) {return n >= 180 && n <= 220;},
            "> 220"      : function(e, n, f, i, $r, c, data) {return n > 220;},
          }
        },

        filter_selectSource : {
            ".filter-select" : function() { return null; }
        },

      filter_reset: '.js_reset_skaters',
      filter_external : "#js_external_filter_skaters",
  }
})

.tablesorterPager({
    container: $(".pager-s"),
    size: 25,
    output: '{page} / {totalPages}',
    savePages: false,
    ajaxUrl: 'http://127.0.0.1:8000/ajax_players?/page={page+1}/size={size}/{sort:col}/{filter:fcol}',
    customAjaxUrl: function(table, url) {
      urlParts = url.split('?');
      url = urlParts[0] + `/${statType}` + urlParts[1];

      url = adjustUrl(url, $("#tab1"));

      if ($("#tab1").data('filter_value')) {
            url += '/rookie_filter=' + $("#tab1").data('filter_value');
            return url
      };
            url += '/rookie_filter=';
            return url;
    },

    ajaxObject: {
        success: function(data) {
        $(data['fav_alert_div']).prependTo('body');

        togglePager(data['total'], $('.pager-s'), $('#tab1'), $('#tab1_pager_options'));

        options = data['filter_select'];
          for (let column = 3; column <= 5; column++) {
              $.tablesorter.filter.buildSelect($("#tab1"), column, options[column], true);
          };
        },
        dataType: 'json',
        type: 'GET'
      },
    });

function togglePager(filteredRows, pager, table, select) {
  if (filteredRows <= 25) {
    pager.hide();
    if (filteredRows < 1) {
      // $('<br><br><h5>No results matched the query</h5>').insertAfter($(this));
        table.hide();
    } else if (filteredRows > 0) {
        table.show();
    }
  } else if (filteredRows > 25) {
      pager.show();
      select.html(pageSizeOptions(filteredRows, table.data['currentPageSize']))
  }
};

function pageSizeOptions(filteredRows, selectedPageSize) {
  let pageSizeOptionsArr = [25, 50, 100, 200];
  let optionsHtml = '';
  let selected;
  let selectAll;
  let currOpts = [];
  for (const option of pageSizeOptionsArr) {
    if (option < filteredRows) {
        currOpts.push(option);
        if (option === selectedPageSize){
          selected = 'selected';
        } else {
          selected = '';
        }
        optionsHtml += `<option ${selected} value="${option}">${option}</option>`
    }
  }
  if (Math.max(...currOpts) < selectedPageSize){
    selectAll = 'selected';
  } else {
    selectAll = '';
  }
  return `${optionsHtml} <option ${selectAll} value="All">All</option>`
};

$("#tab2")
.tablesorter({
    sortInitialOrder: 'desc',
    sortRestart: true,
    headers: headers(tab2['headersCount'], tab2['ascOrderCols'], [0], [0, 1, 2, 3]),
    widgets: ['filter'],
    widgetOptions: {
      filter_functions: {

      },

      filter_selectSource : {
          ".filter-select" : function() { return null; }
      },
    filter_reset: '.js_reset_goalies',
    filter_external : "#js_external_filter_goalies",
}
})

.tablesorterPager({
  container: $(".pager-g"),
  size: 25,
  output: '{page} / {totalPages}',
  savePages: false,
  fixedHeight: false,
  ajaxUrl: 'http://127.0.0.1:8000/ajax_players/gls/page={page+1}/size={size}/{sort:col}/{filter:fcol}',
  customAjaxUrl: function(table, url) {
    url = adjustUrl(url, $("#tab2"));

    if ($("#tab2").data('filter_value')) {
          url += '/rookie_filter=' + $("#tab2").data('filter_value');
          return url;
    };
          url += '/rookie_filter=';
          return url;
  },

  ajaxObject: {
      success: function(data) {
        $(data['fav_alert_div']).prependTo('body');
        togglePager(data['total'], $('.pager-g'), $('#tab2'), $('#tab2_pager_options'))
        options = data['filter_select'];

        for (let column = 3; column <= 5; column++) {
            $.tablesorter.filter.buildSelect($("#tab2"), column, options[column], true);
        };
      },
      dataType: 'json',
      type: 'GET'
    },
  });

$('table').bind("sortEnd", function(){
    $(this).trigger('pageSet', 1);
  });

$('body').on('change', '.js_rookie_filter_skt', function(){
    let checked = $(this).is(":checked");
    $("#tab1").data('filter_value', checked).trigger('pagerUpdate', 1);
    if (checked) {
      $(this).attr('title', 'Show all players')
    } else {
      $(this).attr('title', 'Show rookies only')
    };
});

$('body').on('change', '.js_rookie_filter_gls', function(){
    let checked = $(this).is(":checked");
    $("#tab2").data('filter_value', checked).trigger('pagerUpdate', 1);
    if (checked) {
      $(this).attr('title', 'Show all players')
    } else {
      $(this).attr('title', 'Show rookies only')
    };
});

$('.js_reset_skaters').on('click', function(){
  $('.js_rookie_filter_skt').prop('checked', false);
  $("#tab1").data('filter_value', $(this).is(":checked")).trigger('pagerUpdate');
});

$('.js_reset_goalies').on('click', function(){
  $('.js_rookie_filter_gls').prop('checked', false);
  $("#tab2").data('filter_value', $(this).is(":checked")).trigger('pagerUpdate');
});

$('body').on('click', '#js_total_stats', function(){
  statType = 'tot'
  $("#tab1").trigger('pagerUpdate');
  $(this).attr('id', 'js_avg_stats');
  $(this).html('See average stats');
});

$('body').on('click', '#js_avg_stats', function(){
  statType = 'avg'
  $("#tab1").trigger('pagerUpdate');
  $(this).attr('id', 'js_total_stats');
  $(this).html('See total stats');
});

$('body').on('click', '#js_gls_stats', function(){
  $('#js_gls_stats').hide();
  $("#tab1").hide();
  $("#tab2").show();
  $(".js_rookie_filter_skt").hide();
  $(".js_rookie_filter_gls").show();
  $('.js_reset_skaters').hide();
  $('.js_reset_goalies').show();
  $("#js_external_filter_skaters").hide();
  $("#js_external_filter_goalies").show();
  $('#js_avg_stats').html('See skaters stats');
  $('#js_avg_stats').attr('id', 'js_skaters_stats');
  $('#js_total_stats').html('See skaters stats');
  $('#js_total_stats').attr('id', 'js_skaters_stats');
});

$('body').on('click', '#js_skaters_stats', function(){
  statType = 'tot';
  $('#js_gls_stats').show();
  $("#tab2").hide();
  $("#tab1").show();
  $(".js_rookie_filter_gls").hide()
  $(".js_rookie_filter_skt").show();
  $('.js_reset_goalies').hide();
  $('.js_reset_skaters').show();
  $("#js_external_filter_goalies").hide();
  $("#js_external_filter_skaters").show();
  $("#tab1").trigger('pagerUpdate');
  $(this).attr('id', 'js_avg_stats');
  $(this).html('See average stats');
});

$('body').on('close.bs.alert', '#pls-fav-alert', function(event){
  event.preventDefault();
  $('.js-fav-alert').hide();
});
