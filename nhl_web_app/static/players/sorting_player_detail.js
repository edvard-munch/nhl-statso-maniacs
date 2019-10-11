$("#tab1, #tab2").
    tablesorter({
        sortInitialOrder: 'desc',
        sortRestart: true,
        widgets: ['StaticRow'],
        headers: {
          0: {sortInitialOrder: 'asc'},
          1: {sortInitialOrder: 'asc'},
        },
    });
