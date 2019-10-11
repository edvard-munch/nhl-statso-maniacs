$(function () {
$('body').on('click', '.js-compare-del', function() {
  var btn = $(this);

  $.ajax({
    type: 'GET',
    url: btn.attr('href'),
    success: function(data) {
      $('.js-comp-alert').show().attr('class', 'alert alert-primary js-comp-alert').fadeTo(2000, 500).slideUp(500).insertBefore(btn);
      $('.js-comp-message').html(data['message']);

      btn.html('COMPARE');
      btn.attr('title', 'Add to comparison');
      btn.switchClass('act-button js-compare-del', 'sm-button js-compare-add');
    }
    });

    return false;
  });
});
