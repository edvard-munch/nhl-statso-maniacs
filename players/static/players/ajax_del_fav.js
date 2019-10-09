$(function () {
$('body').on('click', '.js-fav-del', function() {
  var btn = $(this);

  $.ajax({
    type: 'GET',
    url: btn.attr('href'),

    success: function(data) {
      $('.js-fav-alert').show().attr('class', 'alert alert-primary js-fav-alert').fadeTo(2000, 500).slideUp(500).insertAfter(btn);
      $('.js-fav-message').html(data['message']);

      btn.attr('title', 'Add to favorites');
      btn.switchClass('js-fav-del', 'js-fav-add');
      btn.children().switchClass('fas', 'far');
    }
    });

    return false;
  });
});
