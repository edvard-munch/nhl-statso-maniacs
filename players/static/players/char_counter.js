let maxLength = 400;
var $count = $('textarea').text().length;

showCount($count);

$('textarea').keyup(updateCount);
$('textarea').keydown(updateCount);
$('textarea').on('input', updateCount);

function updateCount() {
    var $count = $(this).val().length;
    showCount($count);
};

function showCount(count) {
    $('#characters').html(`<b>${maxLength - count}</b> characters left`);
};

$("#note-reset").click(function() {
      showCount($count);
  });
