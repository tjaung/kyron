from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from server.app.services.auth import require_auth
from server.core.database import get_session
from server.models.context import Patient, PatientPractice, Provider, ProviderPractice
from server.schemas.auth import AuthSession
from server.schemas.directory import PatientPage, ProviderPage

router = APIRouter(tags=["directory"])


@router.get("/patients", response_model=PatientPage)
def patients(response: Response, limit: int = Query(20, ge=1, le=100),
             offset: int = Query(0, ge=0), auth: AuthSession = Depends(require_auth),
             session: Session = Depends(get_session)):
    query = select(Patient.patient_id, Patient.first_name, Patient.last_name,
                   Patient.date_of_birth, PatientPractice.medical_record_number).join(
        PatientPractice, PatientPractice.patient_id == Patient.patient_id,
    ).where(PatientPractice.practice_id == auth.practice.practice_id)
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.execute(query.order_by(Patient.last_name, Patient.first_name, Patient.patient_id)
                           .offset(offset).limit(limit)).mappings().all()
    response.headers["Cache-Control"] = "no-store"
    return {"items": rows, "total": total}


@router.get("/providers", response_model=ProviderPage)
def providers(response: Response, limit: int = Query(20, ge=1, le=100),
              offset: int = Query(0, ge=0), auth: AuthSession = Depends(require_auth),
              session: Session = Depends(get_session)):
    query = select(Provider).where(Provider.provider_id.in_(
        select(ProviderPractice.provider_id).where(ProviderPractice.practice_id == auth.practice.practice_id)))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(Provider.last_name, Provider.first_name, Provider.provider_id)
                           .offset(offset).limit(limit)).all()
    response.headers["Cache-Control"] = "no-store"
    return {"items": rows, "total": total}
