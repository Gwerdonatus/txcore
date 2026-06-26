from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


urlpatterns = [
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
