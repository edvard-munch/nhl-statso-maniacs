let skaters_log_table = $("#skaters_log_table").data;
$("#skaters_log_table").data['pageSizesArr'] = [];
$("#skaters_log_table").data['pageNumbersArr'] = [];
skaters_log_table['statType'] = 'skt_log';
skaters_log_table['ascOrderCols'] = [0, 1, 3];
skaters_log_table['headersCount'] = $("#skaters_log_table > thead > tr:first > th").length;

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

$('table').on("sortEnd", function(){
    $(this).trigger('pageSet', 1);
});

// SKATERS LOG
$("#skaters_log_table")
  .tablesorter({
    headers: headers(skaters_log_table['headersCount'], skaters_log_table['ascOrderCols'], [], []),
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
   ajaxUrl: 'http://127.0.0.1:8000/ajax_fav_players_gamelog?/page={page+1}/size={size}/{sort:col}/{filter:fcol}',
   customAjaxUrl: function(table, url) {
     urlParts = url.split('?');
     url = urlParts[0] + `/${skaters_log_table['statType']}` + urlParts[1];

     return adjustUrl(url, $("#skaters_log_table"));
   },
});
