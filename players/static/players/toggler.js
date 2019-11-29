$('div.expander').click(function(){
    $(this).next('.content').toggle();
});

$('p.expander').click(function(){
	$('.content').toggle();
});

