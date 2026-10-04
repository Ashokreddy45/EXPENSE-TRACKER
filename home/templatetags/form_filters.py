from django import template
register = template.Library()

@register.filter(name='add_attr')
def add_attr(field, args):
    """Allows adding attributes like class or placeholder to form fields from template."""
    bits = [arg.strip() for arg in args.split(",")]
    attrs = {}
    for bit in bits:
        if ":" in bit:
            key, val = bit.split(":")
            attrs[key.strip()] = val.strip()
    return field.as_widget(attrs=attrs)
