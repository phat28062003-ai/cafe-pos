"""
URL configuration for cafe_pos project.
"""
from django.contrib import admin
from django.urls import path, re_path
from strawberry.django.views import GraphQLView
from pos.schema import schema
from pos import views as pos_views

urlpatterns = [
    path('', pos_views.index, name='index'),
    path('admin/', admin.site.urls),
    re_path(r'^graphql/?$', GraphQLView.as_view(schema=schema)),
]
