"""Small, shared discovery hint; never schedules or renders media."""

VIDEO_HANDOFF_HINT = (
    "Optional feature video: local-feature-videos is a shared skill. Focus on the "
    "feature first. Only after an explicit video request, load that skill, record "
    "the request in the project's local video queue, and produce it after feature "
    "validation using the real project flow. At successful closure of a user-visible "
    "feature, offer a video once if neither requested, offered nor declined in the "
    "task history; never offer during implementation, reviews, status replies or "
    "unrelated work. No automatic video jobs, model calls or render. Keep explicit "
    "requests in the task handoff until delivered; use approved shared presets and "
    "deliver files inside the requesting workspace. If the skill is unavailable, "
    "report that instead of pretending to start."
)


def with_video_handoff(message: str) -> str:
    if VIDEO_HANDOFF_HINT in message:
        return message
    return f"{message}\n\n{VIDEO_HANDOFF_HINT}"
