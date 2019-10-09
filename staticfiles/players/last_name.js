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
