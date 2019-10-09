from django import template
from django.template.defaulttags import register
from num2words import num2words


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def to_int(value):
    return int(value)


@register.filter
def to_str(value):
    return str(value)


@register.filter
def ordinal_num(value):
    return num2words(value, to="ordinal_num")
