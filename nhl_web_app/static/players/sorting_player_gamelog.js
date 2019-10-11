$("#tab1").
    tablesorter({
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
    })

.tablesorterPager({
    container: $(".pager-s"),
    size: 25,
    output: '{page} / {totalPages}',
    savePages: false,
    fixedHeight: false,
});
