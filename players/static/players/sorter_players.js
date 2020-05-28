// http://127.0.0.1:8000/ajax_players/tot/page%3D1/size%3D25/col/fcol/rookie_filter%3D/teams_filter%3DBOS/
// // why = got replaced with  %3D in case od BOS?

// http://127.0.0.1:8000/ajax_players/tot/page=1/size=25/col/fcol/rookie_filter=/teams_filter=CAR

let statType = 'tot';
$(".js_rookie_filter_gls").hide();
$('.js_reset_goalies').hide();
$("#js_external_filter_goalies").hide();

skaters_table = $("#skaters_table").data();
goalies_table = $("#goalies_table").data();
skaters_table['pageSizesArr'] = [];
skaters_table['pageNumbersArr'] = [];
goalies_table['pageSizesArr'] = [];
goalies_table['pageNumbersArr'] = [];

skaters_table['ascOrderCols'] = [...Array(12).keys()];
skaters_table['headersCount'] = $("#skaters_table > thead > tr:first > th").length;
skaters_table['allCols'] = [...Array(skaters_table['headersCount']).keys()];
goalies_table['ascOrderCols'] = [...Array(12).keys()];
goalies_table['headersCount'] = $("#goalies_table > thead > tr:first > th").length;
goalies_table['allCols'] = [...Array(goalies_table['headersCount']).keys()];

function headers(headersCount, ascOrderCols, noSorterCols, noFilterCols) {
    let headers = {};
    for (let column = 0; column < headersCount; column++) {
        headers[column] = {}
        if (noSorterCols.includes(column)) {
            headers[column]['sorter'] = false
        };
        if (noFilterCols.includes(column)) {
            headers[column]['filter'] = false
        };
        if (ascOrderCols.includes(column)) {
            headers[column]['sortInitialOrder'] = 'asc'
        };
    };
    return headers;
};

function adjustUrl(url, table) {
  tablePagerConf = table[0].config.pager;
  table = table.data()
  table['currentPageSize'] = tablePagerConf.size;

  if (table['pageSizesArr'].length > 0){
      table['prevPageSize'] = table['pageSizesArr'][table['pageSizesArr'].length - 1];
  } else {
      table['prevPageSize'] = table['currentPageSize'];
  };

  table['pageSizesArr'].push(table['currentPageSize']);

  if (table['currentPageSize'] === 'all' || table['prevPageSize'] === 'all') {
    //pass
  } else {
      if (table['currentPageSize'] != table['prevPageSize']) {

          table['prevPage'] = parseInt(table['pageNumbersArr'][table['pageNumbersArr'].length - 1]);
          table['currentPage'] = (tablePagerConf.page + 1);
          start = table['prevPageSize'] * (table['prevPage'] - 1)
          table['nextPage'] = Math.floor(start / table['currentPageSize']) + 1;
          url = url.replace(`page=${table['currentPage'].toString()}`, `page=${table['nextPage']}`);
          tablePagerConf.page = table['nextPage'] - 1;
      }
    }

    let pageNumRegex = /page\=(\d{1,2})/gm;
    table['pageNumbersArr'].push(pageNumRegex.exec(url)[1]);
    return url;
};

function togglePager(filteredRows, pager, table, select) {
  if (filteredRows <= 25) {
    pager.hide();
    if (filteredRows < 1) {
      // $('<br><br><h5>No results matched the query</h5>').insertAfter($(this));
        table.hide();
    } else if (filteredRows > 0) {
        table.show();
    }
  } else if (filteredRows > 25) {
      pager.show();
      select.html(pageSizeOptions(filteredRows, table.data['currentPageSize']))
  }
};

function pageSizeOptions(filteredRows, selectedPageSize) {
  let pageSizeOptionsArr = [25, 50, 100, 200];
  let optionsHtml = '';
  let selected;
  let selectAll;
  let currOpts = [];
  for (const option of pageSizeOptionsArr) {
    if (option < filteredRows) {
        currOpts.push(option);
        if (option === selectedPageSize){
          selected = 'selected';
        } else {
          selected = '';
        }
        optionsHtml += `<option ${selected} value="${option}">${option}</option>`
    }
  }
  if (Math.max(...currOpts) < selectedPageSize){
    selectAll = 'selected';
  } else {
    selectAll = '';
  }
  return `${optionsHtml} <option ${selectAll} value="All">All</option>`
};


// let ranges = {
//   'ageRanges': [],
//   'weightRanges': [],
// }


function skatersTotals() {
$("#skaters_table")
  .tablesorter({
      sortInitialOrder: 'desc',
      sortRestart: true,
      headers: headers(skaters_table['headersCount'], skaters_table['ascOrderCols'], [0], []),

      widgets: ['filter'],
      widgetOptions: {

        filter_selectSource : {
            ".filter-select" : function() { return null; }
        },

      filter_reset: '.js_reset_skaters',
      filter_external: ".search_skaters",
  }
})

.tablesorterPager({
    container: $(".pager-s"),
    size: 25,
    output: '{page} / {totalPages}',
    savePages: false,
    ajaxUrl: 'http://127.0.0.1:8000/ajax_players?/page={page+1}/size={size}/{sort:col}/{filter:fcol}',
    customAjaxUrl: function(table, url) {
      let addUrl = '';

      urlParts = url.split('?');
      url = urlParts[0] + `/${statType}` + urlParts[1];

      url = adjustUrl(url, $("#skaters_table"));

      if ($("#skaters_table").data('rookie_filter_value')) {
            url += '/rookie_filter=' + $("#skaters_table").data('rookie_filter_value');

            // $("#age-range").on("slide", function() {
            //     // console.log($(this).attr('id'));
            //     url += $(this).attr('id');
            //     // console.log(`AGE RANGE CHANGED: ${url}`);
            //     return url;
            // });

            // $("#weight-range").on("slide", function() {
            //     // console.log($(this).attr('id'));
            //     url += $(this).attr('id');
            //     // console.log(`WEIGHT RANGE CHANGED: ${url}`);
            //     return url;
            // });

            // console.log(`BEFORE RETURN: ${url}`);     
            // return url;
      } else {
            url += '/rookie_filter=';
            // console.log(addUrl);

            // $("#age-range").on("slide", function() {
            //     // console.log($(this).attr('id'));
            //     url += $(this).attr('id');
            //     console.log(`AGE RANGE CHANGED: ${url}`);
            //     return url
            // });

            // $("#weight-range").on("slide", function() {
            //     // console.log($(this).attr('id'));
            //     url += $(this).attr('id');
            //     // console.log(`WEIGHT RANGE CHANGED: ${url}`);
            //     return url
            // });

            // console.log(`BEFORE RETURN: ${url}`); 
            // return url;
         };

         if ($("#skaters_table").data('team_checkboxradio')) {
            radio = JSON.stringify($("#skaters_table").data('team_checkboxradio'));
            url += '/checkbox_filter=' + radio + '/'; 
         } else {
            url += '/checkbox_filter=/'
         };

         return url;
    },

    ajaxObject: {
        success: function(data) {
        $(data['fav_alert_div']).prependTo('body');
        // console.log(data['age_range'])
        // console.log(data['weight_range'])
        // ranges['ageRanges'].push(data['age_range'])
        // ranges['weightRanges'].push(data['weight_range'])

        // if age_range changes:
        // sliderFilter(data['weight_range'], "#weight", "#weight-range")
        // if one range filter is used: change other than that one
        // THINK OF OTHER WAY. YOU ARE REALLY COULD NOT run slidefilter just once,
        // it needs to be ran when you updated your filter, hence sending AJAX request
        // SOMEHOW catch which slider have been actually slided, use mousehover, keyup or something

        $('#teams').html(data['all_teams']); //IT'S probably rewrites changed class for goalies team filters
        $('#nations').html(data['all_nations']);
        $('#positions').html(data['all_positions']);

        $(".checkbox_button").checkboxradio( { icon:false } );

        set_to_widest($('#teams'));
        set_to_widest($('#nations'));
        set_to_widest($('#positions'));

        sliderFilter(data['initial_age_range'], data['age_range'], "#age", "#age-range")
        sliderFilter(data['initial_weight_range'], data['weight_range'], "#weight", "#weight-range")
        sliderFilter(data['initial_height_range'], data['height_range'], "#height", "#height-range", data['height_values'])

        togglePager(data['total'], $('.pager-s'), $('#skaters_table'), $('#skaters_table_pager_options'));

        // options = data['filter_select'];
        // for (let column = 3; column <= 5; column++) {
        //     $.tablesorter.filter.buildSelect($("#skaters_table"), column, options[column], true);
        // };
        },
        dataType: 'json',
        type: 'GET'
      },
    });
};


// set all labels widths equal the widest one
function set_to_widest(div) {
  labels = div.find('label');
  if (labels.is(':visible')) {
    var widest_label = Math.max.apply(Math, labels.map(function() { 
      return $(this).width(); 
    }));

    labels.width(widest_label);
  };
};


function goaliesTotals() {
$("#goalies_table")
.tablesorter({
    sortInitialOrder: 'desc',
    sortRestart: true,
    // headers: headers(goalies_table['headersCount'], goalies_table['ascOrderCols'], [0], goalies_table['allCols']),
    headers: headers(goalies_table['headersCount'], goalies_table['ascOrderCols'], [0], []),

    widgets: ['filter'],
    widgetOptions: {
      filter_functions: {

      },

      filter_selectSource : {
          ".filter-select" : function() { return null; }
      },
    filter_reset: '.js_reset_goalies',
    filter_external: '.search_goalies',
}
})

.tablesorterPager({
  container: $(".pager-g"),
  size: 25,
  output: '{page} / {totalPages}',
  savePages: false,
  fixedHeight: false,
  ajaxUrl: 'http://127.0.0.1:8000/ajax_players/gls/page={page+1}/size={size}/{sort:col}/{filter:fcol}',
  customAjaxUrl: function(table, url) {
    url = adjustUrl(url, $("#goalies_table"));

    if ($("#goalies_table").data('rookie_filter_value')) {
          url += '/rookie_filter=' + $("#goalies_table").data('rookie_filter_value');
    } else {
          url += '/rookie_filter=';
  };
     if ($("#goalies_table").data('team_checkboxradio')) {
      url += '/checkbox_filter=' + $("#goalies_table").data('team_checkboxradio') + '/'; 
   } else {
      url += '/checkbox_filter=/'
   };

   return url
   },

  ajaxObject: {
      success: function(data) {
        $(data['fav_alert_div']).prependTo('body');

        sliderFilter(data['initial_age_range'], data['age_range'], "#age", "#age-range")
        sliderFilter(data['initial_weight_range'], data['weight_range'], "#weight", "#weight-range")
        sliderFilter(data['initial_height_range'], data['height_range'], "#height", "#height-range", data['height_values'])

        // $('#teams').html(data['all_teams']); THE reason for rewriting reset_gls classes
        togglePager(data['total'], $('.pager-g'), $('#goalies_table'), $('#goalies_table_pager_options'))
        // options = data['filter_select'];
        // for (let column = 3; column <= 5; column++) {
        //     $.tablesorter.filter.buildSelect($("#goalies_table"), column, options[column], true);
        // };
      },
      dataType: 'json',
      type: 'GET'
      },

    });
};

$('table').bind("sortEnd", function(){
    $(this).trigger('pageSet', 1);
  });


$('body').on('change', '.js_rookie_filter_skt', function(){
    let checked = $(this).is(":checked");
    $("#skaters_table").data('rookie_filter_value', checked).trigger('pagerUpdate', 1);
    if (checked) {
      $(this).attr('title', 'Show all players')
    } else {
      $(this).attr('title', 'Show rookies only')
    };
});

$('body').on('change', '.js_rookie_filter_gls', function(){
    let checked = $(this).is(":checked");
    $("#goalies_table").data('rookie_filter_value', checked).trigger('pagerUpdate', 1);
    if (checked) {
      $(this).attr('title', 'Show all players')
    } else {
      $(this).attr('title', 'Show rookies only')
    };
});

function resetRookieFilter(event) {
  $(event.data.filter).prop('checked', false);
  $(event.data.table).show();
  $(event.data.table).data('rookie_filter_value', $(this).is(":checked"))//.trigger('pagerUpdate');
};

// MAKE A PRETTY FITERS checkbox
// REFACTOR FILTERS IN A VIEW

let teams = [];
let nations = [];
let positions = [];
let checkbox_obj = {};


// REMOVES ALL teams from options
$('body').on('change', '.team_checkboxradio_skt', {'table': $("#skaters_table"), 'array': teams, 'key': 'teams'}, checkbox);
$('body').on('change', '.nation_checkboxradio_skt', {'table': $("#skaters_table"), 'array': nations, 'key': 'nations'}, checkbox);
$('body').on('change', '.position_checkboxradio_skt', {'table': $("#skaters_table"), 'array': positions, 'key': 'positions'}, checkbox);

$('body').on('change', '.team_checkboxradio_gls', {'table': $("#goalies_table"), 'array': teams, 'column': 'team_checkboxradio'}, checkbox);

function checkbox(event){
  if (event.target.checked) {
    event.data.array.push(event.target.value);
  } else {
      event.data.array.splice($.inArray(event.target.value, event.data.array), 1); 
  };

  checkbox_obj[event.data.key] = event.data.array;
  event.data.table.data('team_checkboxradio', checkbox_obj).trigger('pagerUpdate', 1);
};


function resetCheckboxFilter(event) {
  $(event.data.filter).prop('checked', false);
  $(event.data.table).show();
  event.data.array.length = 0;
  checkbox_obj[event.data.key] = event.data.array;

  $(event.data.table).data('team_checkboxradio', checkbox_obj).trigger('pagerUpdate');
};

$('body').on('click', '.js_reset_skaters', {'table': '#skaters_table', 'filter': '.js_rookie_filter_skt'}, resetRookieFilter);
$('body').on('click', '.js_reset_skaters', {'table': '#skaters_table', 'filter': '.team_checkboxradio_skt', 'array': teams, 'key': 'teams'}, resetCheckboxFilter);
$('body').on('click', '.js_reset_skaters', {'table': '#skaters_table', 'filter': '.nation_checkboxradio_skt', 'array': nations, 'key': 'nations'}, resetCheckboxFilter);
$('body').on('click', '.js_reset_skaters', {'table': '#skaters_table', 'filter': '.position_checkboxradio_skt', 'array': positions, 'key': 'positions'}, resetCheckboxFilter);


$('body').on('click', '.js_reset_goalies', {table: '#goalies_table', filter: '.js_rookie_filter_gls'}, resetRookieFilter);
// $('body').on('click', '.js_reset_goalies', {table: '#goalies_table', filter: '.team_checkboxradio_gls', array: 'teams'}, resetCheckboxFilter);
// $('body').on('click', '.js_reset_goalies', {table: '#goalies_table', filter: '.nation_checkboxradio_skt', array: 'nations'}, resetCheckboxFilter);
// $('body').on('click', '.js_reset_goalies', {table: '#goalies_table', filter: '.position_checkboxradio_skt', array: 'positions'}, resetCheckboxFilter);


// THERE IS NO AJAX call IF there is second time in the session I push the button
// and there is 2 calls when you add a reset skaters button, strangely for BOTH tables
// THE REASON IS HTML REWRITING TEAMS FROM AJAX callback function
$('body').on('click', '#js_gls_stats', function(){
  // $('.js_reset_skaters').click(); // gls classes switches back to skt AS a RESULT of resetting skaters table
  $('.search_skaters').toggleClass("search_skaters search_goalies");

  $('.team_checkboxradio_skt').toggleClass("team_checkboxradio_skt team_checkboxradio_gls");
  // you need to put goalies ranges after this step
  $('#js_gls_stats').hide();
  $("#skaters_table").hide();
  $("#goalies_table").show();
  goaliesTotals();
 $(".js_rookie_filter_skt").hide();
  $(".js_rookie_filter_gls").show();
  $('.js_reset_skaters').hide();
  $('.js_reset_goalies').show();
  $("#js_external_filter_skaters").hide();
  $("#js_external_filter_goalies").show();
  $('#js_avg_stats').html('See skaters stats');
  $('#js_avg_stats').attr('id', 'js_skaters_stats');
  $('#js_total_stats').html('See skaters stats');
  $('#js_total_stats').attr('id', 'js_skaters_stats');

});

$('body').on('click', '#js_skaters_stats', function(){
  statType = 'tot';
  $('.js_reset_goalies').click();
  $('.search_goalies').toggleClass('search_goalies search_skaters');
  $('.team_checkboxradio_gls').toggleClass("team_checkboxradio_gls team_checkboxradio_skt");
  // you need to put goalies ranges after this step
  $('#js_gls_stats').show();
  $("#goalies_table").hide();
  $("#skaters_table").show();
  $(".js_rookie_filter_gls").hide()
  $(".js_rookie_filter_skt").show();
  $('.js_reset_goalies').hide();
  $('.js_reset_skaters').show();
  $("#js_external_filter_goalies").hide();
  $("#js_external_filter_skaters").show();
  $("#skaters_table").trigger('pagerUpdate');
  $(this).attr('id', 'js_avg_stats');
  $(this).html('See average stats');
});

$('body').on('click', '#js_total_stats', function(){
  statType = 'tot';
  $("#skaters_table").trigger('pagerUpdate');
  $(this).attr('id', 'js_avg_stats');
  $(this).html('See average stats');
});

$('body').on('click', '#js_avg_stats', function(){
  statType = 'avg';
  $("#skaters_table").trigger('pagerUpdate');
  $(this).attr('id', 'js_total_stats');
  $(this).html('See total stats');
});

$('body').on('close.bs.alert', '#pls-fav-alert', function(event) {
  event.preventDefault();
  $('.js-fav-alert').hide();
});


// convert values to euro system before sending them to URL !!!
// or parse the values in django
function sliderFilter(min_max, values, label, sliderObject, optional_obj=false) {

  $(sliderObject).slider({
    range: true,
    min: min_max[0],
    max: min_max[1],
    step: 1,
    values: values,

    slide: function(event, ui) {
      if (isObject(optional_obj)) {
          if (!(ui.values[0] in optional_obj) || !(ui.values[1] in optional_obj)) return false;
          $(label).val(optional_obj[ui.values[0]] + " - " + optional_obj[ui.values[1]]);

      } else {
          if (optional_obj) {

            if (!(optional_obj.includes(ui.values[0])) || !(optional_obj.includes(ui.values[1]))) return false;
            $(label).val(ui.values[0] + " - " + ui.values[1]);

          } else {
            $(label).val(ui.values[0] + " - " + ui.values[1]);
          }
      };

      // maybe use filterUpdate or something?
      $('table:visible').trigger('update');
    }
  }); // $(sliderObject).slider

  // needed for initial loading of a label
  $(label).val($(sliderObject).slider("values", 0) +
    " - " + $(sliderObject).slider("values", 1));

if (isObject(optional_obj)) {
  val_min = optional_obj[$(sliderObject).slider("values", 0)]
  val_max = optional_obj[$(sliderObject).slider("values", 1)]

  $(label).val(val_min + " - " + val_max);

};

  // without this line it's just resetting my css style for cursor to a default instead of a pointer
  $(".ui-slider, .ui-slider-handle").css('cursor', 'pointer');

 }; //function sliderFilter


function isObject(obj) {
  return obj != null && obj.constructor.name === "Object"
}

skatersTotals();
$("#goalies_table").hide();

// sliderFilter([18, 42], "#age", "#age-range")
// sliderFilter([160, 280], "#weight", "#weight-range")


// GET RANGE CHANGES, CATCH RANGE SLIDES
// since it's not possible to catch 'input' for readonly

// console.log($('label[for="NYI"]').width());
// console.log($('label[for="CAR"]').width());
