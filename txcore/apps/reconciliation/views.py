import logging
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from drf_spectacular.utils import extend_schema
from txcore.core.schema import (
    ReconciliationUpload, ReconciliationSummary, ReconciliationDetail, ReconciliationListResponse,
)

from .models import ReconciliationRun, ReconciliationDiscrepancy
from .engine import run_reconciliation

logger = logging.getLogger(__name__)


class ReconciliationUploadView(APIView):
    """
    POST /api/v1/reconciliation/upload/
    Upload a CSV file for reconciliation.
    """
    parser_classes = [MultiPartParser]

    @extend_schema(request=ReconciliationUpload, responses={201: ReconciliationSummary})
    def post(self, request):
        csv_file = request.FILES.get("file")
        if not csv_file:
            return Response(
                {"error": {"detail": "A CSV file is required (field: 'file')."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not csv_file.name.endswith(".csv"):
            return Response(
                {"error": {"detail": "Only CSV files are accepted."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            csv_content = csv_file.read().decode("utf-8")
        except UnicodeDecodeError:
            return Response(
                {"error": {"detail": "CSV file must be UTF-8 encoded."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        run = ReconciliationRun.objects.create(filename=csv_file.name)
        run = run_reconciliation(run, csv_content)

        return Response(
            {
                "run_id": str(run.id),
                "status": run.status,
                "filename": run.filename,
                "total_rows": run.total_rows,
                "matched": run.matched,
                "discrepancies": run.discrepancies,
                "skipped": run.skipped,
                "error_message": run.error_message or None,
            },
            status=status.HTTP_201_CREATED,
        )


class ReconciliationRunDetailView(APIView):
    """GET /api/v1/reconciliation/<run_id>/"""

    @extend_schema(responses={200: ReconciliationDetail})
    def get(self, request, run_id):
        try:
            run = ReconciliationRun.objects.get(id=run_id)
        except ReconciliationRun.DoesNotExist:
            return Response(
                {"error": {"detail": "Reconciliation run not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )

        discrepancies = ReconciliationDiscrepancy.objects.filter(run=run)

        return Response({
            "run_id": str(run.id),
            "status": run.status,
            "filename": run.filename,
            "total_rows": run.total_rows,
            "matched": run.matched,
            "discrepancies": run.discrepancies,
            "skipped": run.skipped,
            "discrepancy_detail": [
                {
                    "reference": d.reference,
                    "type": d.discrepancy_type,
                    "expected_amount": str(d.expected_amount) if d.expected_amount else None,
                    "actual_amount": str(d.actual_amount) if d.actual_amount else None,
                    "expected_status": d.expected_status,
                    "actual_status": d.actual_status,
                    "notes": d.notes,
                    "resolved": d.resolved,
                }
                for d in discrepancies
            ],
        })


class ReconciliationRunListView(APIView):
    """GET /api/v1/reconciliation/"""

    @extend_schema(responses={200: ReconciliationListResponse})
    def get(self, request):
        runs = ReconciliationRun.objects.all()[:20]
        data = [
            {
                "run_id": str(r.id),
                "filename": r.filename,
                "status": r.status,
                "total_rows": r.total_rows,
                "matched": r.matched,
                "discrepancies": r.discrepancies,
                "created_at": r.created_at.isoformat(),
            }
            for r in runs
        ]
        return Response({"count": len(data), "results": data})
