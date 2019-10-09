$("#tab1")
  .tablesorter({
      headers: {
          0: {sorter: false, filter: false},
          1: {filter: false},
      },
      widgets: ['indexFirstColumn', 'filter'],

      widgetOptions: {
          filter_functions: {
            8: {
              "< 180"      : function(e, n, f, i, $r, c, data) {return n < 180;},
              "180 to 220" : function(e, n, f, i, $r, c, data) {return n >= 180 && n <= 220;},
              "> 220"      : function(e, n, f, i, $r, c, data) {return n > 220;},
            }
          },
          filter_hideFilters: true,
      }
})

.tablesorterPager({
    container: $(".pager-s"),
    size: 25,
    output: '{page} / {totalPages}',
    savePages: false,
    fixedHeight: false,
});

$("#but1").click(function(){
      $('.tablesorter-filter-row').toggle();
});
