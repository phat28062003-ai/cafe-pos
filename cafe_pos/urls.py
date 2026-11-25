"""
URL configuration for cafe_pos project.
"""
from django.contrib import admin
from django.urls import path, re_path
from strawberry.django.views import GraphQLView
from pos.schema import schema

urlpatterns = [
    path('admin/', admin.site.urls),
    re_path(r'^graphql/?$', GraphQLView.as_view(schema=schema)),
]
