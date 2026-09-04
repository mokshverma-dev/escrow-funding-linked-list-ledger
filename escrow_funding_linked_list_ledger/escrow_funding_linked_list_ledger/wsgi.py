"""
WSGI config for escrow_funding_linked_list_ledger project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault(
    "DJANGO_SETTINGS_MODULE", "escrow_funding_linked_list_ledger.settings"
)

application = get_wsgi_application()
