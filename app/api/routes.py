from fastapi import APIRouter, Request

from app.agents.supervisor import build_supervisor_graph
from app.middleware.context import build_development_context
from app.schemas import AssistantInvokeRequest, AssistantInvokeResponse

router = APIRouter()
_graph = build_supervisor_graph()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/assistant/invoke", response_model=AssistantInvokeResponse)
async def invoke_assistant(payload: AssistantInvokeRequest, request: Request) -> AssistantInvokeResponse:
    context = build_development_context(request, payload.thread_id)
    result = await _graph.ainvoke({"message": payload.message})
    return AssistantInvokeResponse(
        request_id=context.request_id,
        thread_id=context.thread_id,
        intent=result["intent"],
        status=result["status"],
        message=result["result_message"],
        warnings=result["warnings"],
    )
