$.tablesorter.addWidget({
    id: "indexFirstColumn",
    format: function(table) {
        $(table).find("tbody tr:not(.filtered) td:first-child").each(function(index){
            $(this).text(index+1);
        });
    }
    });
