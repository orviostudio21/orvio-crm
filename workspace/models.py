from datetime import timedelta
from decimal import Decimal
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

class Owned(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, editable=False)
    created_at = models.DateTimeField('criado em', auto_now_add=True)
    class Meta:
        abstract = True
        ordering = ['-created_at', '-pk']

    def validate_owner(self, *relations):
        for relation in relations:
            if getattr(self, relation+'_id', None) and getattr(self, relation).owner_id != self.owner_id:
                raise ValidationError({relation:'O registro deve pertencer ao seu espaço.'})

class Event(Owned):
    description = models.CharField('ação', max_length=300)
    def __str__(self):
        return self.description


class Contact(Owned):
    name = models.CharField('nome', max_length=120)
    company = models.CharField('empresa', max_length=120, blank=True)
    email = models.EmailField('e-mail')
    phone = models.CharField('telefone', max_length=30, blank=True)
    notes = models.TextField('observações', blank=True, max_length=3000)
    class Meta(Owned.Meta):
        constraints = [models.UniqueConstraint(fields=['owner','email'], name='unique_contact_email')]
    def __str__(self):
        return self.name

class Deal(Owned):
    STAGES = [('lead','Prospecção'), ('qualified','Qualificação'), ('proposal','Proposta'), ('negotiation','Negociação'), ('won','Ganho'), ('lost','Perdido')]
    title = models.CharField('oportunidade', max_length=140)
    contact = models.ForeignKey(Contact, verbose_name='contato', on_delete=models.PROTECT)
    value = models.DecimalField('valor estimado', max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    stage = models.CharField('etapa', max_length=16, choices=STAGES, default='lead')
    expected_close = models.DateField('previsão de fechamento', default=timezone.localdate)
    notes = models.TextField('observações', blank=True, max_length=3000)
    class Meta(Owned.Meta):
        constraints = [models.CheckConstraint(condition=Q(value__gt=0), name='positive_deal_value')]
    def clean(self):
        self.validate_owner('contact')
    def __str__(self):
        return self.title

class Task(Owned):
    STATUS = [('open','Pendente'), ('done','Concluída')]
    title = models.CharField('atividade', max_length=140)
    deal = models.ForeignKey(Deal, verbose_name='oportunidade', on_delete=models.PROTECT, blank=True, null=True)
    due_date = models.DateField('prazo', default=timezone.localdate)
    status = models.CharField('status', choices=STATUS, max_length=10, default='open')
    notes = models.TextField('observações', blank=True, max_length=3000)
    class Meta(Owned.Meta):
        ordering = ['due_date','pk']
    def clean(self):
        self.validate_owner('deal')
    def __str__(self):
        return self.title
