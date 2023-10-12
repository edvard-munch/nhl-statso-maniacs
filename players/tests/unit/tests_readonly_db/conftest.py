import pytest


@pytest.fixture(scope='session')
def django_db_setup():
    """Avoid creating/setting up the test database"""
    pass


@pytest.fixture
def db_access_without_rollback_and_truncate(request, django_db_setup, django_db_blocker):
    django_db_blocker.unblock()
    request.addfinalizer(django_db_blocker.restore)


@pytest.fixture
def msg():
    return 'AAAAAAAAAAA----------------------------------------AAAAAAAAAA'


# def decorator(func):
#     print('Some')
#     return func


# def dec_1(func):
#     print('laaaaaaaaaaaa')
#     return func


# @decorator
# @dec_1
# def main_func():
#     return 'Main'


# print(main_func())
