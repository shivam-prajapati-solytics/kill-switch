from django.urls import path
from agentguard import views
urlpatterns = [
    path("health/", views.health),
    path("api/agent/query/", views.agent_query),
    path("api/admin/kill/", views.remote_kill),
    path("api/admin/reset/", views.remote_reset),
    path("api/admin/status/", views.kill_status),
]
