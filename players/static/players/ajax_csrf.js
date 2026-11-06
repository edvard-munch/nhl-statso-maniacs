// Use the masked DOM token, including when the CSRF cookie is HTTP-only or session-backed.
$.ajaxPrefilter(function (options, originalOptions, xhr) {
  const safeMethods = /^(GET|HEAD|OPTIONS|TRACE)$/;
  const method = (options.type || 'GET').toUpperCase();
  const target = new URL(options.url, window.location.href);
  if (!safeMethods.test(method) && target.origin === window.location.origin) {
    const token = document.querySelector('#ajax-csrf-token [name="csrfmiddlewaretoken"]');
    if (token) xhr.setRequestHeader('X-CSRFToken', token.value);
  }
});
