$(function () {
$('body').on('click', '.js-fav-add', function() {
  var btn = $(this);

  $.ajax({
    type: 'GET',
    url: btn.attr('href'),
    success: function(data) {
      if (data['authenticated']) {
        if (data['fav_quota_reached']) {
          alertType = 'alert-danger';

       } else {

          alertType = 'alert-primary';
          btn.attr({ title: 'Remove from favorites'});
          btn.switchClass('js-fav-add', 'js-fav-del');
          btn.children().switchClass('far', 'fas');
        }
      } else {
          alertType = 'alert-danger';
      }
       $('.js-fav-alert').show().attr('class', `alert ${alertType} js-fav-alert`).fadeTo(20000, 500).slideUp(500).insertAfter(btn);
       $('.js-fav-message').html(data['message']);
    }
    });

    return false;
  });
});
