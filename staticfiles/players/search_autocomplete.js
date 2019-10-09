$(document).ready(function(){
    $("#txtSearch").autocomplete({
        source: "/ajax_calls/search/",
        minLength: 2,
        appendTo: "#navbarToggle",
      });
});
