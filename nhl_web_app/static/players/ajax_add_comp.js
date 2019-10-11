$(function () {
$('body').on('click', '.js-compare-add', function() {
  var btn = $(this);

  $.ajax({
    type: 'GET',
    url: btn.attr('href'),
    success: function(data) {
      if (data['authenticated']) {
        if (data['comp_quota_reached']) {
          alertType = 'alert-danger';

       } else {

          alertType = 'alert-primary';
          btn.html('IN COMPARISON');
          btn.attr('title', 'Remove from comparison');
          btn.switchClass('sm-button js-compare-add', 'act-button js-compare-del');
        }
       } else {
          alertType = 'alert-danger';
       }
         $('.js-comp-alert').show().attr('class', `alert ${alertType} js-comp-alert`).fadeTo(2000, 500).slideUp(500).insertBefore(btn);
         $('.js-comp-message').html(data['message']);
    }
    });

    return false;
  });
});
