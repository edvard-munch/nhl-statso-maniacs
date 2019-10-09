$(function() {

$.tablesorter.addWidget({
    id: "indexFirstColumn",
    format: function(table) {
        $(table).find("tr td:first-child").each(function(index){
            $(this).text(index+1);
        });
    }
    });

  $.tablesorter.addParser({
    id: 'last-name',
    is: function() {
      return false;
    },
    format: function(str) {
      var parts = (str || '').split(/\s+/),
        last = parts.pop();
      parts.unshift(last);
      return parts.join(' ');
    },
    // set type, either numeric or text
    type: 'text'
  });

$.tablesorter.addParser({
  id: 'height',
  is: function(s) {
    //$.tablesorter uses this function to determine if this colum is of this type
    return false;
  },
  format: function(s) {
    //now we'll just return the number of inches and $.tablesorter will sort them as integers
    var matches = s.match(new RegExp(/^(\d{1})\' (\d{1,2})\"/), 'g');
    return parseInt(matches[1]) * 12 + parseInt(matches[2]);
  }
  });

  $("#tab1")
    .tablesorter({
    headers: {
      0: { sorter: false }
    },
    sortList: [[11,1]],
    // sortList: [[11,1],[10,0],[14,1],[15,1]],
    widgets: ['indexFirstColumn']
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
    sortList: [[13,1]],
    // sortList: [[13,1],[10,0],[11,1],[14,1]],
    widgets: ['indexFirstColumn']
    })

    .tablesorterPager({
     container: $(".pager-s"),
     size: 25,
     output: '{page} / {totalPages}',
     savePages : false,
    });
  });
