// DEFS
$(function () {
$('body').on('click', '#js_switch_to_avg_defencemen', function() {
  var btn = $(this);
  url = btn.attr('href').replace('default', 'd')
  $.ajax({
    type: 'GET',
    url: url,
    success: function(data) {
      $("#tab2 tbody").html(data.stats);
      $("#tab2").trigger("update");
      $('#js_switch_to_avg_defencemen').html('See total stats')
      $('#js_switch_to_avg_defencemen').attr('id', 'js_switch_to_tot_defencemen')
    }
    });
    return false;
  });

$('body').on('click', '#js_switch_to_tot_defencemen', function() {
  var btn = $(this);
  url = btn.attr('href').replace('avg', 'tot').replace('default', 'd')
  $.ajax({
    type: 'GET',
    url: url,
    success: function(data) {
      $("#tab2 tbody").html(data.stats);
      $("#tab2").trigger("update");
      $('#js_switch_to_tot_defencemen').html('See average stats')
      $('#js_switch_to_tot_defencemen').attr('id', 'js_switch_to_avg_defencemen')
    }
    });
    return false;
  });
});

// FORWARDS
$(function () {
$('body').on('click', '#js_switch_to_avg_forwards', function() {
  var btn = $(this);
  url = btn.attr('href').replace('default', 'f')
  $.ajax({
    type: 'GET',
    url: url,
    success: function(data) {
      $("#tab3 tbody").html(data.stats);
      $("#tab3").trigger("update");
      $('#js_switch_to_avg_forwards').html('See total stats')
      $('#js_switch_to_avg_forwards').attr('id', 'js_switch_to_tot_forwards')
    }
    });
    return false;
  });

$('body').on('click', '#js_switch_to_tot_forwards', function() {
  var btn = $(this);
  url = btn.attr('href').replace('avg', 'tot').replace('default', 'f')
  $.ajax({
    type: 'GET',
    url: url,
    success: function(data) {
      $("#tab3 tbody").html(data.stats);
      $("#tab3").trigger("update");
      $('#js_switch_to_tot_forwards').html('See average stats')
      $('#js_switch_to_tot_forwards').attr('id', 'js_switch_to_avg_forwards')
    }
    });
    return false;
  });
});


// TOGETHER
$(function () {
$('body').on('click', '#js_switch_to_join', function() {
  var btn = $(this);
  url = btn.attr('href')

  html_cont = 'See total stats'

  if($('#js_switch_to_avg_defencemen').length > 0) {
      url = url.replace('avg', 'tot');
      html_cont = 'See average stats'
  };

  url = url.replace('default', 't')

  $.ajax({
    type: 'GET',
    url: url,
    success: function(data) {
      $("#tab2 tbody").html(data.stats);
      $("#tab2").trigger("update");
      $("#js_forwards_sect").hide();
      $("div#js_defencemen_sect h5").html('Skaters');
      $('#js_switch_to_join').html('Back to split mode')
      $('#js_switch_to_join').attr('id', 'js_switch_to_split')

      $('#js_switch_to_avg_defencemen').html('See average stats')
      $('#js_switch_to_tot_defencemen').html('See total stats')
      $('#js_switch_to_avg_defencemen').attr('id', 'js_switch_to_avg_joined')
      $('#js_switch_to_tot_defencemen').attr('id', 'js_switch_to_tot_joined')
    }
    });
    return false;
  });

  $('body').on('click', '#js_switch_to_split', function() {
    var btn = $(this);
    url = btn.attr('href')
    console.log(url);
    if($('#js_switch_to_avg_joined').length > 0) {
        url = url.replace('avg', 'tot');
    };
    console.log(url);
    url = url.replace('default', 'd')
    console.log(url);
    $.ajax({
      type: 'GET',
      url: url,
      success: function(data) {
        $("#tab2 tbody").html(data.stats);
        $("#tab2").trigger("update");
        $("#js_forwards_sect").show();
        $("div#js_defencemen_sect h5").html('Defencemen');
        $('#js_switch_to_split').html('D + F in one table')
        $('#js_switch_to_split').attr('id', 'js_switch_to_join')
        $('#js_switch_to_avg_joined').attr('id', 'js_switch_to_avg_defencemen')
        $('#js_switch_to_tot_joined').attr('id', 'js_switch_to_tot_defencemen')
      }
      });
      return false;
    });

  $('body').on('click', '#js_switch_to_tot_joined', function() {
    var btn = $(this);
    url = btn.attr('href').replace('avg', 'tot').replace('default', 't')
    $.ajax({
      type: 'GET',
      url: url,
      success: function(data) {
        $("#tab2 tbody").html(data.stats);
        $("#tab2").trigger("update");
        $('#js_switch_to_tot_joined').html('See average stats')
        $('#js_switch_to_tot_joined').attr('id', 'js_switch_to_avg_joined')
      }
      });
      return false;
    });

  $('body').on('click', '#js_switch_to_avg_joined', function() {
    var btn = $(this);
    url = btn.attr('href').replace('default', 't')
    $.ajax({
      type: 'GET',
      url: url,
      success: function(data) {
        $("#tab2 tbody").html(data.stats);
        $("#tab2").trigger("update");
        $('#js_switch_to_avg_joined').html('See total stats')
        $('#js_switch_to_avg_joined').attr('id', 'js_switch_to_tot_joined')
      }
      });
      return false;
    });

});
