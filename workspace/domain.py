from datetime import datetime, timedelta, time
from decimal import Decimal
from django.db.models import Sum
from django.utils import timezone
from .models import *

def money(value):
    return 'R$ ' + f'{value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

def total(queryset, field):
    return queryset.aggregate(value=Sum(field))['value'] or Decimal('0')

def series(items):
    peak = max([float(value) for label,value in items] + [1])
    return [{'label':label, 'value':float(value), 'display':money(value), 'percent':round(float(value) / peak * 100, 2)} for label,value in items]

def panel_item(obj, title, subtitle, value='', status=''):
    return {'pk':obj.pk, 'title':title, 'subtitle':subtitle, 'value':value, 'status':status}

def config(model, label, singular, icon, columns, headers, search, status=None, help=''):
    return {'model':model, 'label':label, 'new_label':singular, 'icon':icon, 'columns':columns, 'headers':headers, 'search':search, 'status':status, 'choices':list(model._meta.get_field(status).choices) if status else [], 'help':help, 'numeric':[i for i,field in enumerate(columns) if field in ('value','amount','price','balance','opening_balance','duration','limit','spent')]}


REGISTRY = {
 'contacts':config(Contact,'Contatos','Novo contato','◎',['name','company','email','phone'],['Nome','Empresa','E-mail','Telefone'],['name','company','email'],help='Mantenha os dados da pessoa com quem você conversa.'),
 'deals':config(Deal,'Oportunidades','Nova oportunidade','▤',['title','contact','value','stage','expected_close'],['Oportunidade','Contato','Valor','Etapa','Previsão'],['title','contact__name','contact__company'],status='stage',help='Associe um contato, informe o valor e acompanhe a etapa do negócio.'),
 'tasks':config(Task,'Atividades','Nova atividade','✓',['title','deal','due_date','status'],['Atividade','Oportunidade','Prazo','Status'],['title','deal__title'],status='status',help='Defina o próximo passo e marque como concluído quando terminar.'),
}

def dashboard_data(user):
    today = timezone.localdate()
    deals = Deal.objects.filter(owner=user)
    active = deals.exclude(stage__in=['won','lost'])
    tasks = Task.objects.filter(owner=user, status='open')
    late = tasks.filter(due_date__lt=today).count()
    metrics = [
      {'label':'Pipeline aberto','value':money(total(active,'value')),'note':f'{active.count()} oportunidades em andamento'},
      {'label':'Negócios ganhos','value':money(total(deals.filter(stage='won'),'value')),'note':'Valor total dos negócios ganhos'},
      {'label':'Contatos','value':Contact.objects.filter(owner=user).count(),'note':'Relacionamentos no seu espaço'},
      {'label':'Próximas atividades','value':tasks.count(),'note':f'{late} com prazo vencido'},
    ]
    lanes = [{'label':label,'count':active.filter(stage=key).count(),'items':list(active.filter(stage=key).select_related('contact')[:3])} for key,label in Deal.STAGES[:4]]
    return {'today':today,'heading':'Seu pipeline, em perspectiva.','insight':('1 atividade precisa de atenção hoje.' if late == 1 else f'{late} atividades precisam de atenção hoje.') if late else 'Cada oportunidade tem espaço para um próximo passo.', 'metrics':metrics,'empty':not deals.exists() and not Contact.objects.filter(owner=user).exists(), 'chart_title':'Valor por etapa','chart_subtitle':'Distribuição do pipeline aberto em reais','chart_legend':'Valor estimado','series':series([(label,total(active.filter(stage=key),'value')) for key,label in Deal.STAGES[:4]]),'lanes':lanes,'panels':[
      {'title':'Próximas ações','subtitle':'O que mantém as conversas em movimento','kind':'tasks','items':[panel_item(t,t.title,t.deal.title if t.deal else 'Atividade avulsa',t.due_date.strftime('%d/%m'),'Atrasada' if t.due_date<today else 'Pendente') for t in tasks.select_related('deal')[:5]]},
      {'title':'Últimos relacionamentos','subtitle':'Pessoas por trás das oportunidades','kind':'contacts','items':[panel_item(c,c.name,c.company or c.email,'Contato') for c in Contact.objects.filter(owner=user)[:5]]},
    ]}

def seed_data(user):
    today = timezone.localdate()
    people = [('Marina Costa','Ateliê Horizonte'),('Rafael Almeida','Café Aurora'),('Beatriz Santos','Estúdio Norte'),('Luiza Martins','Casa Flora'),('Pedro Lima','Nexo Arquitetura'),('Camila Rocha','Vértice Design')]
    contacts = [Contact.objects.create(owner=user,name=name,company=company,email=f'contato{i}@example.com',phone=f'(11) 90000-00{i:02}') for i,(name,company) in enumerate(people)]
    stages = ['lead','qualified','proposal','negotiation','won','proposal']
    values = ['4800','12500','8600','18400','7200','5600']
    deals = [Deal.objects.create(owner=user,title=title,contact=c,value=Decimal(value),stage=stage,expected_close=today+timedelta(days=7+i*3)) for i,(c,title,value,stage) in enumerate(zip(contacts,['Nova identidade digital','Plataforma de pedidos','Portal de clientes','Experiência de marca','Site institucional','Catálogo online'],values,stages))]
    for i,title in enumerate(['Enviar proposta revisada','Agendar conversa de descoberta','Apresentar cronograma','Confirmar escopo do projeto','Compartilhar referências']):
        Task.objects.create(owner=user,title=title,deal=deals[i],due_date=today+timedelta(days=i-1))
