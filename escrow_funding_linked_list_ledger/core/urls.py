from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register, name="register"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html"
        ),
        name="login",
    ),
    path(
        "logout/",
        auth_views.LogoutView.as_view(),
        name="logout",
    ),
    path(
        "projects/create/",
        views.create_project,
        name="create_project",
    ),
    path(
        "projects/<int:project_id>/",
        views.project_detail,
        name="project_detail",
    ),
    path(
        "projects/<int:project_id>/contribute/",
        views.contribute,
        name="contribute",
    ),
    path(
        "projects/<int:project_id>/vote/",
        views.cast_vote,
        name="cast_vote",
    ),
]