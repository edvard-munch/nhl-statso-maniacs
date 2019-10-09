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
