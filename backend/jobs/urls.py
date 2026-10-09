from django.urls import path

from jobs import views

urlpatterns = [
    path("execucoes", views.execucoes, name="execucoes"),
    path("execucoes/<int:pk>", views.execucao, name="execucao"),
]
