$('textarea').keyup(updateCount);
$('textarea').keydown(updateCount);
$('textarea').on('input', updateCount);

function updateCount() {
    var cs = $(this).val().length;
    $('#characters').text(cs);
}
