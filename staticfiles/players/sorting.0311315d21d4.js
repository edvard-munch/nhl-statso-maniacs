$("#tab3, #tab4")
  .tablesorter({
      widgets: ['staticRow'],
  });

$("#tab1")
  .tablesorter({
    headers: {
      0: { sorter: false, filter: false },
      1: { filter: false },
      3: { filter: false },
  },
  // sortList: [[11,1],[10,0],[14,1],[15,1]],
  widgets: ['indexFirstColumn', 'filter'],

  widgetOptions: {
    filter_functions : {
        6 : {
          "< 180"      : function(e, n, f, i, $r, c, data) { return n < 180; },
          "180 to 220" : function(e, n, f, i, $r, c, data) { return n >= 180 && n <= 220; },
          "> 220"     : function(e, n, f, i, $r, c, data) { return n > 220; },
        },
      }
    }
  //     filter_reset: ".reset",
  //     filter_cssFilter: ["", "", "browser-default"]
    })

  .tablesorterPager({
  container: $(".pager-g"),
  size: 15,
  output: '{page} / {totalPages}',
  savePages : false,
  fixedHeight: false,
  });

$("#tab2")
  .tablesorter({
  headers: {
    0: { sorter: false }
  },
  // sortList: [[13,1],[10,0],[11,1],[14,1]],
  widgets: ['indexFirstColumn']
  })

  .tablesorterPager({
   container: $(".pager-s"),
   size: 25,
   output: '{page} / {totalPages}',
   savePages : false,
   fixedHeight: false,
  });
