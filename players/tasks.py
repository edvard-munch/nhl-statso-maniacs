from __future__ import absolute_import, unicode_literals
from celery import shared_task
from django.core import management


@shared_task
def upd_pls():
    management.call_command('upd_tms')
    management.call_command('upd_pls')
    management.call_command('upd_pls_tot')
    management.call_command('upd_gms')
    management.call_command('upd_pls_sbs')
    management.call_command('upd_pls_proj')
    # management.call_command('upd_pls_fw')
    # management.call_command('upd_pls_multi_g')
    # management.call_command('upd_pls_logs_fw')
    # management.call_command('check_sbs')


@shared_task
def upd_tms():
    management.call_command('upd_tms')


# @celery.task
# def send_confirmation_mail(user_id):
#     user = User.get(User.pk == user_id)
#     send_mail(
#         to=user.email,
#         subject='[Selfmailbot] Confirm your email',
#         user_id=user.id,
#         text=get_template('email/confirmation.txt').render(user=user),
#     )