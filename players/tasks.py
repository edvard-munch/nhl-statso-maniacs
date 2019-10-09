from __future__ import absolute_import, unicode_literals
from celery import shared_task
from django.core import management


@shared_task
def upd_pls():
    management.call_command('upd_tms')
    management.call_command('upd_pls')
    management.call_command('upd_pls_tot')
    management.call_command('upd_gms')
    management.call_command('upd_pls_log')
    management.call_command('upd_pls_sbs')
    management.call_command('upd_pls_proj')
    # management.call_command('upd_pls_fw')
    # management.call_command('upd_pls_multi_g')
    # management.call_command('upd_pls_logs_fw')
    # management.call_command('check_sbs')


@shared_task
def upd_tms():
    management.call_command('upd_tms')
