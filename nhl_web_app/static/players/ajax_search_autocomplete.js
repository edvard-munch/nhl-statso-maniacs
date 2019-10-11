$(document).ready(function(){
    $("#txtSearch").autocomplete({
        source: "/ajax_calls/search/",
        minLength: 2,
        appendTo: "#navbarToggle",
    })

.data("ui-autocomplete")
    ._renderItem = function (ul, item) {
    return $("<li></li>")
    .data("item.autocomplete", item)
    .append(item.label)
    .appendTo(ul);
};

});
