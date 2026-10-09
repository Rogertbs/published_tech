from django.urls import path

from public import views

urlpatterns = [
    path("home", views.home, name="public-home"),
    path("secao/<slug:secao>", views.secao, name="public-secao"),
    path("artigo/<slug:slug>", views.artigo, name="public-artigo"),
]
