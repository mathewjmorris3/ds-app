from decimal import Decimal
from django import template

register = template.Library()


@register.filter
def currency(value):
    if value is None:
        return "—"
    amount = Decimal(value)
    return f"{'-' if amount < 0 else ''}${abs(amount):,.2f}"
