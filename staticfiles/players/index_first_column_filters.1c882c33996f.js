$.tablesorter.addWidget({
    id: "indexFirstColumn",
    format: function(table) {
        $(table).find("tr:not(:last-child) td:first-child").each(function(index){
            $(this).text(index+1);
        });
    }
    });
