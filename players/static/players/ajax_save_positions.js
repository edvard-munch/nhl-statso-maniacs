var frmPos = $('.js-save-positions');
frmPos.submit(function () {
  $.ajax({
    type: frmPos.attr('method'),
    url: frmPos.attr('action'),
    dataType: 'json',
    data: frmPos.serialize(),

    success: function(data) {
      if (data['authenticated']) {
          alertType = 'alert-primary';
          $('.js_pos').html(data['ajax_upd_pos']);
      } else {
          alertType = 'alert-danger';
      }
      $('.js-positions-alert').show().attr('class', `alert ${alertType} js-positions-alert`).fadeTo(2000, 500).slideUp(500).appendTo(frmPos);
      $('.js-positions-message').html(data['message']);
    },
    timeout: 3000,

    error: function (data, jqXHR, exception) {
              $('.js-positions-alert').show().attr('class', 'alert alert-danger js-positions-alert');
              $('.js-positions-message').html('Error! Please, try again');
           },
    });
    return false;
  });
