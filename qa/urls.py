from django.urls import path

from qa import views

app_name = "qa"
urlpatterns = [
    path("", views.ask, name="ask"),
    path("about/", views.about, name="about"),
]
