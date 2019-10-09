var frmNote = $('.js-save-note');
frmNote.submit(function () {
  $.ajax({
    type: frmNote.attr('method'),
    url: frmNote.attr('action'),
    dataType: 'json',
    data: frmNote.serialize(),

    success: function(data) {
        if (data['authenticated']) {
          alertType = 'alert-primary';
        } else {
          alertType = 'alert-danger';
        }
        $('.js-note-alert').show().attr('class', `alert ${alertType} js-note-alert`).fadeTo(2000, 500).slideUp(500).appendTo(frmNote);
        $('.js-note-message').html(data['message']);
    },
    timeout: 3000,

    error: function (data, jqXHR, exception) {
            $('.js-note-alert').show().attr('class', 'alert alert-danger js-note-alert').appendTo(frmNote);
            $('.js-note-message').html('Error! Please, try again');
        },
    });
    return false;
  });
