from django.contrib import admin
from django.urls import include, path

from config import views

urlpatterns = [
    path("", include("qa.urls")),
    path("laws/", include("laws.urls")),
    path("admin/", admin.site.urls),
    path("livez/", views.livez, name="livez"),
    path("healthz/", views.healthz, name="healthz"),
]
