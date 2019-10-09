// NOT USING YET

<input type="hidden" id="refreshed" value="false">
$(window).load(function(){
    if ($('#refreshed').val() == "false") {
      $('#refreshed').val("true");
    }
    else {
      $('#refreshed').val("false");
      location.reload();
    }
  });
