from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/publico/", include("public.urls")),
    path("api/", include("jobs.urls")),
]
