from django.urls import path

from laws import views

app_name = "laws"
urlpatterns = [
    path("", views.index, name="index"),
    path("<slug:source>/<str:number>/", views.article, name="article"),
]
