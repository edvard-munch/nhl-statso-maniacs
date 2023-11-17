from __future__ import absolute_import, unicode_literals
from celery import shared_task
from django.core import management


@shared_task
def upd_database():
    management.call_command('upd_tms')
    management.call_command('upd_pls')
    management.call_command('upd_gms')


# @celery.task
# def send_confirmation_mail(user_id):
#     user = User.get(User.pk == user_id)
#     send_mail(
#         to=user.email,
#         subject='[Selfmailbot] Confirm your email',
#         user_id=user.id,
#         text=get_template('email/confirmation.txt').render(user=user),
#     )