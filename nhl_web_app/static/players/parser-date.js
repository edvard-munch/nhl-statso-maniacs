let monthsFirstDayIndexes = {
    'Aug': 0,
    'Sep': 31,
    'Oct': 61,
    'Nov': 92,
    'Dec': 122,
    'Jan': 153,
    'Feb': 184,
    'Mar': 213,
    'Apr': 244,
    'May': 274,
    'Jun': 305,
    'Jul': 335,
  }

$.tablesorter.addParser({
  id: 'date',
  is: function() {
    return false;
  },

  format: function(s) {
    dateSplitted = s.split(' ')
    return monthsFirstDayIndexes[dateSplitted[0]] + Number(dateSplitted[1])
 },

     type: 'numeric'
  });
