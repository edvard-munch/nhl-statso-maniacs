$(function () {
$('body').on('click', '.js-compare-del_skater', function() {
  var btn = $(this);

  $.ajax({
    type: 'GET',
    url: btn.attr('href'),
    success: function(data) {
      $('.js-comp-alert').show().attr('class', 'alert alert-primary js-comp-alert').fadeTo(2000, 500).slideUp(500).insertBefore(btn);
      $('.js-comp-message').html(data['message']);

      $('#js_skaters_switch').html(data['skaters_button']);
      $("#skaters_table tbody").html(data.compare_skaters);

      if ($('#skaters_table tbody td').length === 0) {
        $("#skaters_table").hide();
        $("#js_skaters_block").hide();
        $("#js_skaters_switch").css('pointer-events', 'none');
        $("#skaters_h5").html('No skaters').show();
      };
    }
    });

    return false;
  });
});
