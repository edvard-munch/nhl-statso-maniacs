$("#tab1")
  .tablesorter({
    headers: {
      0: { sorter: false, filter: false },
      1: { filter: false },
      3: { filter: false },
  },
  // sortList: [[11,1],[10,0],[14,1],[15,1]],
  widgets: ['indexFirstColumn', 'filter'],

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
