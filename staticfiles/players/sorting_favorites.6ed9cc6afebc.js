$("#tab1")
  .tablesorter({
      widgets: ['filter'],
      headers: {
          2: {sorter: false},
      },
  })

.tablesorterPager({
   container: $(".pager-gl-log"),
   size: 15,
   output: '{page} / {totalPages}',
   savePages : false,
   fixedHeight: false,
});


$("#tab2")
  .tablesorter({
      widgets: ['filter'],
      headers: {
          2: {sorter: false},
      },
  })

.tablesorterPager({
   container: $(".pager-sk-log"),
   size: 15,
   output: '{page} / {totalPages}',
   savePages : false,
   fixedHeight: false,
});


$("#tab3")
  .tablesorter({
    headers: {
        0: {sorter: false, filter: false},
        1: {filter: false},
    },
    widgets: ['indexFirstColumn', 'filter'],
  })

.tablesorterPager({
   container: $(".pager-gl-tot"),
   size: 15,
   output: '{page} / {totalPages}',
   savePages : false,
   fixedHeight: false,
});


$("#tab4")
  .tablesorter({
    headers: {
        0: {sorter: false, filter: false},
        1: {filter: false},
    },
    widgets: ['indexFirstColumn', 'filter'],
  })

.tablesorterPager({
   container: $(".pager-sk-tot"),
   size: 15,
   output: '{page} / {totalPages}',
   savePages : false,
   fixedHeight: false,
});


$("#tab5")
  .tablesorter({
    headers: {
        0: {sorter: false, filter: false},
        1: {filter: false},
    },
    widgets: ['indexFirstColumn', 'filter'],
  })

.tablesorterPager({
   container: $(".pager-sk-avg"),
   size: 15,
   output: '{page} / {totalPages}',
   savePages : false,
   fixedHeight: false,
});
