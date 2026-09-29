"""Controller providers so routers receive a ready, tenant-bound controller per request."""

from typing import Annotated

from fastapi import Depends

from app.controllers.auth_controller import AuthController
from app.controllers.briefing_controller import BriefingController
from app.controllers.commitment_controller import CommitmentController
from app.controllers.integration_controller import IntegrationController
from app.controllers.meeting_controller import MeetingController
from app.controllers.reconciliation_controller import ReconciliationController
from app.controllers.settings_controller import SettingsController
from app.dependencies.auth import CurrentUser
from app.dependencies.database import DbSession


def _auth(db: DbSession) -> AuthController:
    return AuthController(db)


def _meetings(db: DbSession, user: CurrentUser) -> MeetingController:
    return MeetingController(db, user)


def _commitments(db: DbSession, user: CurrentUser) -> CommitmentController:
    return CommitmentController(db, user)


def _reconciliation(db: DbSession, user: CurrentUser) -> ReconciliationController:
    return ReconciliationController(db, user)


def _briefings(db: DbSession, user: CurrentUser) -> BriefingController:
    return BriefingController(db, user)


def _settings(db: DbSession, user: CurrentUser) -> SettingsController:
    return SettingsController(db, user)


def _integrations(db: DbSession, user: CurrentUser) -> IntegrationController:
    return IntegrationController(db, user)


AuthCtl = Annotated[AuthController, Depends(_auth)]
MeetingCtl = Annotated[MeetingController, Depends(_meetings)]
CommitmentCtl = Annotated[CommitmentController, Depends(_commitments)]
ReconciliationCtl = Annotated[ReconciliationController, Depends(_reconciliation)]
BriefingCtl = Annotated[BriefingController, Depends(_briefings)]
SettingsCtl = Annotated[SettingsController, Depends(_settings)]
IntegrationCtl = Annotated[IntegrationController, Depends(_integrations)]
