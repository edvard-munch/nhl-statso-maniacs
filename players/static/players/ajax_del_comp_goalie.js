$(function () {
$('body').on('click', '.js-compare-del_goalie', function() {
  var btn = $(this);

  $.ajax({
    type: 'GET',
    url: btn.attr('href'),
    success: function(data) {
      $('.js-comp-alert').show().attr('class', 'alert alert-primary js-comp-alert').fadeTo(2000, 500).slideUp(500).insertBefore(btn);
      $('.js-comp-message').html(data['message']);

      $('#js_goalies_switch').html(data['goalies_button']);
      $("#goalies_table tbody").html(data.compare_goalies);

      if ($('#goalies_table tbody td').length === 0) {
        $("#goalies_table").hide();
        $("#js_goalies_block").hide();
        $("#js_goalies_switch").css('pointer-events', 'none');
        $("#goalies_h5").html('No goalies').show();
      };
    }
    });

    return false;
  });
});
