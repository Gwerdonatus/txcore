from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from txcore.workspace import workspace
from txcore.auth import WorkspaceTokenView
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


urlpatterns = [
    path("", workspace, name="workspace"),
    path("payments/return/", workspace, name="payment-return"),
    path("login/", LoginView.as_view(template_name="txcore/login.html"), name="login"),
    path("logout/", LogoutView.as_view(next_page="/login/"), name="logout"),
    path("api/token/", WorkspaceTokenView.as_view(), name="workspace-token"),
    path("api-auth/", include("rest_framework.urls")),
    path("admin/", admin.site.urls),
    path("api/v1/transactions/", include("txcore.apps.transactions.urls")),
    path("api/v1/webhooks/", include("txcore.apps.webhooks.urls")),
    path("api/v1/reconciliation/", include("txcore.apps.reconciliation.urls")),
    # Observability
    path("", include("django_prometheus.urls")),
    # API docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
