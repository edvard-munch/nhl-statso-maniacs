let clickedButtons = []

function prevClicked() {
  return clickedButtons[clickedButtons.length - 2];
};

// RESET SKATERS
$(function() {
  $('body').on('click', '#js_clear_skaters_comparison', function customConfirm(e) {
    e.preventDefault();
    $.confirm({
      title: 'Confirmation',
      content: 'Are you sure you want to clear the skaters comparison list?',
      buttons: {
        confirm: function() {
          let btn = $('#js_clear_skaters_comparison');
          $.ajax({
            type: 'GET',
            url: btn.attr('href'),
            success: function(data) {
              $('#js_skaters_switch').html(data.skaters_button);
              $("#skaters_table tbody").html(data.compare_skaters);
              $("#skaters_table").hide();
              $("#js_skaters_block").hide();
              $("#js_skaters_switch").css('pointer-events', 'none');
              $("#skaters_h5").html('No skaters').show();
            },
          });
        },
        cancel: function() {
        }
      }
    });
  });
});

// RESET GOALIES
$(function() {
  $('body').on('click', '#js_clear_goalies_comparison', function customConfirm(e) {
    e.preventDefault();
    $.confirm({
      title: 'Confirmation',
      content: 'Are you sure you want to clear the goalies comparison list?',
      buttons: {
        confirm: function() {
          let btn = $('#js_clear_goalies_comparison');
          let url = btn.attr('href').replace('skaters', 'goalies');
          $.ajax({
            type: 'GET',
            url: url,
            success: function(data) {
              $('#js_goalies_switch').html(data.goalies_button);
              $("#goalies_table tbody").html(data.compare_goalies);
              $("#goalies_table").hide();
              $("#js_goalies_block").hide();
              $("#js_goalies_switch").css('pointer-events', 'none');
              $("#goalies_h5").html('No goalies').show();
            },
          });
        },
        cancel: function() {
        }
      }
    });
  });
});

// HIDE GOALIES TABLE
function hideGoaliesTable() {
  if ($('#skaters_table tbody td').length > 0) {
    $("#goalies_table").hide();
    $("#js_goalies_block").hide();
    clickedButtons.push($("#js_switch_to_skaters_season_tot"));
  };
};

function makeGoaliesTablePrimary() {
  if ($('#skaters_table tbody td').length === 0) {
    $('#js_goalies_switch').addClass('current-tab');
    let btn = $('#js_switch_to_goalies_season_tot');
    btn.addClass('current-tab');
    $('#js_goalies_switch').after('<br>');
    clickedButtons.push(btn);
  };
};

hideGoaliesTable();
makeGoaliesTablePrimary();

$('body').on('click', '#js_goalies_switch', function() {
  $("#skaters_h5").hide();
  $("#skaters_table").hide();
  $("#js_skaters_block").hide();
  $("#goalies_table").show();
  $("#js_goalies_block").show();
  $('#js_goalies_switch').addClass('current-tab')
  $('#js_skaters_switch').removeClass('current-tab')
  let btn = $('#js_switch_to_goalies_season_tot');
  clickedButtons.push(btn);
  btn.addClass('current-tab');
  prevClicked().removeClass('current-tab');
});

$('body').on('click', '#js_skaters_switch', function() {
  $("#goalies_h5").hide();
  $("#goalies_table").hide();
  $("#js_goalies_block").hide();
  $("#skaters_table").show();
  $("#js_skaters_block").show();
  $('#js_skaters_switch').addClass('current-tab');
  $('#js_goalies_switch').removeClass('current-tab');
  let btn = $('#js_switch_to_skaters_season_tot');
  clickedButtons.push(btn);
  btn.addClass('current-tab');
  prevClicked().removeClass('current-tab');
});

// SWITCH TO SKATERS SEASON AVERAGES
$(function() {
  $('body').on('click', '#js_switch_to_skaters_season_avg', function() {
    let btn = $(this);
    $.ajax({
      type: 'GET',
      url: btn.attr('href'),
      success: function(data) {
        clickedButtons.push(btn);
        $("#skaters_table tbody tr:gt(11)").remove();
        $("#skaters_table tbody").append(data.stats);
        $("#skaters_table").trigger("update");
        btn.addClass('current-tab');
        prevClicked().removeClass('current-tab');
      }
    });
    return false;
  });
});

// SWITCH TO SKATERS SEASON TOTAL
$(function() {
  $('body').on('click', '#js_switch_to_skaters_season_tot', function() {
    let btn = $(this);
    url = btn.attr('href').replace('season_avg', 'season_tot')

    $.ajax({
      type: 'GET',
      url: url,
      success: function(data) {
        clickedButtons.push(btn);
        $("#skaters_table tbody tr:gt(11)").remove();
        $("#skaters_table tbody").append(data.stats);
        $("#skaters_table").trigger("update");
        btn.addClass('current-tab');
        prevClicked().removeClass('current-tab');
      }
    });
    return false;
  });
});

// SWITCH TO SKATERS CAREER TOTAL
$(function() {
  $('body').on('click', '#js_switch_to_skaters_career_tot', function() {
    let btn = $(this);
    url = btn.attr('href').replace('season_avg', 'career_tot')
    $.ajax({
      type: 'GET',
      url: url,
      success: function(data) {
        clickedButtons.push(btn);
        $("#skaters_table tbody tr:gt(11)").remove();
        $("#skaters_table tbody").append(data.stats);
        $("#skaters_table").trigger("update");
        $('#js_switch_to_skaters_career_tot').addClass('current-tab')
        prevClicked().removeClass('current-tab');
      }
    });
    return false;
  });
});

// SWITCH TO SKATERS CAREER AVERAGES
$(function() {
  $('body').on('click', '#js_switch_to_skaters_career_avg', function() {
    let btn = $(this);
    url = btn.attr('href').replace('season_avg', 'career_avg');
    $.ajax({
      type: 'GET',
      url: url,
      success: function(data) {
        clickedButtons.push(btn);
        $("#skaters_table tbody tr:gt(11)").remove();
        $("#skaters_table tbody").append(data.stats);
        $("#skaters_table").trigger("update");
        $('#js_switch_to_skaters_career_avg').addClass('current-tab')
        prevClicked().removeClass('current-tab');
      }
    });
    return false;
  });
});


// SWITCH TO GOALIES SEASON TOTAL
$(function() {
  $('body').on('click', '#js_switch_to_goalies_season_tot', function() {
    let btn = $(this);
    url = btn.attr('href').replace('skaters', 'goalies').replace('season_avg', 'season_tot')
    $.ajax({
      type: 'GET',
      url: url,
      success: function(data) {
        clickedButtons.push(btn);
        $("#goalies_table tbody tr:gt(11)").remove();
        $("#goalies_table tbody").append(data.stats);
        $("#goalies_table").trigger("update");
        $('#js_switch_to_goalies_season_tot').addClass('current-tab')
        prevClicked().removeClass('current-tab');
      }
    });
    return false;
  });
});

// SWITCH TO GOALIES CAREER TOTAL
$(function() {
  $('body').on('click', '#js_switch_to_goalies_career_tot', function() {
    let btn = $(this);
    url = btn.attr('href').replace('skaters', 'goalies').replace('season_avg', 'career_tot')
    $.ajax({
      type: 'GET',
      url: url,
      success: function(data) {
        clickedButtons.push(btn);
        $("#goalies_table tbody tr:gt(11)").remove();
        $("#goalies_table tbody").append(data.stats);
        $("#goalies_table").trigger("update");
        $('#js_switch_to_goalies_career_tot').addClass('current-tab');
        prevClicked().removeClass('current-tab');
      }
    });
    return false;
  });
});
