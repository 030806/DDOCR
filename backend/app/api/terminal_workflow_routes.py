from typing import Annotated, Any
from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field
from app.api.routes import service, authenticated_user
from app.services.terminal_workflow import TerminalWorkflowService
from app.utils.common import envelope

router = APIRouter(prefix='/api/v1/terminal-workflows', tags=['terminal-workflows'])
class Create(BaseModel):
    file_id: str
class Action(BaseModel):
    base_revision: int = Field(ge=0)
    changes: dict[str, Any] = Field(default_factory=dict)
    step: int = Field(default=1, ge=1, le=6)

def context(request, authorization):
    return TerminalWorkflowService(service(request)), authenticated_user(request, authorization)['id']

@router.post('')
def create(body: Create, request: Request, authorization: Annotated[str | None, Header()] = None):
    flow, owner = context(request, authorization)
    return envelope(flow.create(body.file_id, owner))

@router.get('/{ident}')
def get(ident: str, request: Request, authorization: Annotated[str | None, Header()] = None):
    flow, owner = context(request, authorization)
    return envelope(flow.get(ident, owner))

@router.post('/{ident}/{action}')
def action(ident: str, action: str, body: Action, request: Request, authorization: Annotated[str | None, Header()] = None):
    from fastapi import HTTPException
    flow, owner = context(request, authorization)
    args = (ident, owner, body.base_revision)
    if action == 'configuration':
        try:
            value = flow.patch(*args, body.changes)
        except (KeyError, TypeError, ValueError, OverflowError):
            raise HTTPException(422, '配置格式无效')
    elif action == 'confirmations': value = flow.confirm(*args, body.step)
    elif action == 'skeleton-detections': value = flow.detect(*args)
    elif action == 'position-previews': value = flow.preview_positions(*args)
    elif action == 'recognitions': value = flow.recognize(*args)
    else: raise HTTPException(404, 'Unknown action')
    return envelope(value)
