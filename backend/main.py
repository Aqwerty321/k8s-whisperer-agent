from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.agent import AgentRuntime, BackgroundPoller
from backend.app.api import router
from backend.app.audit import AuditLogger
from backend.app.config import get_settings
from backend.app.integrations.k8s import K8sClient
from backend.app.integrations.llm import LLMClient
from backend.app.integrations.slack import SlackClient


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    audit_logger = AuditLogger(settings.audit_log_path)
    k8s_client = K8sClient(kubeconfig=settings.kubeconfig)
    llm_client = LLMClient(api_key=settings.gemini_api_key, model=settings.gemini_model)
    slack_client = SlackClient(
        bot_token=settings.slack_bot_token,
        signing_secret=settings.slack_signing_secret,
        default_channel=settings.slack_default_channel,
        public_base_url=settings.public_base_url,
        request_tolerance_seconds=settings.slack_request_tolerance_seconds,
    )
    runtime = AgentRuntime(
        settings=settings,
        audit_logger=audit_logger,
        k8s_client=k8s_client,
        llm_client=llm_client,
        slack_client=slack_client,
    )
    poller = BackgroundPoller(
        runtime=runtime,
        poll_interval_seconds=settings.poll_interval_seconds,
    )

    app.state.settings = settings
    app.state.audit_logger = audit_logger
    app.state.k8s_client = k8s_client
    app.state.llm_client = llm_client
    app.state.slack_client = slack_client
    app.state.runtime = runtime
    app.state.poller = poller

    if settings.enable_background_polling:
        await poller.start()

    yield

    await poller.stop()


app = FastAPI(
    title="K8sWhisperer",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)
