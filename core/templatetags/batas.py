from django import template
from django.templatetags.static import static
from django.utils.html import format_html

register = template.Library()


@register.simple_tag
def icon(name: str, extra: str = ""):
    """An icon from the static sprite. Decorative: screen readers skip it."""
    return format_html(
        '<svg class="i {}" aria-hidden="true" focusable="false"><use href="{}#{}"></use></svg>',
        extra,
        static("core/icons.svg"),
        name,
    )
