"""
ASGI config for cafe_pos project.
Hỗ trợ cả HTTP (Query / Mutation) và WebSocket (Subscription) qua cùng một endpoint /graphql.
"""

import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cafe_pos.settings')
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import re_path
from strawberry.channels import GraphQLHTTPConsumer, GraphQLWSConsumer
from pos.schema import schema

# WebSocket route cho Strawberry GraphQL Subscriptions
websocket_urlpatterns = [
    re_path(r"^graphql/?$", GraphQLWSConsumer.as_asgi(schema=schema)),
]

# ASGI application router
application = ProtocolTypeRouter({
    "http": URLRouter([
        re_path(r"^graphql/?$", GraphQLHTTPConsumer.as_asgi(schema=schema)),
        re_path(r"^", django_asgi_app),
    ]),
    "websocket": URLRouter(websocket_urlpatterns),
})
