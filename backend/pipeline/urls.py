from django.urls import path

from pipeline import views

urlpatterns = [
    path("noticias", views.noticias, name="produzir-noticia"),
    path("curadorias", views.curadorias, name="produzir-curadoria"),
]
