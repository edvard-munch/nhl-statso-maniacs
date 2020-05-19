$('div.expander').click(function() {
	content_div = $(this).next('.content');
    content_div.toggle();
    div_id = content_div.attr('id');

    if (div_id) {
    	div = $(`#${div_id}`);
		set_to_widest(div);
    };
});

function set_to_widest(div) {
	labels = div.find('label');
	if (labels.is(':visible')) {
	  var widest_label = Math.max.apply(Math, labels.map(function() { 
	  return $(this).width(); 
    }));
	  labels.width(widest_label);
};
};

$('p.expander').click(function(){
	$('.content').toggle();
});
