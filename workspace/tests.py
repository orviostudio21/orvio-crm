
import csv
from io import StringIO
from datetime import timedelta
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.forms.models import model_to_dict
from django.test import TestCase, Client as Browser
from django.urls import reverse
from django.utils import timezone
from .domain import REGISTRY, seed_data, dashboard_data
from .forms import form_for
from .models import *

class WorkspaceTests:
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user('marina',password='A-strong-password-2026')
        cls.other = get_user_model().objects.create_user('rafael',password='A-strong-password-2026')
        seed_data(cls.user)
        seed_data(cls.other)

    def setUp(self):
        cache.clear()
        self.client.force_login(self.user)

    def test_private_routes_require_login(self):
        self.client.logout()
        for url in ['/', '/settings/', '/api/overview/']:
            self.assertEqual(self.client.get(url).status_code,302)

    def test_dashboard_and_api_render_real_data(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'Orvio')
        self.assertNotRegex(response.content.decode(), r'height:[0-9]+,[0-9]+%')
        api = self.client.get('/api/overview/')
        self.assertEqual(api.status_code,200)
        self.assertEqual(len(api.json()['metrics']),4)

    def test_all_lists_details_and_forms_render(self):
        for kind,config in REGISTRY.items():
            obj = config['model'].objects.filter(owner=self.user).first()
            for url in [f'/records/{kind}/',f'/records/{kind}/new/',f'/records/{kind}/{obj.pk}/',f'/records/{kind}/{obj.pk}/edit/',f'/records/{kind}/{obj.pk}/delete/']:
                with self.subTest(url=url):
                    self.assertEqual(self.client.get(url).status_code,200)

    def test_foreign_objects_are_inaccessible(self):
        for kind,config in REGISTRY.items():
            obj = config['model'].objects.filter(owner=self.other).first()
            for suffix in ['', 'edit/', 'delete/']:
                url = f'/records/{kind}/{obj.pk}/'+suffix
                self.assertEqual(self.client.get(url).status_code,404)
                self.assertEqual(self.client.post(url,{}).status_code,404)
            self.assertTrue(config['model'].objects.filter(pk=obj.pk).exists())

    def test_foreign_relations_are_not_form_choices(self):
        for config in REGISTRY.values():
            model = config['model']
            obj = model(owner=self.user)
            form = form_for(model)(instance=obj,user=self.user)
            for field in form.fields.values():
                if hasattr(field,'queryset') and field.queryset is not None:
                    self.assertFalse(field.queryset.exclude(owner=self.user).exists())

    def test_owner_cannot_be_changed_by_post(self):
        kind,config = next(iter(REGISTRY.items()))
        obj = config['model'].objects.filter(owner=self.user).first()
        data = model_to_dict(obj)
        data['owner'] = self.other.pk
        for key,value in list(data.items()):
            if value is None:
                data[key] = ''
            elif hasattr(value,'isoformat'):
                data[key] = timezone.localtime(value).strftime('%Y-%m-%dT%H:%M') if isinstance(value,timezone.datetime) else value.isoformat()
        response = self.client.post(f'/records/{kind}/{obj.pk}/edit/',data)
        self.assertEqual(response.status_code,302)
        obj.refresh_from_db()
        self.assertEqual(obj.owner_id,self.user.pk)

    def test_csv_export_is_scoped(self):
        for kind,config in REGISTRY.items():
            response = self.client.get(f'/records/{kind}/export/')
            self.assertEqual(response.status_code,200)
            rows = list(csv.reader(StringIO(response.content.decode('utf-8-sig'))))
            self.assertEqual(len(rows),config['model'].objects.filter(owner=self.user).count()+1)

    def test_demo_is_idempotent_and_does_not_overwrite(self):
        counts = [c['model'].objects.filter(owner=self.user).count() for c in REGISTRY.values()]
        self.client.post('/demo/')
        self.assertEqual(counts,[c['model'].objects.filter(owner=self.user).count() for c in REGISTRY.values()])

    def test_new_account_starts_empty_and_can_seed(self):
        fresh = get_user_model().objects.create_user('new-account',password='Some-strong-pass-26')
        self.client.force_login(fresh)
        self.assertContains(self.client.get('/'),'Seu próximo capítulo')
        self.assertEqual(self.client.post('/demo/').status_code,302)
        self.assertTrue(all(c['model'].objects.filter(owner=fresh).exists() for c in REGISTRY.values()))

    def test_mutations_require_csrf(self):
        browser = Browser(enforce_csrf_checks=True)
        browser.force_login(self.user)
        self.assertEqual(browser.post('/demo/').status_code,403)

    def test_logout_is_post_only(self):
        self.assertEqual(self.client.get('/logout/').status_code,405)
        self.assertEqual(self.client.post('/logout/').status_code,302)

    def test_unknown_collections_404(self):
        self.assertEqual(self.client.get('/records/unknown/').status_code,404)

    def test_signup_rejects_weak_password(self):
        self.client.logout()
        response = self.client.post('/signup/',{'username':'weak','password1':'123','password2':'123'})
        self.assertEqual(response.status_code,200)
        self.assertFalse(get_user_model().objects.filter(username='weak').exists())

    def test_signup_and_login(self):
        self.client.logout()
        response = self.client.post('/signup/',{'username':'new-user','password1':'A-new-strong-pass-2026','password2':'A-new-strong-pass-2026'})
        self.assertEqual(response.status_code,302)
        self.client.post('/logout/')
        response = self.client.post('/login/',{'username':'new-user','password':'A-new-strong-pass-2026'})
        self.assertEqual(response.status_code,302)

    def test_password_change_preserves_session(self):
        response = self.client.post('/settings/',{'old_password':'A-strong-password-2026','new_password1':'Changed-strong-pass-26','new_password2':'Changed-strong-pass-26'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get('/').status_code,200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('Changed-strong-pass-26'))

    def test_login_rate_limit(self):
        self.client.logout()
        for i in range(20):
            self.client.post('/login/',{'username':'absent','password':'wrong'})
        self.assertEqual(self.client.post('/login/',{'username':'absent','password':'wrong'}).status_code,429)

    def test_admin_forms_have_owner_and_scoped_relations(self):
        from django.contrib import admin
        from django.test import RequestFactory
        superuser = get_user_model().objects.create_superuser('admin-review', password='Admin-test-password-26', email='admin@example.com')
        request = RequestFactory().get('/admin/')
        request.user = superuser
        for config in REGISTRY.values():
            model_admin = admin.site._registry[config['model']]
            form = model_admin.get_form(request)()
            self.assertEqual(form.instance.owner, superuser)
            for field in form.fields.values():
                if hasattr(field, 'queryset') and field.queryset is not None:
                    self.assertFalse(field.queryset.exclude(owner=superuser).exists())

    def test_health_checks_database(self):
        self.assertEqual(self.client.get('/health/').json(),{'status':'ok'})


class CRMTests(WorkspaceTests, TestCase):
    def test_negative_deal_is_rejected(self):
        c = Contact.objects.filter(owner=self.user).first()
        form = form_for(Deal)({'title':'Inválido','contact':c.pk,'value':'-1','stage':'lead','expected_close':'2026-11-01'},user=self.user)
        self.assertFalse(form.is_valid())

    def test_foreign_contact_is_rejected(self):
        c = Contact.objects.filter(owner=self.other).first()
        form = form_for(Deal)({'title':'Inválido','contact':c.pk,'value':'200','stage':'lead','expected_close':'2026-11-01'},user=self.user)
        self.assertFalse(form.is_valid())

    def test_protected_contact_cannot_be_deleted(self):
        deal = Deal.objects.filter(owner=self.user).first()
        response = self.client.post(f'/records/contacts/{deal.contact_id}/delete/')
        self.assertEqual(response.status_code,302)
        self.assertTrue(Contact.objects.filter(pk=deal.contact_id).exists())

    def test_create_complete_update_activity_and_delete(self):
        response = self.client.post('/records/tasks/new/',{'title':'Retornar ligação','due_date':'2026-11-01','status':'open','deal':''})
        self.assertEqual(response.status_code,302)
        task = Task.objects.get(owner=self.user,title='Retornar ligação')
        response = self.client.post(f'/records/tasks/{task.pk}/edit/',{'title':task.title,'due_date':'2026-11-01','status':'done','deal':''})
        self.assertEqual(response.status_code,302)
        task.refresh_from_db()
        self.assertEqual(task.status,'done')
        self.client.post(f'/records/tasks/{task.pk}/delete/')
        self.assertFalse(Task.objects.filter(pk=task.pk).exists())

    def test_pipeline_excludes_won_and_lost(self):
        active = Deal.objects.filter(owner=self.user).exclude(stage__in=['won','lost'])
        self.assertEqual(dashboard_data(self.user)['metrics'][0]['value'], __import__('workspace.domain',fromlist=['money']).money(sum(d.value for d in active)))

    def test_csv_formula_neutralization(self):
        Contact.objects.create(owner=self.user,name='=1+1',email='formula@example.com')
        response = self.client.get('/records/contacts/export/')
        self.assertIn("'=1+1",response.content.decode('utf-8-sig'))

    def test_search_filters_records(self):
        response = self.client.get('/records/contacts/',{'q':'Ateliê Horizonte'})
        self.assertContains(response,'Marina Costa')
        self.assertNotContains(response,'Beatriz Santos')
