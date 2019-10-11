// DON'T NEED NOW

$(function () {
var pages = parseInt(document.getElementById('val').textContent);

var pageBack = $('.page_back')
var pageForward = $('.page_forward')
var pageNumber = 1;
var firstPage = '1';

$('body').on('click', '.page_forward', function() {
  pageNumber++

  if (pageNumber > 1) {
    pageBack.show();
  };

  if (pageNumber >= pages) {
    pageForward.hide();
  };

  url = pageForward.attr('href').replace(firstPage, pageNumber);
  console.log(url)
  $.ajax({
    type: 'GET',
    url: url,
    success: function(data) {
        console.log(data);
        $('.json').html(data)
      }
    });
    return false;
  });


  $('body').on('click', '.page_back', function() {
    pageNumber--

    if (pageNumber < 2) {
      pageBack.hide();
    };

    if (pageNumber <= pages) {
      pageForward.show();
    };

    url = pageBack.attr('href').replace(firstPage, pageNumber);
    console.log(url)
    $.ajax({
      type: 'GET',
      url: url,
      success: function(data) {
          console.log(data);
          $('.json').html(data)
        }
      });
      return false;
    });
});
