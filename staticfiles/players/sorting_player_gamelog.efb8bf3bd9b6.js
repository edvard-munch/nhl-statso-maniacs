$("#tab1").
    tablesorter({
      headers: {
          0: {sorter: false},
      },
    })

.tablesorterPager({
    container: $(".pager-g"),
    size: 25,
    output: '{page} / {totalPages}',
    savePages: false,
    fixedHeight: false,
});

$("#tab2").
    tablesorter({
      headers: {
          0: {sorter: false},
      },
    })

.tablesorterPager({
    container: $(".pager-s"),
    size: 25,
    output: '{page} / {totalPages}',
    savePages: false,
    fixedHeight: false,
});
