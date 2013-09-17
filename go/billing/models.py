from decimal import *

from django.db import models
from django.utils.translation import ugettext_lazy as _

import go.billing.settings as app_settings


class TagPool(models.Model):
    """Tag pool definition"""

    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    def __unicode__(self):
        return self.name


class BaseCost(models.Model):
    """Define the base cost for a single message"""

    DIRECTION_CHOICES = (
        ('Inbound', 'Inbound'),
        ('Outbound', 'Outbound'),
    )

    tag_pool = models.ForeignKey(TagPool)
    message_direction = models.CharField(max_length=20,
                                         choices=DIRECTION_CHOICES)

    message_cost = models.IntegerField(
        default=0, help_text=_("The base message cost in cents."))

    markup_percent = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0,
        help_text=_("The markup percentage."))

    @property
    def resulting_price(self):
        """Return the resulting price in cents"""
        markup = self.message_cost * self.markup_percent / Decimal(100.0)
        return self.message_cost + markup.to_integral_value()

    @property
    def credit_cost(self):
        """Return the calculated cost in credits"""
        return self.resulting_price * app_settings.CREDIT_CONVERSION_FACTOR

    def __unicode__(self):
        return u"%s (%s)" % (self.tag_pool, self.message_direction)


class Account(models.Model):
    """Represents a user account"""

    user = models.ForeignKey('auth.User')
    account_number = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    credit_balance = models.IntegerField(default=0)
    alert_threshold = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0,
        help_text=_("Low-credits notification will be sent when the "
                    "credit balance reaches the alert threshold percentage"))

    alert_credit_balance = models.IntegerField(default=0)

    def __unicode__(self):
        return self.account_number


class CostOverride(models.Model):
    """Allows for a per-account cost override"""

    account = models.ForeignKey(Account)
    tag_pool = models.ForeignKey(TagPool)
    message_direction = models.CharField(max_length=20,
                                         choices=BaseCost.DIRECTION_CHOICES)

    message_cost = models.IntegerField(
        default=0, help_text=_("The message cost in cents."))

    markup_percent = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.0,
        help_text=_("The markup percentage."))

    @property
    def resulting_price(self):
        """Return the resulting price in cents"""
        markup = self.message_cost * self.markup_percent / Decimal(100.0)
        return self.message_cost + markup.to_integral_value()

    @property
    def credit_cost(self):
        """Return the calculated cost in credits"""
        return self.resulting_price * app_settings.CREDIT_CONVERSION_FACTOR

    def __unicode__(self):
        return u"%s (%s)" % (self.tag_pool, self.message_direction)


class Transaction(models.Model):
    """Represents a credit transaction"""

    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Completed', 'Completed'),
        ('Failed', 'Failed'),
        ('Reversed', 'Reversed'),
    )

    account_number = models.CharField(max_length=100)
    tag_pool_name = models.CharField(max_length=100, blank=True)
    message_direction = models.CharField(max_length=20, blank=True)
    message_cost = models.IntegerField(blank=True, null=True)
    markup_percent = models.DecimalField(max_digits=10, decimal_places=2,
                                         blank=True, null=True)

    credit_factor = models.DecimalField(max_digits=10, decimal_places=2,
                                        blank=True, null=True)

    credit_amount = models.IntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                              default='Pending')

    created = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now=True)

    def __unicode__(self):
        return unicode(self.pk)