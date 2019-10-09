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

tab1['ascOrderCols'] = [...Array(11).keys()];
tab1['headersCount'] = $("#tab1 > thead > tr:first > th").length;
tab2['headersCount'] = $("#tab2 > thead > tr:first > th").length;

$("#tab1").tablesorter({
    headers: headers(tab1['headersCount'], tab1['ascOrderCols'], [0, 1], []),
    sortInitialOrder: 'desc',
    sortRestart: true,
    widgets: ['indexFirstColumn'],
});

$("#tab2, #tab3").tablesorter({
    headers: headers(tab2['headersCount'], tab1['ascOrderCols'], [0, 1], []),
    sortInitialOrder: 'desc',
    sortRestart: true,
    widgets: ['indexFirstColumn'],
});
