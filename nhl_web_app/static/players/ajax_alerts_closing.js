$(".alert").on("close.bs.alert", function () {
      $(".alert").hide();
      return false;
});

// $('body').on('hideAlert', '.alert-primary', function() {
//   $(".js-comp-alert").fadeTo(2000, 500).slideUp(500);
// })

// $(".alert-primary").fadeTo(2000, 500).slideUp(500);

// var target = document.querySelector('#note-alert.alert-primary');
//
// var observer = new MutationObserver(function(mutations) {
//   alert('Attributes changed!');
// });
//
// observer.observe(target, {
//   attributes: true
// });
