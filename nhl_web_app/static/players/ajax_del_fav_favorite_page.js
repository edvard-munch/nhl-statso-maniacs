const pageSize = 25;

const delAlert=$('\
  <div class="alert alert-primary js-fav-alert" role="alert">\
    <span class="js-fav-message"></span>\
    <button type="button" class="close" data-dismiss="alert" aria-label="Close">\
      <span aria-hidden="true">&times;</span>\
    </button>\
  </div>\
');

$(function () {
$('body').on('click', '.js-fav-del', function() {
  var btn = $(this);

  $.ajax({
    type: 'GET',
    url: btn.attr('href'),
    success: function(data) {
      let table = btn.closest('table');
      let pager = table.find('.pager');
      let currPage = table[0].config.pager.page;
      let currentRow = btn.closest("tr");
      let nextRow = currentRow.next();
      let nextRowButton = nextRow.find('.js-fav-del');
      let beforeLastRow = table.find("tbody tr").eq(-2);
      let beforeLastRowButton = beforeLastRow.find('.js-fav-del');

      delAlert.insertAfter(table);

      let object = '';
      if (nextRow.length > 0) {
          object = nextRowButton;

      } else {
          object = beforeLastRowButton;
      };

      // needed to remove a current row to correctly count a number of rows for
      // pageEmpty variable
      currentRow.remove();
      let pageEmpty = $('tbody tr:visible', table).length === 0;

      $('.js-fav-alert').show().attr('class', 'alert alert-primary js-fav-alert').fadeTo(2000, 500).slideUp(500).insertAfter(object);
      $('.js-fav-message').html(data['message']);

      if (currPage > 0 && pageEmpty) {
        // Updating to a current page instead of previous because pagerUpdate
        // is using 1-based index and table[0].config.pager.page is using 0-based index
          table.trigger('pagerUpdate', currPage);
      } else {
          setTimeout(function() {   // for alert to be shown for enough time
            table.trigger('pagerUpdate')
          }, 1000);
      };

      table.find("tbody tr:not(.filtered) td:first-child").each(function(index) {
          $(this).text(index + 1);
      });

      let tab = $('.comparison-button.current-tab');
      let numberOfRows = '';

      if (table.attr('id').includes('skaters')) {
          numberOfRows = data['skaters_count'];
          tab.html(buttonMod('SKATERS', numberOfRows));
      } else if (table.attr('id').includes('goalies')) {
          numberOfRows = data['goalies_count'];
          tab.html(buttonMod('GOALIES', numberOfRows));
      };

      if (numberOfRows <= pageSize) {
          pager.hide();
      };
    }
    });
    return false;
  });
});

function buttonMod(word, number) {
    return `${word} (${number})`;
};
