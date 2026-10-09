from django.urls import path

from finance import views

urlpatterns = [
    path("relatorios/custos", views.custos, name="relatorios-custos"),
    path("relatorios/custos.csv", views.custos_csv, name="relatorios-custos-csv"),
]
