$.tablesorter.addWidget({
    id: "indexFirstColumn",
    format: function(table) {
        $(table).find("tr td:first-child").each(function(index){
            $(this).text(index+1);
        });
    }
    });
